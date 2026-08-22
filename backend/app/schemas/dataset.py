"""
Dataset Schemas
Pydantic models for dataset validation and serialization
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


# Base schema with common attributes
class DatasetBase(BaseModel):
    filename: str
    original_filename: str


# Schema for dataset upload request (multipart form)
class DatasetUpload(BaseModel):
    """Schema for validating uploaded dataset files"""
    pass  # File will be handled via UploadFile parameter


# Schema for dataset creation (internal use)
class DatasetCreate(DatasetBase):
    file_path: str
    row_count: int = 0
    column_count: int = 0
    data_types_json: Optional[str] = None
    user_id: int


# Schema for dataset response
class Dataset(DatasetBase):
    id: int
    user_id: int
    file_path: str
    row_count: int
    column_count: int
    data_types_json: Optional[str] = None
    cleaned_status: bool
    processing_status: str = 'ready'
    upload_date: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


# Schema for dataset list item (minimal info)
class DatasetListItem(BaseModel):
    id: int
    filename: str
    original_filename: str
    row_count: int
    column_count: int
    upload_date: datetime
    cleaned_status: bool
    processing_status: str = 'ready'
    file_size: Optional[str] = "N/A"  # Will be calculated
    source_type: str = 'upload'
    refresh_interval_minutes: Optional[int] = None
    last_refreshed: Optional[datetime] = None
    ingest_token: Optional[str] = None   # owner-only list; powers the push-setup snippet
    last_push_at: Optional[datetime] = None  # CH-10: last webhook delivery

    class Config:
        from_attributes = True


# Schema for dataset preview
class DatasetPreview(BaseModel):
    id: int
    filename: str
    original_filename: str
    row_count: int
    column_count: int
    upload_date: datetime
    data_types: Optional[Dict[str, str]] = None  # Column name -> data type mapping
    preview_rows: List[Dict[str, Any]] = []  # First 100 rows
    column_names: List[str] = []
    
    class Config:
        from_attributes = True


# Schema for dataset statistics
class DatasetStats(BaseModel):
    total_datasets: int = 0
    total_rows: int = 0
    total_columns: int = 0
    total_storage: str = "0 MB"


# Schema for dataset deletion response
class DatasetDeleteResponse(BaseModel):
    message: str
    dataset_id: int


# ── External data connector schemas ─────────────────────────────────────────

class ListTablesRequest(BaseModel):
    """Request body for POST /datasets/connect/tables (MySQL / Postgres only)."""
    source_type: str          # "mysql" | "postgres"
    host: str
    port: int
    username: str
    password: str
    database: str

    @field_validator("source_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("mysql", "postgres"):
            raise ValueError("source_type must be 'mysql' or 'postgres'")
        return v


class ConnectSourceRequest(BaseModel):
    """Request body for POST /datasets/connect."""
    source_type: str          # "google_sheets" | "mysql" | "postgres"

    # Google Sheets fields
    url: Optional[str] = None
    # Auto-refresh interval in minutes (Google Sheets only; None = one-time import)
    refresh_interval_minutes: Optional[int] = Field(None, ge=1, le=10080)

    # Database fields (MySQL / Postgres)
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    table_name: Optional[str] = None

    # Optional display name for the resulting dataset
    dataset_name: Optional[str] = None

    @field_validator("source_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        allowed = ("google_sheets", "mysql", "postgres")
        if v not in allowed:
            raise ValueError(f"source_type must be one of {allowed}")
        return v
