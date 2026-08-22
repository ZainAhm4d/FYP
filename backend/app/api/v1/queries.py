"""
Query API Endpoints
Handle query template execution and chart generation
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import pandas as pd
from app.services.data_processing.io_utils import read_tabular
import os
from difflib import get_close_matches

logger = logging.getLogger(__name__)

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.dataset import Dataset
from app.schemas.query import (
    QueryExecuteRequest,
    QueryExecuteResponse,
    TemplateListResponse,
    DatasetColumnsResponse,
    NaturalQueryRequest,
    NaturalQueryResponse,
    ForecastRequest,
    ForecastResponse,
)
from app.services.nlp import list_all_templates, get_template_by_type, parse_natural_query
from app.services.analytics import QueryExecutor
from app.services.visualization import ChartFactory, ChartBuilder
from app.services.insights import generate_insights
from app.services.data_processing import DataPreprocessor
from app.crud import query_history as crud_history

router = APIRouter()

# Patterns that identify ID / surrogate-key columns — should NOT be treated as metrics
_ID_PATTERN = re.compile(
    r"(?:^id$|_id$|^id_|_key$|_num$|number$|_no$|^no_|_code$|_ref$|invoice)",
    re.IGNORECASE,
)


def _detect_column_category(col_name: str, series: pd.Series) -> str:
    """
    Classify a DataFrame column as 'metric', 'dimension', or 'date'.

    Numeric columns that look like surrogate keys (name pattern or all-unique
    integers) are demoted to 'dimension' so the NLP engine never tries to
    SUM or AVERAGE an order_id or customer_id.
    """
    if pd.api.types.is_numeric_dtype(series):
        is_id_name = bool(_ID_PATTERN.search(col_name))
        n = len(series.dropna())
        is_all_unique = n > 1 and series.nunique() == n
        if is_id_name or (pd.api.types.is_integer_dtype(series) and is_all_unique):
            return "dimension"
        return "metric"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    # Date-sniff for string columns
    try:
        sample = series.dropna().iloc[:10]
        if len(sample) > 0:
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.5:
                return "date"
    except Exception:
        pass
    return "dimension"


def normalize_string_columns(df: pd.DataFrame, typo_threshold: float = 0.8) -> pd.DataFrame:
    """
    Generic normalization for all low-cardinality string columns in any DataFrame.
    Works on any dataset — no column names or values are hardcoded.

    Steps per column:
    1. Strip leading/trailing whitespace
    2. Convert all values to Title Case so 'north', 'NORTH', 'North' all become 'North'
       before any comparison — this ensures case-insensitive deduplication
    3. Fuzzy-match remaining unique values to catch typos (e.g. 'Noerth' → 'North'),
       always mapping the less-frequent variant to the more-frequent one
    """
    df = df.copy()
    for col in df.columns:
        # pandas 3.x infers strings as 'str' dtype, not object — check both
        if not (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])):
            continue

        # Skip columns with too many unique values (likely IDs, emails, free text)
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        unique_ratio = non_null.nunique() / len(non_null)
        if unique_ratio > 0.5:
            continue

        # Step 1: Strip whitespace
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace('nan', pd.NA)

        # Step 2: Title Case normalization
        # 'north'→'North', 'SOUTH'→'South', 'WEST'→'West', 'west'→'West'
        # This eliminates all pure case-variant duplicates in one pass.
        df[col] = df[col].apply(lambda x: x.title() if pd.notna(x) else x)

        # Step 3: Typo correction via fuzzy matching on the now-uniform Title Case values
        # e.g. 'Noerth' vs 'North' — both Title Case so comparison is fair
        freq = df[col].dropna().value_counts()
        unique_vals = freq.index.tolist()
        typo_map = {}
        for val in unique_vals:
            if val in typo_map:
                continue
            # Only compare against values not already being remapped
            candidates = [v for v in unique_vals if v != val and v not in typo_map]
            matches = get_close_matches(val, candidates, n=1, cutoff=typo_threshold)
            if matches:
                match = matches[0]
                # Always remap the less-frequent variant to the more-frequent canonical form
                if freq[val] < freq[match]:
                    typo_map[val] = match
        if typo_map:
            df[col] = df[col].replace(typo_map)

    return df


# ── CH-04 / CH-07: chart finalization shared by /execute and /natural ─────────

_CONVERTIBLE_TYPES = {"line", "area", "bar", "stacked_bar", "horizontal_bar",
                      "stacked_horizontal", "scatter", "pie"}


def _column_labels(template_type: str, parameters: Dict[str, Any]) -> Dict[str, str]:
    """CH-07: map the executor's generic row keys to the real column names so
    the results table can show 'Revenue (sum)' instead of 'value'."""
    p = parameters or {}
    agg = p.get("aggregation", "sum")
    metric = p.get("metric_column")
    labels: Dict[str, str] = {}
    if metric:
        labels["value"] = f"{metric} ({agg})"
    elif p.get("column"):
        labels["value"] = "Count"
    if p.get("category_column"):
        labels["category"] = p["category_column"]
    if p.get("dimension_column"):
        labels["item"] = p["dimension_column"]
    if p.get("time_column"):
        labels["time"] = p["time_column"]
    if template_type == "period_over_period":
        labels["period"] = "Period"
    if p.get("column"):
        labels.setdefault("category", p["column"])
        labels["bin"] = p["column"]
    sec = p.get("secondary_dimensions") or []
    if p.get("dimension_column") and sec:
        labels["primary"] = p["dimension_column"]
        labels["secondary"] = ", ".join(sec)
    return labels


def _apply_requested_chart_type(plotly_spec: Dict[str, Any],
                                chart_config: Dict[str, Any],
                                requested: Optional[str]) -> None:
    """CH-04d: honor an explicitly requested chart style when the data shape
    allows it (mirrors the frontend _convertTraces rules); otherwise keep the
    default chart and attach a human-readable note. Never fails the query."""
    if not requested or requested == "auto" or requested not in _CONVERTIBLE_TYPES:
        return
    if not plotly_spec or not plotly_spec.get("data"):
        return

    traces = plotly_spec["data"]
    layout = plotly_spec.setdefault("layout", {})

    def note(msg: str) -> None:
        chart_config["chart_type_note"] = msg

    if requested == "pie":
        t = traces[0] if len(traces) == 1 else None
        if t is None:
            note("A pie chart needs a single series — kept the default chart.")
            return
        labels = t.get("labels") or t.get("x")
        values = t.get("values") or t.get("y")
        if not labels or not values or len(labels) > 30:
            note("Pie needs one categorical series with ≤ 30 categories — kept the default chart.")
            return
        plotly_spec["data"] = [{"type": "pie", "labels": list(labels),
                                "values": list(values), "hole": 0.35}]
        layout.pop("xaxis", None); layout.pop("yaxis", None); layout.pop("barmode", None)
        chart_config["chart_type"] = "pie"
        return

    # xy targets: every trace must have (or be convertible to) x and y
    converted = []
    for t in traces:
        t = dict(t)
        if t.get("type") == "pie":
            t["x"] = t.pop("labels", None); t["y"] = t.pop("values", None)
            t.pop("hole", None); t.pop("textinfo", None); t.pop("textposition", None)
        if t.get("x") is None or t.get("y") is None:
            note("This data shape doesn't support that chart type — kept the default chart.")
            return
        t.pop("fill", None); t.pop("orientation", None)
        if requested == "line":    t.update(type="scatter", mode="lines+markers")
        elif requested == "area":  t.update(type="scatter", mode="lines", fill="tozeroy")
        elif requested == "scatter": t.update(type="scatter", mode="markers")
        else:
            t["type"] = "bar"; t.pop("mode", None)
            if requested in ("horizontal_bar", "stacked_horizontal"):
                t["x"], t["y"] = t["y"], t["x"]
                t["orientation"] = "h"
                t.pop("texttemplate", None)
        converted.append(t)

    plotly_spec["data"] = converted
    if requested in ("stacked_bar", "stacked_horizontal"):
        layout["barmode"] = "stack"
    elif requested == "bar" and layout.get("barmode") == "stack":
        layout["barmode"] = "group"
    if requested in ("horizontal_bar", "stacked_horizontal"):
        xax = dict(layout.get("xaxis") or {}); yax = dict(layout.get("yaxis") or {})
        xax_title, yax_title = xax.get("title"), yax.get("title")
        xax["title"], yax["title"] = yax_title, xax_title
        if yax.get("tickformat") and not xax.get("tickformat"):
            xax["tickformat"] = yax.pop("tickformat")
        xax["automargin"] = yax["automargin"] = True
        layout["xaxis"], layout["yaxis"] = xax, yax
    chart_config["chart_type"] = requested


def _finalize_chart(template_type: str, query_result: Dict[str, Any],
                    parameters: Dict[str, Any]):
    """Build chart config + Plotly spec, honor a requested chart type, and
    attach the CH-07 column-label map to the query result."""
    chart_config = ChartFactory.create_chart_config(
        template_type=template_type, query_result=query_result, parameters=parameters,
    )
    plotly_spec = ChartBuilder.build_chart(chart_config)
    _apply_requested_chart_type(plotly_spec, chart_config,
                                (parameters or {}).get("requested_chart_type"))
    query_result["column_labels"] = _column_labels(template_type, parameters)
    return chart_config, plotly_spec


@router.get("/templates", response_model=TemplateListResponse)
async def list_query_templates():
    """
    Get list of all available query templates
    
    Returns:
        List of templates with their parameters
    """
    templates = list_all_templates()
    
    return {
        "templates": templates,
        "count": len(templates)
    }


@router.get("/datasets/{dataset_id}/columns", response_model=DatasetColumnsResponse)
async def get_dataset_columns(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get column information for a dataset
    
    Args:
        dataset_id: ID of dataset
    
    Returns:
        Column names and types
    """
    # Get dataset from database
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == current_user.id
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Load dataset
    file_path = dataset.file_path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset file not found at: {file_path}"
        )
    
    try:
        # Try to load processed dataset first, fall back to original
        df = None
        preprocessor = DataPreprocessor()
        
        # Try processed dataset
        df = preprocessor.get_processed_dataset(dataset_id, current_user.id)
        
        # If processed doesn't exist, load original file
        if df is None:
            print(f"Loading original dataset from: {file_path}")
            file_extension = os.path.splitext(file_path)[1].lower()
            if file_extension not in ('.csv', '.xlsx', '.xls'):
                raise ValueError(f"Unsupported file type: {file_extension}")
            df = read_tabular(file_path)
        
        if df is None or df.empty:
            raise ValueError("Failed to load dataset or dataset is empty")
        
        # Normalize string columns: fix case inconsistencies and typos generically
        df = normalize_string_columns(df)
        
        print(f"Successfully loaded dataset with {len(df)} rows and {len(df.columns)} columns")
        
        # Get column information
        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            category = _detect_column_category(col, df[col])
            columns.append({
                "name": col,
                "dtype": dtype,
                "category": category,
                "unique_count": int(df[col].nunique()),
                "null_count": int(df[col].isnull().sum())
            })
        
        return {
            "dataset_id": dataset_id,
            "columns": columns,
            "column_count": len(columns)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading dataset columns: {str(e)}"
        )


@router.post("/execute", response_model=QueryExecuteResponse)
async def execute_query(
    request: QueryExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a query template on a dataset
    
    Args:
        request: Query execution request with template type, dataset ID, and parameters
    
    Returns:
        Query results, chart configuration, and Plotly specification
    """
    # Validate template type
    template = get_template_by_type(request.template_type)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template type: {request.template_type}"
        )
    
    # Get dataset from database
    dataset = db.query(Dataset).filter(
        Dataset.id == request.dataset_id,
        Dataset.user_id == current_user.id
    ).first()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Load dataset
    file_path = dataset.file_path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset file not found at: {file_path}"
        )
    
    try:
        # Try to load processed dataset first, fall back to original
        df = None
        preprocessor = DataPreprocessor()
        
        # Try processed dataset (CP-21: track whether this is cleaned data)
        df = preprocessor.get_processed_dataset(request.dataset_id, current_user.id)
        data_state = "cleaned"

        # If processed doesn't exist, the dataset hasn't been through the
        # approved cleaning yet — fall back to the raw file with only a light
        # query-time normalization, and tell the client this is RAW data.
        if df is None:
            print(f"Loading original dataset from: {file_path}")
            file_extension = os.path.splitext(file_path)[1].lower()
            if file_extension not in ('.csv', '.xlsx', '.xls'):
                raise ValueError(f"Unsupported file type: {file_extension}")
            df = read_tabular(file_path)
            df = normalize_string_columns(df)
            data_state = "raw"

        if df is None or df.empty:
            raise ValueError("Failed to load dataset or dataset is empty")

        print(f"Successfully loaded dataset with {len(df)} rows and {len(df.columns)} columns")

        # Execute query
        executor = QueryExecutor(df)
        query_result = executor.execute_query(
            template_type=request.template_type,
            parameters=request.parameters
        )
        
        if not query_result.get('success', False):
            return {
                "success": False,
                "message": query_result.get('error', 'Query execution failed'),
                "query_result": query_result
            }
        
        # Chart config + spec (honors requested_chart_type, adds column labels)
        chart_config, plotly_spec = _finalize_chart(
            request.template_type, query_result, request.parameters,
        )

        # Generate insights
        insights = generate_insights(
            template_type=request.template_type,
            query_result=query_result,
            parameters=request.parameters
        )

        # Persist to query history (best-effort — don't fail the response if this errors)
        try:
            crud_history.save_query(
                db=db,
                dataset_id=request.dataset_id,
                user_id=current_user.id,
                template_type=request.template_type,
                parameters=request.parameters,
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": "Query executed successfully",
            "template_type": request.template_type,
            "query_result": query_result,
            "chart_config": chart_config,
            "plotly_spec": plotly_spec,
            "insights": insights,
            "data_state": data_state,
        }

    except Exception as e:
        print(f"Error executing query: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing query: {str(e)}"
        )


@router.post("/natural", response_model=NaturalQueryResponse)
async def execute_natural_query(
    request: NaturalQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute a natural-language query against a dataset.

    The NLP engine classifies the intent, maps tokens to column names, and
    builds the same parameter structure used by /queries/execute — so the
    existing QueryExecutor / ChartFactory / ChartBuilder pipeline is reused
    unchanged.

    Returns the full chart response when the query is unambiguous, or a
    clarification prompt when required parameters cannot be resolved.
    """
    # Verify dataset ownership
    dataset = db.query(Dataset).filter(
        Dataset.id == request.dataset_id,
        Dataset.user_id == current_user.id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    file_path = dataset.file_path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset file not found at: {file_path}",
        )

    try:
        # Load dataset (prefer cleaned version; CP-21 track raw vs cleaned)
        preprocessor = DataPreprocessor()
        df = preprocessor.get_processed_dataset(request.dataset_id, current_user.id)
        data_state = "cleaned"
        if df is None:
            df = read_tabular(file_path)
            df = normalize_string_columns(df)
            data_state = "raw"
        if df is None or df.empty:
            raise ValueError("Dataset is empty")

        # Build column metadata list for the NLP engine
        columns_meta = [
            {"name": col, "category": _detect_column_category(col, df[col])}
            for col in df.columns
        ]

        # Run NLP parsing
        parsed = parse_natural_query(request.query_text, columns_meta)

        intent     = parsed["intent"]
        confidence = parsed["confidence"]
        parameters = parsed["parameters"]
        clarify    = parsed.get("clarification")
        nlp_mode   = parsed.get("nlp_mode", "keyword")

        # Return clarification request — do not execute query yet
        if clarify or not parsed.get("ready"):
            return NaturalQueryResponse(
                success=True,
                message="Clarification needed",
                intent=intent,
                confidence=confidence,
                nlp_mode=nlp_mode,
                detected_parameters=parameters,
                clarification=clarify,
            )

        # Execute via existing pipeline (identical to /execute)
        executor     = QueryExecutor(df)
        query_result = executor.execute_query(template_type=intent, parameters=parameters)

        if not query_result.get("success"):
            return NaturalQueryResponse(
                success=False,
                message=query_result.get("error", "Query execution failed"),
                intent=intent,
                confidence=confidence,
                nlp_mode=nlp_mode,
                detected_parameters=parameters,
            )

        chart_config, plotly_spec = _finalize_chart(intent, query_result, parameters)
        insights    = generate_insights(
            template_type=intent,
            query_result=query_result,
            parameters=parameters,
        )

        # Persist to query history (best-effort)
        try:
            crud_history.save_query(
                db=db,
                dataset_id=request.dataset_id,
                user_id=current_user.id,
                template_type=intent,
                parameters=parameters,
                query_text=request.query_text,
                nlp_mode=nlp_mode,
            )
        except Exception:
            pass

        return NaturalQueryResponse(
            success=True,
            message=f"Query executed ({nlp_mode} mode, confidence={confidence:.0%})",
            intent=intent,
            confidence=confidence,
            nlp_mode=nlp_mode,
            detected_parameters=parameters,
            query_result=query_result,
            chart_config=chart_config,
            plotly_spec=plotly_spec,
            insights=insights,
            data_state=data_state,
        )

    except Exception as exc:
        logger.error("Error in /queries/natural: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Natural query error: {exc}",
        )


# ── Forecast endpoint ─────────────────────────────────────────────────────────

@router.post("/forecast", response_model=ForecastResponse)
async def generate_forecast(
    request: ForecastRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a linear-regression time-series forecast for a trend query.

    Executes the underlying trend_over_time query to obtain the aggregated
    series, then fits an OLS line and returns prediction intervals together
    with ready-to-use Plotly trace dicts that the frontend can overlay on the
    existing chart with Plotly.addTraces().
    """
    from app.services.analytics.forecasting import forecast_linear, build_forecast_plotly_traces

    # ── Load dataset ──────────────────────────────────────────────────────────
    dataset = db.query(Dataset).filter(
        Dataset.id == request.dataset_id,
        Dataset.user_id == current_user.id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    file_path = dataset.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dataset file not found")

    try:
        preprocessor = DataPreprocessor()
        df = preprocessor.get_processed_dataset(request.dataset_id, current_user.id)
        if df is None:
            ext = os.path.splitext(file_path)[1].lower()
            df = read_tabular(file_path)

        if df is None or df.empty:
            raise ValueError("Dataset is empty")

        df = normalize_string_columns(df)

        # ── Execute the trend query to get the aggregated series ──────────────
        executor    = QueryExecutor(df)
        query_result = executor.execute_query("trend_over_time", request.parameters)

        if not query_result.get("success"):
            return ForecastResponse(
                success=False,
                message=query_result.get("error", "Trend query failed"),
            )

        data = query_result.get("data", [])
        if len(data) < 3:
            return ForecastResponse(
                success=False,
                message=f"Need at least 3 data points to forecast (got {len(data)})",
            )

        # ── Run forecasting ───────────────────────────────────────────────────
        result = forecast_linear(
            data=data,
            n_periods=request.n_periods,
            confidence=request.confidence,
        )

        if "error" in result:
            return ForecastResponse(success=False, message=result["error"])

        # ── Build Plotly overlay traces ───────────────────────────────────────
        traces = build_forecast_plotly_traces(data, result)

        return ForecastResponse(
            success=True,
            message=(
                f"Forecast generated: {result['trend']} trend, "
                f"R²={result['r_squared']:.2f}, "
                f"{request.n_periods} periods ahead"
            ),
            fitted=result["fitted"],
            forecast=result["forecast"],
            r_squared=result["r_squared"],
            trend=result["trend"],
            slope_per_period=result["slope_per_period"],
            n_periods=result["n_periods"],
            confidence=result["confidence"],
            method=result["method"],
            plotly_traces=traces,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Forecast error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Forecast error: {exc}")


