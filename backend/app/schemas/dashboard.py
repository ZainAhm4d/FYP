"""
Dashboard Schemas
Pydantic models for dashboard validation and serialization
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


# Base schema with common attributes
class DashboardBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Dashboard name")
    description: Optional[str] = Field(None, max_length=500, description="Dashboard description")


# Schema for dashboard creation
class DashboardCreate(DashboardBase):
    config_json: Dict[str, Any] = Field(..., description="Dashboard configuration including charts and layout")


# Schema for dashboard update
class DashboardUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Dashboard name")
    description: Optional[str] = Field(None, max_length=500, description="Dashboard description")
    config_json: Optional[Dict[str, Any]] = Field(None, description="Dashboard configuration")


# Schema for dashboard response
class Dashboard(DashboardBase):
    id: int
    user_id: int
    config_json: Dict[str, Any]
    is_public: bool = False
    share_token: Optional[str] = None
    view_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


# Schema for dashboard list item (minimal info for list view)
class DashboardListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    chart_count: int = Field(0, description="Number of charts in dashboard")
    is_public: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for sharing response
class ShareResponse(BaseModel):
    share_token: str
    share_url: str
    is_public: bool
    view_count: int


# Schema for the public (no-auth) shared dashboard view
class PublicDashboardResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    config_json: Dict[str, Any]
    view_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# Schema for dashboard export
class DashboardExport(BaseModel):
    dashboard_name: str
    exported_at: datetime
    charts: list
    data: Dict[str, Any]
    schema_version: int = 1   # CH-12: import compatibility marker


# Schema for client-side PDF export (browser renders charts, server assembles PDF)
class ChartImageData(BaseModel):
    title: str = ""
    image_b64: str = ""   # data:image/png;base64,... or raw base64
    insights: list = []


class PdfFromImagesRequest(BaseModel):
    dashboard_name: str = "Dashboard"
    description: str = ""
    charts: list[ChartImageData] = []
