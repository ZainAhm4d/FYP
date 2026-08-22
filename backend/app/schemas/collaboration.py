"""Pydantic schemas for dashboard collaboration endpoints."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class InviteCollaboratorRequest(BaseModel):
    email: EmailStr = Field(..., description="Email of the user to invite")
    role:  str      = Field("viewer", pattern="^(viewer|editor)$")


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(viewer|editor)$")


class CollaboratorOut(BaseModel):
    id:         int
    user_id:    int
    email:      str
    full_name:  Optional[str] = None
    role:       str
    created_at: datetime

    class Config:
        from_attributes = True
