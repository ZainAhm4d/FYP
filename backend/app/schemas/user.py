"""
User Pydantic Schemas
Request/Response models for user operations
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# Base User Schema
class UserBase(BaseModel):
    """Base user fields"""
    email: EmailStr
    full_name: Optional[str] = None


# User Registration Schema
class UserCreate(UserBase):
    """Schema for user registration"""
    password: str = Field(..., min_length=8, description="Password (min 8 chars, uppercase, number, special char)")


# User Login Schema
class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


# User in Database (with hashed password)
class UserInDB(UserBase):
    """Schema for user stored in database"""
    id: int
    hashed_password: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode in Pydantic v2


# User Response Schema (public-facing)
class User(UserBase):
    """Schema for user responses (no password)"""
    id: int
    is_active: bool
    created_at: datetime
    is_admin: bool = False   # CH-18: lets the frontend show/guard the Admin page

    class Config:
        from_attributes = True


# ── CH-18: admin portal schemas ───────────────────────────────────────────────

class AdminUserRow(BaseModel):
    """One row of the admin user table."""
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    dataset_count: int = 0
    dashboard_count: int = 0

    class Config:
        from_attributes = True


class AdminUserCreate(UserCreate):
    """Admin-onboarded user."""
    is_admin: bool = False


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    deleted_users: int
    total_datasets: int
    total_dashboards: int
    uploads_size_bytes: int


class AccountDeleteRequest(BaseModel):
    """Self-service account deletion — password re-entry required."""
    password: str


# Token Schemas
class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded token data"""
    email: Optional[str] = None
