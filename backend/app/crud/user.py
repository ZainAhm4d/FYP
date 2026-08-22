"""
User CRUD Operations
Database operations for User model
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash, verify_password


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get user by email address
    
    Args:
        db: Database session
        email: User's email address
    
    Returns:
        User object if found, None otherwise
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Get user by ID
    
    Args:
        db: Database session
        user_id: User's ID
    
    Returns:
        User object if found, None otherwise
    """
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: UserCreate) -> User:
    """
    Create a new user
    
    Args:
        db: Database session
        user: UserCreate schema with user data
    
    Returns:
        Created User object
    """
    hashed_password = get_password_hash(user.password)
    
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        is_active=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate user with email and password
    
    Args:
        db: Database session
        email: User's email
        password: Plain text password
    
    Returns:
        User object if authentication successful, None otherwise
    """
    user = get_user_by_email(db, email)
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return user


def update_user(db: Session, user_id: int, **kwargs) -> Optional[User]:
    """
    Update user fields
    
    Args:
        db: Database session
        user_id: User's ID
        **kwargs: Fields to update
    
    Returns:
        Updated User object if found, None otherwise
    """
    user = get_user_by_id(db, user_id)
    
    if not user:
        return None
    
    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    return user
