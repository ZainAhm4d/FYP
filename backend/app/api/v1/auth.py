"""
Authentication Endpoints
User registration, login, and profile management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, validate_password
from app.core.rate_limiter import limit_login, limit_register
from app.crud import user as crud_user
from app.schemas.user import User, UserCreate, Token, AccountDeleteRequest
from app.api.deps import get_current_active_user

router = APIRouter()


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(limit_register)])
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user
    
    - **email**: Valid email address (unique)
    - **password**: Min 8 chars, uppercase, number, special character
    - **full_name**: Optional full name
    
    Returns the created user object (without password)
    """
    # Check if user already exists
    existing_user = crud_user.get_user_by_email(db, email=user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate password strength
    is_valid, error_message = validate_password(user.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Create user
    db_user = crud_user.create_user(db, user)
    
    return db_user


@router.post("/login", response_model=Token, dependencies=[Depends(limit_login)])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Login with email and password
    
    Returns JWT access token valid for 7 days
    
    OAuth2 compatible endpoint:
    - **username**: User's email address
    - **password**: User's password
    """
    # Authenticate user
    user = crud_user.authenticate_user(db, email=form_data.username, password=form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    
    # CH-18: track last login for the admin user table
    try:
        from datetime import datetime
        user.last_login_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    # Create access token
    access_token = create_access_token(data={"sub": user.email})

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=User)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's profile information
    
    Requires valid JWT token in Authorization header:
    `Authorization: Bearer <token>`
    
    Returns user profile (id, email, full_name, etc.)
    """
    return current_user


@router.get("/test-token", response_model=User)
def test_token(current_user: User = Depends(get_current_active_user)):
    """
    Test JWT token validity

    Development endpoint to verify token authentication is working
    """
    return current_user


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_account(
    body: AccountDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    CH-18: self-service account deletion ("delete my data on request").

    Requires password re-entry. The account is soft-deleted immediately
    (locked + email anonymized) and hard-purged with all files after the
    retention window.
    """
    authed = crud_user.authenticate_user(db, email=current_user.email,
                                         password=body.password)
    if not authed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Password is incorrect")
    if getattr(current_user, "is_admin", False):
        from app.models.user import User as UserModel
        admins_left = db.query(UserModel).filter(
            UserModel.is_admin.is_(True), UserModel.deleted_at.is_(None),
            UserModel.id != current_user.id,
        ).count()
        if admins_left == 0:
            raise HTTPException(status_code=400,
                                detail="The last admin account cannot self-delete")

    from app.api.v1.admin import soft_delete_user
    from app.models.audit_log import AdminAuditLog
    original = soft_delete_user(db, current_user)
    db.add(AdminAuditLog(admin_user_id=current_user.id, action="self_delete",
                         target_user_id=current_user.id, detail=original))
    db.commit()
    return None
