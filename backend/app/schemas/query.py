"""
Query Schemas
Pydantic models for query-related requests and responses
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime


class QueryExecuteRequest(BaseModel):
    """Request to execute a query template"""
    template_type: str = Field(..., description="Type of query template to execute")
    dataset_id: int = Field(..., description="ID of dataset to query")
    parameters: Dict[str, Any] = Field(..., description="Query parameters")


class QueryResult(BaseModel):
    """Query execution result"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    row_count: Optional[int] = None
    summary: Optional[Dict[str, Any]] = None


class ChartConfig(BaseModel):
    """Chart configuration"""
    chart_type: str
    data: List[Dict[str, Any]]
    config: Dict[str, Any]
    summary: Optional[Dict[str, Any]] = None


class QueryExecuteResponse(BaseModel):
    """Response from query execution"""
    success: bool
    message: Optional[str] = None
    template_type: Optional[str] = None
    query_result: Optional[QueryResult] = None
    chart_config: Optional[Dict[str, Any]] = None
    plotly_spec: Optional[Dict[str, Any]] = None
    insights: Optional[List[Dict[str, Any]]] = None
    data_state: Optional[str] = None   # "raw" | "cleaned" (CP-21)


class TemplateListResponse(BaseModel):
    """Response for listing available templates"""
    templates: List[Dict[str, Any]]
    count: int


class DatasetColumnsResponse(BaseModel):
    """Response for dataset column information"""
    dataset_id: int
    columns: List[Dict[str, Any]]
    column_count: int


# ---------------------------------------------------------------------------
# Natural-language query schemas (Phase 2)
# ---------------------------------------------------------------------------

class NaturalQueryRequest(BaseModel):
    """Request for the /queries/natural endpoint"""
    query_text: str = Field(..., min_length=3, description="Plain-English question about the data")
    dataset_id: int = Field(..., description="ID of the dataset to query")


class ForecastRequest(BaseModel):
    """Request to generate a time-series forecast."""
    dataset_id:    int              = Field(..., description="Dataset to query")
    parameters:    Dict[str, Any]   = Field(..., description="Trend query parameters (same as execute)")
    n_periods:     int              = Field(6, ge=1, le=24, description="Periods to forecast ahead")
    confidence:    float            = Field(0.95, ge=0.5, le=0.99, description="Prediction interval width")


class ForecastResponse(BaseModel):
    """Response from the /queries/forecast endpoint."""
    success:            bool
    message:            Optional[str]             = None
    fitted:             Optional[List[Dict[str, Any]]] = None
    forecast:           Optional[List[Dict[str, Any]]] = None
    r_squared:          Optional[float]           = None
    trend:              Optional[str]             = None
    slope_per_period:   Optional[float]           = None
    n_periods:          Optional[int]             = None
    confidence:         Optional[float]           = None
    method:             Optional[str]             = None
    plotly_traces:      Optional[List[Dict[str, Any]]] = None  # ready to pass to Plotly.addTraces()


class NaturalQueryResponse(BaseModel):
    """Response from the /queries/natural endpoint"""
    success: bool
    message: Optional[str] = None
    # NLP metadata
    intent: Optional[str] = None
    confidence: Optional[float] = None
    nlp_mode: Optional[str] = None           # "embeddings" or "keyword"
    detected_parameters: Optional[Dict[str, Any]] = None
    clarification: Optional[str] = None      # set when user input is ambiguous
    # Populated when ready_to_execute is True
    query_result: Optional[Dict[str, Any]] = None
    chart_config: Optional[Dict[str, Any]] = None
    plotly_spec: Optional[Dict[str, Any]] = None
    insights: Optional[List[Dict[str, Any]]] = None
    data_state: Optional[str] = None   # "raw" | "cleaned" (CP-21)
