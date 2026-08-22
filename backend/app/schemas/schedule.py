"""Pydantic schemas for report schedules."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class ScheduleCreate(BaseModel):
    dashboard_id:    int
    recipient_email: EmailStr
    frequency:       str                       # daily | weekly | monthly
    send_hour:       int = Field(8,  ge=0, le=23)
    send_minute:     int = Field(0,  ge=0, le=59)
    day_of_week:     Optional[int] = Field(None, ge=0, le=6)   # 0=Mon … 6=Sun
    day_of_month:    Optional[int] = Field(None, ge=1, le=31)
    timezone:        str = "UTC"               # IANA name

    @field_validator("frequency")
    @classmethod
    def _check_freq(cls, v: str) -> str:
        if v not in ("daily", "weekly", "monthly"):
            raise ValueError("frequency must be 'daily', 'weekly', or 'monthly'")
        return v

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Unknown timezone: {v}")
        return v


class ScheduleUpdate(BaseModel):
    recipient_email: Optional[EmailStr] = None
    frequency:       Optional[str] = None
    send_hour:       Optional[int] = Field(None, ge=0, le=23)
    send_minute:     Optional[int] = Field(None, ge=0, le=59)
    day_of_week:     Optional[int] = Field(None, ge=0, le=6)
    day_of_month:    Optional[int] = Field(None, ge=1, le=31)
    timezone:        Optional[str] = None
    is_active:       Optional[bool] = None

    @field_validator("frequency")
    @classmethod
    def _check_freq(cls, v):
        if v is not None and v not in ("daily", "weekly", "monthly"):
            raise ValueError("frequency must be 'daily', 'weekly', or 'monthly'")
        return v


class ScheduleResponse(BaseModel):
    id:              int
    dashboard_id:    int
    recipient_email: str
    frequency:       str
    send_hour:       int = 8
    send_minute:     int = 0
    day_of_week:     Optional[int] = None
    day_of_month:    Optional[int] = None
    timezone:        str = "UTC"
    is_active:       bool
    next_run:        Optional[datetime]
    last_run:        Optional[datetime]
    last_status:     Optional[str]
    created_at:      datetime

    class Config:
        from_attributes = True
