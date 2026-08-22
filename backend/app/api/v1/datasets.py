"""
Dataset Management Endpoints
Upload, list, preview, and delete datasets
"""
import os
import json
import math
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np
from app.services.data_processing.io_utils import read_tabular
from app.services.data_processing import config as C

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import limit_upload
from app.models.user import User
from app.models.dataset import Dataset
from app.crud import query_history as crud_history
from app.schemas.dataset import (
    Dataset as DatasetSchema,
    DatasetListItem,
    DatasetPreview,
    DatasetStats,
    DatasetDeleteResponse,
    DatasetCreate,
    ConnectSourceRequest,
    ListTablesRequest,
)
from app.crud import dataset as crud_dataset


def _sanitize(obj):
    """Recursively replace NaN/Inf floats with None for JSON serialisation."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj
from app.services.data_processing.preprocessor import DataPreprocessor
from app.services.data_processing.type_detector import TypeDetector
from app.services.data_processing.cleaner import DataCleaner

router = APIRouter()

# Configuration
UPLOAD_DIR = Path("data/uploads")
PROCESSED_DIR = Path("data/processed")
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Differentiated limits: Excel files carry formatting/formulas/multiple sheets,
# so the same logical table is much heavier and slower to parse than CSV.
MAX_CSV_SIZE   = 50 * 1024 * 1024   # 50 MB
MAX_EXCEL_SIZE = 20 * 1024 * 1024   # 20 MB
MAX_CSV_ROWS   = 500_000            # per file
MAX_EXCEL_ROWS = 200_000            # per sheet

# Magic bytes for content validation (extension alone is spoofable)
_XLSX_MAGIC = b"PK\x03\x04"                      # XLSX = ZIP container
_XLS_MAGIC  = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # XLS = OLE2 compound file


def _validate_content(content: bytes, extension: str) -> Optional[str]:
    """
    Verify the file's bytes match its claimed extension.
    Returns an error message, or None if valid.
    """
    if not content:
        return "File is empty."
    if extension == ".xlsx":
        if not content.startswith(_XLSX_MAGIC):
            return "File content is not a valid XLSX workbook (extension does not match content)."
    elif extension == ".xls":
        if not content.startswith(_XLS_MAGIC):
            return "File content is not a valid XLS workbook (extension does not match content)."
    elif extension == ".csv":
        sample = content[:65536]
        if b"\x00" in sample:
            return "File content is not valid text — CSV files cannot contain binary data."
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample.decode("latin-1")
            except UnicodeDecodeError:
                return "CSV file uses an unsupported text encoding (expected UTF-8 or Latin-1)."
    return None


def get_file_size_str(file_path: str) -> str:
    """Convert file size to human-readable format"""
    try:
        size_bytes = os.path.getsize(file_path)
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    except:
        return "N/A"


def validate_file_extension(filename: str) -> bool:
    """Check if file extension is allowed"""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def parse_dataset_file(file_path: str) -> tuple:
    """
    Parse CSV or Excel file and return DataFrame with metadata
    Returns: (dataframe, row_count, column_count, data_types_dict)
    """
    file_extension = Path(file_path).suffix.lower()
    
    try:
        if file_extension == ".csv":
            df = pd.read_csv(file_path)
        elif file_extension in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")
        
        # Get basic metadata
        row_count = len(df)
        column_count = len(df.columns)
        
        # Detect data types (delegates to the pattern-aware detector)
        data_types = _detect_types(df)

        return df, row_count, column_count, data_types
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {str(e)}"
        )


import re as _re

_EMAIL_RE    = _re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_PHONE_RE    = _re.compile(r"^\+?[\d\s\-().]{7,20}$")
_CURRENCY_RE = _re.compile(r"^[\$£€₹¥]\s?-?[\d,]+(\.\d+)?$|^-?[\d,]+(\.\d+)?\s?[\$£€₹¥]$")
_PERCENT_RE  = _re.compile(r"^-?\d+(\.\d+)?\s?%$")
_ID_NAME_RE  = _re.compile(r"(?:^id$|_id$|^id_|_key$|_code$|_ref$|_no$|number$)", _re.IGNORECASE)


def _detect_types(df: pd.DataFrame) -> dict:
    """
    Per-column type + pattern classification. Pattern rules are generic —
    they sample values and apply regexes, never matching specific column
    names from any particular file.
    """
    data_types = {}
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        sample = series.dropna().astype(str).head(50)
        n_sample = len(sample)

        def _mostly(regex) -> bool:
            if n_sample == 0:
                return False
            return sum(bool(regex.match(v.strip())) for v in sample) / n_sample >= 0.8

        if dtype.startswith('int') or dtype.startswith('float'):
            # All-unique integers or ID-style names are identifiers, not metrics
            non_null = series.dropna()
            if _ID_NAME_RE.search(col) or (
                dtype.startswith('int') and len(non_null) > 1 and non_null.nunique() == len(non_null)
            ):
                data_types[col] = 'identifier'
            else:
                data_types[col] = 'numeric'
        elif pd.api.types.is_datetime64_any_dtype(series):
            data_types[col] = 'datetime'
        elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            if _mostly(_EMAIL_RE):
                data_types[col] = 'email'
            elif _mostly(_CURRENCY_RE):
                data_types[col] = 'currency'
            elif _mostly(_PERCENT_RE):
                data_types[col] = 'percentage'
            elif _mostly(_PHONE_RE) and _ID_NAME_RE.search(col) is None and any(
                c in ''.join(sample.head(5)) for c in '+-() '
            ):
                data_types[col] = 'phone'
            else:
                try:
                    parsed = pd.to_datetime(sample.head(10), errors='coerce')
                    if parsed.notna().mean() > 0.7:
                        data_types[col] = 'datetime'
                    elif series.dropna().nunique() / max(len(series.dropna()), 1) > 0.8:
                        data_types[col] = 'text'          # high-cardinality free text
                    else:
                        data_types[col] = 'categorical'
                except Exception:
                    data_types[col] = 'categorical'
        else:
            data_types[col] = 'other'
    return data_types


def _register_dataframe_as_dataset(
    df: pd.DataFrame,
    original_name: str,
    user_upload_dir: Path,
    current_user: User,
    db: Session,
):
    """
    Persist a DataFrame as a CSV-backed dataset row. Cleaning does NOT run
    here — the caller schedules it as a background task so the HTTP request
    returns immediately (processing_status: 'processing' -> 'ready'/'failed').
    """
    unique_filename = f"{uuid.uuid4()}.csv"
    file_path = user_upload_dir / unique_filename
    df.to_csv(file_path, index=False)

    dataset_create = DatasetCreate(
        user_id=current_user.id,
        filename=unique_filename,
        original_filename=original_name,
        file_path=str(file_path),
        row_count=len(df),
        column_count=len(df.columns),
        data_types_json=json.dumps(_detect_types(df)),
    )
    db_dataset = crud_dataset.create_dataset(db, dataset_create)
    db_dataset.processing_status = 'processing'
    db.commit()
    db.refresh(db_dataset)
    return db_dataset


def _plan_path(dataset_id: int, user_id: int) -> Path:
    return PROCESSED_DIR / f"user_{user_id}" / f"dataset_{dataset_id}_plan.json"


def _analyze_dataset_in_background(dataset_id: int, user_id: int, file_path: str) -> None:
    """
    Background task: ANALYZE the data and store a proposed cleaning plan —
    nothing is applied without the user's approval. Status flow:
    'processing' -> 'review' (plan ready, user decides) or 'failed'.
    Opens its own DB session — the request's session is long gone by now.
    """
    from app.core.database import SessionLocal
    from app.services.data_processing.cleaning_plan import build_plan
    db = SessionLocal()
    try:
        ext = Path(file_path).suffix.lower()
        df = read_tabular(file_path)
        plan = build_plan(df)
        plan['dataset_id'] = dataset_id

        plan_file = _plan_path(dataset_id, user_id)
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(_sanitize(plan), f, default=str)

        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if ds:
            n_ops = len(plan.get('operations', []))
            # No issues found -> data is clean as-is, no review needed
            if n_ops == 0:
                preprocessor = DataPreprocessor()
                preprocessor._save_processed_dataset(df, dataset_id, user_id)
                ds.cleaned_status = True
                ds.processing_status = 'ready'
            else:
                ds.processing_status = 'review'
            db.commit()
        print(f"[Analyze] dataset #{dataset_id}: {len(plan.get('operations', []))} proposed change(s)")
    except Exception as e:
        print(f"[Analyze] dataset #{dataset_id} failed: {e}")
        try:
            ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if ds:
                ds.processing_status = 'failed'
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/", response_model=DatasetSchema, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(limit_upload),
):
    """
    Upload a new dataset (CSV or Excel file).

    - Validates file type by content (magic bytes), not just extension
    - Enforces size limits: CSV 50 MB / 500k rows, Excel 20 MB / 200k rows per sheet
    - Multi-sheet workbooks: every non-empty sheet becomes its own dataset
      (named "workbook.xlsx [SheetName]"); the first is returned, the rest
      appear in the dataset list
    """
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    extension = Path(file.filename).suffix.lower()
    is_excel  = extension in (".xlsx", ".xls")
    max_size  = MAX_EXCEL_SIZE if is_excel else MAX_CSV_SIZE
    max_rows  = MAX_EXCEL_ROWS if is_excel else MAX_CSV_ROWS

    content = await file.read()

    if len(content) > max_size:
        kind = "Excel" if is_excel else "CSV"
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"{kind} file is {len(content) / (1024*1024):.1f} MB — the limit for {kind} "
                f"is {max_size // (1024*1024)} MB. "
                + ("Excel limits are lower because formatting and formulas make files heavier; "
                   "consider exporting to CSV for large tables." if is_excel else
                   "Consider splitting the file or removing unused columns.")
            ),
        )

    content_error = _validate_content(content, extension)
    if content_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=content_error)

    # Everything from here on is blocking I/O + CPU-bound pandas work — for a
    # 20-25MB file this can take several real seconds. Uvicorn runs a single
    # event loop by default, so calling this directly would freeze the ENTIRE
    # server (every user, every endpoint) for that whole duration, not just
    # the uploader's own page. Running it in a worker thread keeps the event
    # loop free to serve other requests while this one file is processed.
    return await run_in_threadpool(
        _upload_dataset_sync, content, extension, is_excel, max_rows,
        file.filename, current_user, db, background_tasks,
    )


def _upload_dataset_sync(
    content: bytes, extension: str, is_excel: bool, max_rows: int,
    filename: str, current_user: User, db: Session, background_tasks: BackgroundTasks,
):
    """Synchronous body of upload_dataset — runs in a thread pool, see caller."""
    user_upload_dir = UPLOAD_DIR / f"user_{current_user.id}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    # Persist the original file for provenance
    original_path = user_upload_dir / f"{uuid.uuid4()}{extension}"
    try:
        with open(original_path, "wb") as buffer:
            buffer.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    try:
        if is_excel:
            # Multi-sheet support: one dataset per non-empty sheet
            xls = pd.ExcelFile(original_path)
            sheet_frames = []
            for sheet_name in xls.sheet_names:
                sdf = xls.parse(sheet_name)
                if sdf.empty or len(sdf.columns) == 0:
                    continue
                if len(sdf) > max_rows:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"Sheet '{sheet_name}' has {len(sdf):,} rows — the per-sheet limit "
                            f"for Excel is {max_rows:,}. Export it to CSV (limit {MAX_CSV_ROWS:,} rows)."
                        ),
                    )
                sheet_frames.append((sheet_name, sdf))

            if not sheet_frames:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Workbook contains no non-empty sheets.")

            created = []
            multi = len(sheet_frames) > 1
            for sheet_name, sdf in sheet_frames:
                name = f"{filename} [{sheet_name}]" if multi else filename
                ds = _register_dataframe_as_dataset(sdf, name, user_upload_dir, current_user, db)
                # Cleaning runs after the response is sent — upload returns instantly
                background_tasks.add_task(
                    _analyze_dataset_in_background, ds.id, current_user.id, ds.file_path)
                created.append(ds)
            return created[0]

        # CSV path
        df = read_tabular(original_path)
        if len(df) > max_rows:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File has {len(df):,} rows — the CSV limit is {max_rows:,} rows.",
            )
        if df.empty or len(df.columns) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File contains no data.")
        ds = _register_dataframe_as_dataset(df, filename, user_upload_dir, current_user, db)
        background_tasks.add_task(
            _analyze_dataset_in_background, ds.id, current_user.id, ds.file_path)
        return ds

    except HTTPException:
        if original_path.exists():
            original_path.unlink()
        raise
    except Exception as e:
        if original_path.exists():
            original_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {str(e)}"
        )


@router.get("/", response_model=List[DatasetListItem])
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """
    Get list of all datasets for the current user
    """
    datasets = crud_dataset.get_datasets_by_user(db, current_user.id, skip, limit)
    
    # Add file size to each dataset
    result = []
    for dataset in datasets:
        dataset_dict = {
            "id": dataset.id,
            "filename": dataset.filename,
            "original_filename": dataset.original_filename,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "upload_date": dataset.upload_date,
            "cleaned_status": dataset.cleaned_status,
            "processing_status": getattr(dataset, "processing_status", None) or "ready",
            "file_size": get_file_size_str(dataset.file_path),
            "source_type": getattr(dataset, "source_type", None) or "upload",
            "refresh_interval_minutes": getattr(dataset, "refresh_interval_minutes", None),
            "last_refreshed": getattr(dataset, "last_refreshed", None),
            "ingest_token": getattr(dataset, "ingest_token", None),
            "last_push_at": getattr(dataset, "last_push_at", None),
        }
        result.append(DatasetListItem(**dataset_dict))
    
    return result


@router.get("/stats", response_model=DatasetStats)
def get_dataset_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics about user's datasets
    """
    datasets = crud_dataset.get_datasets_by_user(db, current_user.id)
    
    total_datasets = len(datasets)
    total_rows = sum(d.row_count for d in datasets)
    total_columns = sum(d.column_count for d in datasets)
    
    # Calculate total storage
    total_bytes = sum(os.path.getsize(d.file_path) if os.path.exists(d.file_path) else 0 for d in datasets)
    total_storage = f"{total_bytes / (1024 * 1024):.1f} MB"
    
    return DatasetStats(
        total_datasets=total_datasets,
        total_rows=total_rows,
        total_columns=total_columns,
        total_storage=total_storage
    )


# ── External data connector helpers + endpoints ──────────────────────────────

def _register_dataframe(
    df: pd.DataFrame,
    original_name: str,
    current_user: "User",
    db,
    background_tasks: "BackgroundTasks" = None,
) -> "DatasetSchema":
    """
    Register a DataFrame from an external connector as a raw dataset (CP-08).

    Connectors go through the SAME analyze-first consent flow as file uploads:
    the raw data is registered with status 'processing', then the cleaning plan
    is built in the background and the dataset flips to 'review'. NOTHING is
    value-level cleaned until the user approves the plan — identical to uploads.
    """
    user_upload_dir = UPLOAD_DIR / f"user_{current_user.id}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    db_dataset = _register_dataframe_as_dataset(
        df, original_name, user_upload_dir, current_user, db)

    if background_tasks is not None:
        background_tasks.add_task(
            _analyze_dataset_in_background, db_dataset.id, current_user.id, db_dataset.file_path)
    else:
        # Synchronous fallback (kept for callers without a request scope)
        _analyze_dataset_in_background(db_dataset.id, current_user.id, db_dataset.file_path)
        db.refresh(db_dataset)

    return db_dataset


@router.post("/connect/tables")
async def list_connection_tables(
    body: ListTablesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the list of table names for a MySQL or Postgres connection.
    No data is imported; this is used to populate the table-picker dropdown
    in the frontend before the user confirms which table to import.
    """
    from app.services.integrations.db_connector import list_tables

    try:
        tables = list_tables(
            source_type=body.source_type,
            host=body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            database=body.database,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error listing tables: {exc}",
        )

    return {"tables": tables}


@router.post("/connect", response_model=DatasetSchema, status_code=status.HTTP_201_CREATED)
async def connect_data_source(
    body: ConnectSourceRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import data from an external source and register it as a dataset.

    Supported source_type values:
    - **google_sheets** — provide `url` (sheet must be publicly shared)
    - **mysql**         — provide `host`, `port`, `username`, `password`, `database`, `table_name`
    - **postgres**      — same as mysql

    The imported data is registered raw, then analyzed in the background exactly
    like a file upload (CP-08): the dataset lands in 'review' status with a
    cleaning plan and nothing value-level is applied until the user approves.
    """
    try:
        if body.source_type == "google_sheets":
            if not body.url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="url is required for source_type 'google_sheets'",
                )
            from app.services.integrations.google_sheets import fetch_google_sheet
            df = fetch_google_sheet(body.url)
            # Derive a sensible display name from the URL or user-supplied name
            display_name = (
                body.dataset_name.strip()
                if body.dataset_name and body.dataset_name.strip()
                else "google_sheet.csv"
            )

        elif body.source_type in ("mysql", "postgres"):
            missing = [
                f for f in ("host", "port", "username", "password", "database", "table_name")
                if not getattr(body, f, None)
            ]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Missing required fields for database connection: {missing}",
                )
            from app.services.integrations.db_connector import fetch_table
            df = fetch_table(
                source_type=body.source_type,
                host=body.host,
                port=body.port,
                username=body.username,
                password=body.password,
                database=body.database,
                table_name=body.table_name,
            )
            display_name = (
                body.dataset_name.strip()
                if body.dataset_name and body.dataset_name.strip()
                else f"{body.database}.{body.table_name}.csv"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown source_type '{body.source_type}'",
            )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch data from external source: {exc}",
        )

    try:
        # Register raw first (status 'processing'); set source metadata BEFORE
        # scheduling the background analyze so the two don't race on the row.
        user_upload_dir = UPLOAD_DIR / f"user_{current_user.id}"
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        db_dataset = _register_dataframe_as_dataset(
            df, display_name, user_upload_dir, current_user, db)

        # Google Sheets: remember the source so the dataset can auto-refresh.
        # The URL is a public share link — safe to persist (no credentials).
        if body.source_type == "google_sheets":
            db_dataset.source_type = "google_sheets"
            db_dataset.source_url = body.url
            db_dataset.refresh_interval_minutes = body.refresh_interval_minutes
            db_dataset.last_refreshed = datetime.utcnow()
            db_dataset.ingest_token = uuid.uuid4().hex   # secret for the push webhook
            db.commit()
            db.refresh(db_dataset)

        # Analyze-first: build the plan in the background → 'review' status
        background_tasks.add_task(
            _analyze_dataset_in_background, db_dataset.id, current_user.id, db_dataset.file_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data imported but could not be saved: {exc}",
        )

    return db_dataset


# Per-token limiter: a chatty Apps Script trigger can't hammer the fetch path
from app.core.rate_limiter import SlidingWindowLimiter
_ingest_limiter = SlidingWindowLimiter(max_requests=6, window_seconds=60)


@router.post("/ingest/{token}", status_code=status.HTTP_202_ACCEPTED)
def ingest_push(
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Push webhook for near-real-time updates. A Google Apps Script `onChange`
    trigger in the source sheet calls this the moment the sheet is edited;
    we re-fetch the data in the background. No auth header — the unguessable
    token (128-bit) IS the credential, and it can only trigger a re-fetch of
    the one dataset it belongs to.
    """
    dataset = db.query(Dataset).filter(Dataset.ingest_token == token).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Unknown token")

    allowed, retry_after = _ingest_limiter.check(token)
    if not allowed:
        # Burst of edits — one refresh is already inbound; that's enough
        return {"accepted": False, "detail": f"Cooling down ({retry_after}s) — a refresh is already queued"}

    # CH-10: record that live push is actually working for this dataset,
    # so the UI can badge it "⚡ Live" with confidence.
    try:
        dataset.last_push_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    def _do_refresh(dataset_id: int):
        from app.core.database import SessionLocal
        from app.services.data_refresh import refresh_dataset
        session = SessionLocal()
        try:
            ds = session.query(Dataset).filter(Dataset.id == dataset_id).first()
            if ds:
                refresh_dataset(session, ds)
        finally:
            session.close()

    background_tasks.add_task(_do_refresh, dataset.id)
    return {"accepted": True, "detail": "Refresh queued"}


@router.get("/meta/last-updated")
def datasets_last_updated(
    ids: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cheap change-detection poll for live dashboards: returns each dataset's
    last-refreshed timestamp. The dashboard compares against what it last
    rendered and re-queries ONLY when data actually changed.
    """
    try:
        id_list = [int(i) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be comma-separated integers")

    rows = db.query(Dataset).filter(
        Dataset.id.in_(id_list),
        Dataset.user_id == current_user.id,
    ).all()
    # Timestamps are naive-UTC in the DB — suffix 'Z' so browsers parse them
    # as UTC instead of local time (comparison skew otherwise)
    return {
        str(d.id): (d.last_refreshed or d.upload_date).isoformat() + "Z"
        for d in rows
    }


@router.post("/{dataset_id}/refresh")
def refresh_dataset_now(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually re-fetch a connected dataset from its source right now."""
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.source_type != "google_sheets" or not dataset.source_url:
        raise HTTPException(
            status_code=400,
            detail="This dataset was uploaded as a file — it has no live source to refresh from.",
        )
    from app.services.data_refresh import refresh_dataset
    ok = refresh_dataset(db, dataset)
    if not ok:
        raise HTTPException(status_code=502, detail="Could not fetch the latest data from the source.")
    return {
        "success": True,
        "message": f"Refreshed from source — {dataset.row_count:,} rows",
        "row_count": dataset.row_count,
        "last_refreshed": dataset.last_refreshed,
    }


@router.get("/{dataset_id}", response_model=DatasetSchema)
def get_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific dataset
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    return dataset


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
def preview_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get preview of dataset (first 100 rows + metadata)
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check if file exists
    if not os.path.exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found on disk"
        )
    
    # Read and preview data
    try:
        df, _, _, data_types = parse_dataset_file(dataset.file_path)
        
        # Get first 100 rows
        # Use to_json then parse back — pandas converts NaN → null properly
        # (df.where(notna, None) doesn't work because None→NaN in float columns)
        preview_df = df.head(100)
        preview_rows = json.loads(preview_df.to_json(orient='records'))
        column_names = df.columns.tolist()
        
        # Add data quality analysis
        preprocessor = DataPreprocessor()
        analysis = preprocessor.analyze_only(dataset.file_path)
        
        # Build enhanced response with quality info
        response_data = {
            "id": dataset.id,
            "filename": dataset.filename,
            "original_filename": dataset.original_filename,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "upload_date": dataset.upload_date,
            "data_types": data_types,
            "preview_rows": preview_rows,
            "column_names": column_names
        }
        
        # Add data quality info if analysis succeeded
        if analysis.get('success'):
            response_data["data_quality"] = analysis.get('data_quality')
        
        return response_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview dataset: {str(e)}"
        )


@router.get("/{dataset_id}/cleaning-plan")
def get_cleaning_plan(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dry-run the cleaning pipeline on the ORIGINAL file and return the proposed
    operations with cell-level examples — nothing is modified. The user reviews,
    unchecks what they don't want, optionally adjusts via chat, then POSTs the
    approved plan to /cleaning-apply.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=404, detail="Dataset file not found")

    try:
        from app.services.data_processing.cleaning_plan import build_plan, load_policy

        # Serve the plan computed at upload time when it's still fresh
        plan = None
        plan_file = _plan_path(dataset_id, current_user.id)
        if plan_file.exists() and plan_file.stat().st_mtime >= os.path.getmtime(dataset.file_path):
            with open(plan_file, encoding="utf-8") as f:
                plan = json.load(f)
        if plan is None:
            df = read_tabular(dataset.file_path)
            plan = build_plan(df)
            plan["dataset_id"] = dataset_id
            plan = _sanitize(plan)
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(plan, f, default=str)

        # CP-11: include the previously-approved policy so the UI can mark ops
        # Applied / Skipped / New and pre-select from the last decision
        try:
            pre = DataPreprocessor()
            policy = load_policy(str(pre.processed_dir), dataset_id, current_user.id)
            if policy:
                plan["applied_policy"] = policy
        except Exception:
            pass
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build cleaning plan: {e}")


@router.post("/{dataset_id}/cleaning-apply")
def apply_cleaning_plan_endpoint(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Apply an approved cleaning plan.
    Body: { "plan": <plan from /cleaning-plan>,
            "selected_ids": [...],
            "overrides": { op_id: {"action": "fill_zero"|"fill_value"|"drop_rows", "value": ...} } }
    Replaces the processed dataset; the original file is never touched.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=404, detail="Dataset file not found")

    plan = body.get("plan")
    selected_ids = body.get("selected_ids", [])
    overrides = body.get("overrides", {})
    if not plan or not isinstance(selected_ids, list):
        raise HTTPException(status_code=400, detail="Body must include 'plan' and 'selected_ids'")

    try:
        from app.services.data_processing.cleaning_plan import apply_plan, save_policy
        df = read_tabular(dataset.file_path)

        cleaned, actions, report = apply_plan(df, plan, selected_ids, overrides)

        # Persist as the processed dataset (original stays untouched);
        # writes Parquet and warms the DataFrame cache
        preprocessor = DataPreprocessor()
        preprocessor._save_processed_dataset(cleaned, dataset_id, current_user.id)

        # CP-05: remember the user's approved decisions so live refreshes and
        # scheduled reports reproduce them instead of reverting to auto defaults
        try:
            save_policy(str(preprocessor.processed_dir), dataset_id, current_user.id,
                        selected_ids, overrides, plan)
        except Exception as pe:
            print(f"[cleaning-apply] could not save policy: {pe}")

        # Persist the applied actions + null reconciliation into metadata so the
        # report page can show what changed
        try:
            meta = preprocessor.get_metadata(dataset_id, current_user.id) or {}
            meta['applied_cleaning'] = {
                'applied_at': datetime.utcnow().isoformat(),
                'actions': actions,
                'applied_ops': report.get('applied_ops', []),
                'null_reconciliation': report.get('null_reconciliation', {}),
                'manual_edits': report.get('manual_edits', {}),
                'rows': len(cleaned),
                'columns': len(cleaned.columns),
                # CH-19: an empty selection is a deliberate "use raw data" choice
                'policy': 'raw_by_choice' if not selected_ids else 'reviewed',
            }

            # This interactive flow used to only write 'applied_cleaning' —
            # the Cleaning Report page's KPI cards, Operations Log and
            # Column Analysis all read type_detection/data_quality/
            # cleaning_report, which only the OLD bulk /process endpoint
            # ever populated. Any dataset cleaned exclusively through Review
            # Cleaning (Highlight Issues -> apply) showed those as blank/0.
            # Compute and store the same fields here too.
            try:
                from app.services.data_processing.cleaner import DataCleaner
                from app.services.data_processing.type_detector import TypeDetector

                type_map = (plan.get("summary") or {}).get("type_map") or {}
                if not type_map:
                    type_map = TypeDetector.detect_all_types(df)

                actions_taken = {
                    'interactive_cleaning': actions,
                    'null_reconciliation': report.get('null_reconciliation', {}),
                    'manual_edits': report.get('manual_edits', {}),
                }
                cleaning_report_full = DataCleaner.generate_cleaning_report(
                    df, cleaned, type_map, actions_taken
                )

                meta['original_file'] = dataset.file_path
                meta['original_shape'] = {'rows': len(df), 'columns': len(df.columns)}
                meta['cleaned_shape'] = {'rows': len(cleaned), 'columns': len(cleaned.columns)}
                meta['type_detection'] = {
                    'type_map': type_map,
                    'type_statistics': TypeDetector.get_type_statistics(df, type_map),
                }
                meta['data_quality'] = {
                    'missing_values': DataCleaner.analyze_missing_values(df),
                    'duplicates': DataCleaner.analyze_duplicates(df),
                    'outliers': DataCleaner.detect_outliers(df, type_map),
                }
                meta['cleaning_report'] = cleaning_report_full
                meta['column_names'] = cleaned.columns.tolist()
            except Exception as ke:
                print(f"[cleaning-apply] could not build report KPIs: {ke}")

            preprocessor._save_metadata(meta, dataset_id, current_user.id)
        except Exception as me:
            print(f"[cleaning-apply] could not save metadata: {me}")

        dataset.cleaned_status = True
        dataset.processing_status = 'ready'
        dataset.row_count = len(cleaned)
        dataset.column_count = len(cleaned.columns)
        # Re-cleaning changes the data — bump the change stamp so open
        # dashboards notice and re-query
        dataset.last_refreshed = datetime.utcnow()
        db.commit()

        return _sanitize({
            "success": True,
            "message": f"Applied {len(actions)} operation group(s)",
            "actions": actions,
            "null_reconciliation": report.get('null_reconciliation', {}),
            "rows": len(cleaned),
            "columns": len(cleaned.columns),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply cleaning plan: {e}")


@router.get("/{dataset_id}/cells")
def get_op_affected_cells(
    dataset_id: int,
    op_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    CH-19: the cells an operation would touch, for the manual-fix editor.
    Row indices refer to the ORIGINAL file (what the review examples show).
    Derivable op kinds get a full (capped) list; anything else returns the
    op's stored examples.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    plan_file = _plan_path(dataset_id, current_user.id)
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="No cleaning plan for this dataset")
    with open(plan_file, "r", encoding="utf-8") as fh:
        plan = json.load(fh)
    plan = plan.get("plan", plan)
    op = next((o for o in plan.get("operations", []) if o["id"] == op_id), None)
    if op is None:
        raise HTTPException(status_code=404, detail="Operation not found in the plan")

    limit = max(1, min(limit, 200))
    cells = [dict(e) for e in (op.get("examples") or [])]

    col = op.get("column")
    try:
        df = read_tabular(dataset.file_path)
    except Exception:
        df = None

    if df is not None and col in getattr(df, "columns", []):
        from app.services.data_processing.type_detector import parse_numeric_series
        seen = {(c.get("row"), c.get("column")) for c in cells}

        def add(mask, values=None):
            for i in df.index[mask]:
                if len(cells) >= limit:
                    return
                key = (int(i), col)
                if key in seen:
                    continue
                seen.add(key)
                cells.append({"row": int(i), "column": col,
                              "from": None if pd.isna(df.at[i, col]) else str(df.at[i, col]),
                              "to": None})

        if op_id.startswith(("missing.", "residual.")):
            add(df[col].isna())
            if op_id.startswith("residual.") and len(cells) < limit:
                parsed, _info = parse_numeric_series(df[col])
                add(parsed.isna() & df[col].notna())
        elif op_id.startswith("normalize."):
            variants = {m["from"] for m in op.get("mappings", [])}
            if variants:
                add(df[col].astype(str).isin(variants))

    return {"op_id": op_id, "column": col, "cells": cells[:limit],
            "total_affected": op.get("affected_count", len(cells))}


@router.get("/{dataset_id}/data")
def get_dataset_data(
    dataset_id: int,
    page: int = 1,
    page_size: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full dataset contents, server-side paginated (max 500 rows/page) so the
    whole sheet can be browsed without ever shipping the full file to the browser.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    if not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    page = max(1, page)
    page_size = min(max(10, page_size), 500)

    try:
        preprocessor = DataPreprocessor()
        processed_df = preprocessor.get_processed_dataset(dataset_id, current_user.id)
        # Row-level edits (cell-chat editor) are only safe when the rows shown
        # are indexed the same way as the ORIGINAL file — i.e. no cleaning has
        # reindexed/dropped rows. Once a cleaned copy exists we still show it
        # (that's the usable data), but disable in-place editing on it rather
        # than risk writing an edit to the wrong row.
        editable = processed_df is None
        df = processed_df if processed_df is not None else read_tabular(dataset.file_path)

        total_rows = len(df)
        start = (page - 1) * page_size
        page_df = df.iloc[start:start + page_size]
        rows = json.loads(page_df.to_json(orient="records"))
        row_indices = [int(i) for i in page_df.index] if editable else []

        return _sanitize({
            "dataset_id": dataset_id,
            "columns": list(df.columns),
            "rows": rows,
            "row_indices": row_indices,
            "editable": editable,
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": max(1, -(-total_rows // page_size)),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")


def _compute_quality_issues(df: pd.DataFrame, page_df: pd.DataFrame, plan: Optional[Dict[str, Any]]):
    """
    Shared cell/row/column issue detection — used by both /data-quality
    (against the ORIGINAL file) and /cleaned-preview (against the CLEANED
    file, to surface whatever the pipeline couldn't/didn't fix). `df` is the
    full dataframe (for whole-file context like duplicates), `page_df` the
    slice actually being returned to the client.

    Returns (issues, row_issues_list, column_notices).
    """
    from app.services.data_processing.cleaner import DataCleaner
    from app.services.data_processing.type_detector import parse_numeric_series, TypeDetector

    row_indices_set = set(int(i) for i in page_df.index)

    def _is_text(s):
        return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)

    issues = []
    row_issues = {}  # row_index -> reason, for whole-row structural problems
    column_notices = []  # column-level (not per-cell) quality/sanitation notices

    def add_issue(row_i, col, reason, tier="fix"):
        # tier "fix" (amber) = cleaning will change this cell.
        # tier "review" (purple) = flagged for the user's attention —
        # negative values, statistical outliers, cross-column mismatches,
        # out-of-range dates — cleaning does NOT auto-change these.
        if row_i in row_indices_set:
            issues.append({"row": int(row_i), "column": col, "reason": reason, "tier": tier})

    def add_row_issue(row_i, reason):
        if row_i in row_indices_set and row_i not in row_issues:
            row_issues[row_i] = reason

    # ── Universal checks (independent of any stored plan) ────────────────

    # Missing/blank cells
    for col in df.columns:
        na_mask = page_df[col].isna()
        for i in page_df.index[na_mask]:
            add_issue(int(i), str(col), "Missing value")

    # Stray/invisible whitespace (sanitation.whitespace)
    for col in df.columns:
        if not _is_text(df[col]):
            continue
        raw = page_df[col]
        cleaned = (raw.astype(str)
                   .str.replace('\xa0', ' ', regex=False)
                   .str.replace('​', '', regex=False)
                   .str.replace(r'\s{2,}', ' ', regex=True)
                   .str.strip())
        changed = (cleaned != raw.astype(str)) & raw.notna()
        for i in page_df.index[changed]:
            add_issue(int(i), str(col), "Extra or invisible whitespace")

    # Placeholder/sentinel values that count as missing (sanitation.sentinels)
    for col in df.columns:
        if not _is_text(df[col]):
            continue
        mask = (page_df[col].astype(str).str.strip().str.lower()
                .isin(DataCleaner.MISSING_SENTINELS)) & page_df[col].notna()
        for i in page_df.index[mask]:
            add_issue(int(i), str(col), "Placeholder text — treated as missing")

    # Structural row problems (computed on the whole file, sliced to this page)
    header_mask = DataCleaner.detect_header_rows(df)
    for i in page_df.index[header_mask.loc[page_df.index]]:
        add_row_issue(int(i), "Duplicate header row (from a stitched export)")

    empty_mask = df.isna().all(axis=1)
    for i in page_df.index[empty_mask.loc[page_df.index]]:
        add_row_issue(int(i), "Completely empty row")

    agg_mask = DataCleaner.detect_aggregate_rows(df)
    for i in page_df.index[agg_mask.loc[page_df.index]]:
        add_row_issue(int(i), "Summary row (Total/Subtotal) — would double-count in charts")

    dup_mask = df.duplicated(keep='first')
    for i in page_df.index[dup_mask.loc[page_df.index]]:
        add_row_issue(int(i), "Exact duplicate of an earlier row")

    # ── Plan-driven checks (need a stored cleaning plan) ──────────────────
    numeric_cols = []  # columns the plan confirms are numeric — reused below
    if plan:
        for op in plan.get("operations", []):
            op_id = op.get("id", "")
            col = op.get("column")

            if op_id.startswith("normalize.") and col in df.columns:
                variants = {m["from"] for m in op.get("mappings", [])}
                if variants:
                    mask = page_df[col].astype(str).isin(variants)
                    for i in page_df.index[mask]:
                        add_issue(int(i), str(col),
                                  f"Inconsistent value — will be normalized ({op.get('description', '')})")

            elif op_id.startswith("convert.numeric.") and col in df.columns:
                numeric_cols.append(col)
                parsed, _info = parse_numeric_series(page_df[col])
                fail_mask = parsed.isna() & page_df[col].notna()
                for i in page_df.index[fail_mask]:
                    add_issue(int(i), str(col), "Doesn't look like a number")

                # Successfully-parsed but non-plain-numeric text (currency
                # symbols, thousands separators, % signs, accounting
                # parens) — cleaning WILL rewrite these, so the user
                # should see it coming, not just the outright failures.
                raw_str = page_df[col].astype(str).str.strip()
                reformatted = (parsed.notna() & page_df[col].notna()
                               & ~raw_str.str.fullmatch(r'-?\d+(\.\d+)?'))
                for i in page_df.index[reformatted]:
                    add_issue(int(i), str(col), "Will be reformatted to a plain number (currency/%/separator)")

            elif op_id.startswith("convert.datetime.") and col in df.columns:
                parsed = pd.to_datetime(page_df[col], errors="coerce")
                fail_mask = parsed.isna() & page_df[col].notna()
                for i in page_df.index[fail_mask]:
                    add_issue(int(i), str(col), "Doesn't look like a date")

                # Parses fine, but not already in a consistent ISO format
                # (e.g. "01-08-25" alongside "2025-01-13" in the same
                # column) — cleaning WILL rewrite these too, silently,
                # so surface it the same way currency reformatting is.
                raw_str = page_df[col].astype(str).str.strip()
                reformatted = (parsed.notna() & page_df[col].notna()
                               & ~raw_str.str.fullmatch(r'\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?'))
                for i in page_df.index[reformatted]:
                    add_issue(int(i), str(col), "Inconsistent date format — will be standardized")

            elif op_id.startswith("convert.serial_date.") and col in df.columns:
                # The plan already confirmed this column looks like Excel
                # date serials; flag the in-range values on this page.
                numeric = pd.to_numeric(page_df[col], errors="coerce")
                mask = (numeric.notna()
                        & (numeric >= TypeDetector.EXCEL_SERIAL_MIN)
                        & (numeric <= TypeDetector.EXCEL_SERIAL_MAX))
                for i in page_df.index[mask]:
                    add_issue(int(i), str(col), "Looks like an Excel date serial, not a plain number")

            elif op_id.startswith("quality.date_range."):
                # Recompute directly (row-accurate for THIS page, not
                # capped like the plan's stored examples) rather than
                # trusting op["examples"].
                if col not in df.columns:
                    continue
                s = page_df[col]
                dt = s if pd.api.types.is_datetime64_any_dtype(s) else pd.to_datetime(s, errors="coerce", format="mixed")
                today = pd.Timestamp.today().normalize()
                floor = pd.Timestamp("1990-01-01")
                mask = dt.notna() & ((dt > today) | (dt < floor))
                for i in page_df.index[mask]:
                    add_issue(int(i), str(col), "Date is in the future or before 1990 — likely a typo", tier="review")

            elif op_id == "quality.qty_price_amount" and col in df.columns:
                # op["column"] is the amount column; re-derive qty/price
                # column names the same way validations.py does.
                try:
                    from app.services.data_processing.validations import _QTY_RE, _PRICE_RE
                    qty_c = next((c for c in df.columns if _QTY_RE.search(str(c))), None)
                    price_c = next((c for c in df.columns if _PRICE_RE.search(str(c))), None)
                    if qty_c and price_c:
                        q, _ = parse_numeric_series(page_df[qty_c])
                        p, _ = parse_numeric_series(page_df[price_c])
                        a, _ = parse_numeric_series(page_df[col])
                        expected = q * p
                        both = expected.notna() & a.notna() & (a.abs() > 0)
                        rel_err = (expected - a).abs() / a.abs().where(a.abs() > 0, np.nan)
                        mask = both & (rel_err > 0.01)
                        for i in page_df.index[mask]:
                            add_issue(int(i), str(col),
                                      f"{qty_c} × {price_c} ≠ {col} — possible pricing/entry error", tier="review")
                except Exception:
                    pass

            elif op.get("category") in ("quality",) or op_id.startswith("sanitation.drop_column."):
                # Remaining column-wide notices (mixed currency/scale,
                # conflicting keys, mostly-empty column) aren't a single
                # cell's fault — surface once instead of per-cell.
                if col:
                    column_notices.append({
                        "column": col, "title": op.get("title", op_id),
                        "description": op.get("description", ""),
                    })

    # ── Negative values + statistical outliers (flagged, NOT auto-fixed
    #    by cleaning — DataCleaner.detect_outliers is explicitly flag-only,
    #    and there's no "negative value" cleaning step at all) ───────────
    # UNION, not "only if empty" — a column that's ALREADY plain numeric
    # (e.g. Quantity, no $ signs) never gets a convert.numeric.* op, so
    # it would otherwise be silently skipped just because some OTHER
    # column (e.g. Unit_Price) needed conversion and populated the list.
    numeric_cols = set(numeric_cols) | {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    for col in numeric_cols:
        if col not in df.columns:
            continue
        full_parsed, _info = parse_numeric_series(df[col])

        neg_mask = full_parsed.loc[page_df.index] < 0
        for i in page_df.index[neg_mask.fillna(False)]:
            add_issue(int(i), str(col), f"Negative value in \"{col}\" — verify this is expected", tier="review")

        series = full_parsed.dropna()
        if len(series) >= C.OUTLIER_MIN_SAMPLE:
            try:
                skew = float(series.skew())
            except Exception:
                skew = 0.0
            if abs(skew) > C.OUTLIER_SKEW_THRESHOLD:
                mask, _meta = (DataCleaner._log_iqr_mask(series) if (series > 0).all()
                               else DataCleaner._mad_mask(series))
            else:
                mask, _meta = DataCleaner._iqr_mask(series)
            if mask is not None:
                outlier_idx = set(series.index[mask]) & row_indices_set
                for i in outlier_idx:
                    add_issue(int(i), str(col), f"Statistical outlier for \"{col}\"", tier="review")

    return issues, [{"row": r, "reason": reason} for r, reason in row_issues.items()], column_notices


def _load_or_build_plan(df: pd.DataFrame, dataset_id: int, user_id: int):
    """Stored plan if fresh, else built in-memory (never persisted here)."""
    plan = None
    try:
        plan_file = _plan_path(dataset_id, user_id)
        if plan_file.exists():
            with open(plan_file, "r", encoding="utf-8") as fh:
                plan = json.load(fh)
            plan = plan.get("plan", plan)
    except Exception:
        plan = None
    if plan is None:
        try:
            from app.services.data_processing.cleaning_plan import build_plan
            plan = build_plan(df)
        except Exception:
            plan = None
    return plan


@router.get("/{dataset_id}/data-quality")
def get_dataset_data_quality(
    dataset_id: int,
    page: int = 1,
    page_size: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Same page slice as /data, but against the ORIGINAL (pre-cleaning) file,
    plus a list of problem cells in that slice — for the "highlight issues"
    browse view next to Browse Full Data. Reuses the stored cleaning plan's
    operations (same detection the cleaning-review screen uses) so the
    highlights always match what "Review Cleaning" would actually fix.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    if not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    page = max(1, page)
    page_size = min(max(10, page_size), 500)

    try:
        df = read_tabular(dataset.file_path)
        total_rows = len(df)
        start = (page - 1) * page_size
        page_df = df.iloc[start:start + page_size]
        rows = json.loads(page_df.to_json(orient="records"))
        row_indices = [int(i) for i in page_df.index]

        plan = _load_or_build_plan(df, dataset_id, current_user.id)
        issues, row_issues, column_notices = _compute_quality_issues(df, page_df, plan)

        return _sanitize({
            "dataset_id": dataset_id,
            "columns": list(df.columns),
            "rows": rows,
            "row_indices": row_indices,
            "editable": True,
            "issues": issues,
            "row_issues": row_issues,
            "column_notices": column_notices if page == 1 else [],  # avoid repeating every page
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": max(1, -(-total_rows // page_size)),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")


def _load_source_df(dataset: Dataset, source: str):
    """
    "raw" -> the original uploaded file (existing behaviour everywhere else).
    "cleaned" -> the processed/cleaned copy — 404s with a clear message if
    cleaning hasn't been run yet, since there's nothing to review/edit there.
    """
    if source == "cleaned":
        preprocessor = DataPreprocessor()
        df = preprocessor.get_processed_dataset(dataset.id, dataset.user_id)
        if df is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail="No cleaned copy exists yet — run Review Cleaning first.")
        return df
    return read_tabular(dataset.file_path)


def _coerce_cell_edit(df: pd.DataFrame, col: str, val: Any) -> Any:
    """
    Coerce a raw edit value (always a string or None from the JSON request
    body) into something assignable to this column without raising.

    pandas 2.x/3.x's `.at` setter validates dtype strictly and no longer
    silently upcasts like older pandas did — writing "1200.0" (a str) into a
    float64 column, or None into an int64 column (which can't hold NaN),
    raises instead of "just working". This widens the column's dtype in
    place when needed (float64 for numbers going nullable, object for text
    that doesn't fit the column's type) so any user-entered value can always
    be saved, matching the editor's promise that edits just apply.
    """
    if val is None:
        if pd.api.types.is_integer_dtype(df[col]):
            df[col] = df[col].astype("float64")
        elif not pd.api.types.is_float_dtype(df[col]) and not pd.api.types.is_object_dtype(df[col]) \
                and not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].astype(object)
        return None

    dtype = df[col].dtype

    if pd.api.types.is_bool_dtype(dtype):
        if isinstance(val, str):
            low = val.strip().lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
        return bool(val)

    if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_float_dtype(dtype):
        try:
            num = float(val)
        except (TypeError, ValueError):
            df[col] = df[col].astype(object)  # not numeric — widen so free text can be saved
            return val
        if pd.api.types.is_integer_dtype(dtype):
            if num.is_integer():
                return int(num)
            df[col] = df[col].astype("float64")  # decimal typed into an int column
        return num

    if pd.api.types.is_datetime64_any_dtype(dtype):
        try:
            return pd.to_datetime(val)
        except Exception:
            df[col] = df[col].astype(object)
            return val

    return val


@router.get("/{dataset_id}/cleaned-data-quality")
def get_cleaned_data_quality(
    dataset_id: int,
    page: int = 1,
    page_size: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Same shape as /data-quality, but against the CLEANED/processed file — for
    the "Review Manually" viewer (right after Review Cleaning) that surfaces
    whatever the pipeline couldn't or didn't fix: negative values, outliers,
    cross-column mismatches, etc. Editing here (via /apply-cell-edits with
    source="cleaned") changes the cleaned copy only — the original file is
    never touched, matching every other editor in this file.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    page = max(1, page)
    page_size = min(max(10, page_size), 500)

    try:
        df = _load_source_df(dataset, "cleaned")
        total_rows = len(df)
        start = (page - 1) * page_size
        page_df = df.iloc[start:start + page_size]
        rows = json.loads(page_df.to_json(orient="records"))
        row_indices = [int(i) for i in page_df.index]

        plan = _load_or_build_plan(df, dataset_id, current_user.id)
        issues, row_issues, column_notices = _compute_quality_issues(df, page_df, plan)

        return _sanitize({
            "dataset_id": dataset_id,
            "columns": list(df.columns),
            "rows": rows,
            "row_indices": row_indices,
            "editable": True,
            "issues": issues,
            "row_issues": row_issues,
            "column_notices": column_notices if page == 1 else [],
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": max(1, -(-total_rows // page_size)),
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read cleaned dataset: {e}")


@router.post("/{dataset_id}/cell-chat")
def cell_chat(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Conversational assistant for one specific cell (Browse Full Data /
    Highlight Issues / cleaned-data right-click editor). Body: {row, column,
    message, history: [{role, content}], source: "raw"|"cleaned" (default
    "raw", unchanged for every existing caller)}.
    Returns {reply, suggested_value}.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    source = body.get("source", "raw")
    if source == "raw" and not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    row = body.get("row")
    column = body.get("column")
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if row is None or not column or not message:
        raise HTTPException(status_code=400, detail="row, column and message are required")

    try:
        df = _load_source_df(dataset, source)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")
    if column not in df.columns:
        raise HTTPException(status_code=400, detail="Unknown column")

    current_value = None
    if row in df.index:
        v = df.at[row, column]
        current_value = None if pd.isna(v) else str(v)
    sample_values = [str(v) for v in df[column].dropna().unique()[:15]]

    from app.services.nlp.cell_chat import chat_about_cell
    result = chat_about_cell(column, current_value, sample_values, message, history)
    if result is None:
        raise HTTPException(status_code=503,
                             detail="The AI assistant is unavailable right now — no model responded.")
    return result


@router.post("/{dataset_id}/apply-cell-edits")
def apply_cell_edits(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Persist manual cell edits (from the cell-chat editor's Save Changes
    button). Edits are keyed by the ORIGINAL row index shown in whichever
    view they were made in.

    Body: {edits: [{row, column, value}], delete_rows: [row_index, ...],
           delete_columns: [column_name, ...], source: "raw"|"cleaned"}
    source defaults to "raw" — unchanged from prior behaviour, writing
    straight back to the dataset's original file. delete_rows/delete_columns
    are only meaningful with source="cleaned" (the "Review Manually" editor);
    for source="raw" they're ignored so existing callers are unaffected.

    source="cleaned" writes to the CLEANED/processed copy only — the
    original file is never touched — and updates row/column counts +
    cleaning-report metadata so the Cleaning Report / Cleaned Data tab
    reflect the change immediately.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    source = body.get("source", "raw")
    if source == "raw" and not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    edits = body.get("edits") or []
    delete_rows = body.get("delete_rows") or [] if source == "cleaned" else []
    delete_columns = body.get("delete_columns") or [] if source == "cleaned" else []
    if not isinstance(edits, list) or not (edits or delete_rows or delete_columns):
        raise HTTPException(status_code=400,
                             detail="Body must include a non-empty 'edits', 'delete_rows' or 'delete_columns'")

    try:
        df = _load_source_df(dataset, source)

        applied = 0
        for e in edits:
            row, col, val = e.get("row"), e.get("column"), e.get("value")
            if col not in df.columns or row not in df.index:
                continue
            val = val if val not in ("", None) else None
            df.at[row, col] = _coerce_cell_edit(df, col, val)
            applied += 1

        deleted_rows = 0
        if delete_rows:
            existing = [r for r in delete_rows if r in df.index]
            if existing:
                df = df.drop(index=existing)
                deleted_rows = len(existing)

        deleted_cols = 0
        if delete_columns:
            existing_cols = [c for c in delete_columns if c in df.columns]
            if existing_cols:
                df = df.drop(columns=existing_cols)
                deleted_cols = len(existing_cols)

        if source == "cleaned":
            df = df.reset_index(drop=True)
            preprocessor = DataPreprocessor()
            preprocessor._save_processed_dataset(df, dataset_id, current_user.id)

            dataset.row_count = len(df)
            dataset.column_count = len(df.columns)

            # Keep the Cleaning Report / Cleaned Data tab's KPI numbers and
            # column list in sync with the manually-edited cleaned copy.
            try:
                meta = preprocessor.get_metadata(dataset_id, current_user.id) or {}
                meta['cleaned_shape'] = {'rows': len(df), 'columns': len(df.columns)}
                meta['column_names'] = df.columns.tolist()
                if isinstance(meta.get('cleaning_report'), dict):
                    meta['cleaning_report']['cleaned'] = {
                        'rows': len(df), 'columns': len(df.columns),
                        'missing_cells': int(df.isna().sum().sum()),
                        'duplicates': int(df.duplicated().sum()),
                    }
                preprocessor._save_metadata(meta, dataset_id, current_user.id)
            except Exception as me:
                print(f"[apply-cell-edits] could not update report metadata: {me}")
        else:
            ext = Path(dataset.file_path).suffix.lower()
            if ext in (".xlsx", ".xls"):
                df.to_excel(dataset.file_path, index=False)
            else:
                df.to_csv(dataset.file_path, index=False)

        dataset.last_refreshed = datetime.utcnow()
        db.commit()

        return {"success": True, "applied": applied,
                "deleted_rows": deleted_rows, "deleted_columns": deleted_cols}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply cell edits: {e}")


def _compute_column_transform(df: pd.DataFrame, column: str, action: Dict[str, Any]):
    """
    Deterministic, whitelisted transforms for the column-chat editor. The LLM
    only ever picks a "type" + params from a fixed menu (validated server-side
    in cell_chat.COLUMN_ACTION_TYPES) — it never generates code that runs
    against the data, so a bad model response can't corrupt the dataset.

    Returns (new_series, meta) where meta may include "unresolved_count" —
    non-null cells the transform couldn't confidently touch and left as-is.
    """
    s = df[column]
    action_type = action.get("type")
    params = action.get("params") or {}
    meta: Dict[str, Any] = {}

    if action_type == "standardize_date":
        dayfirst = bool(params.get("dayfirst", False))
        fmt = params.get("format") or "%Y-%m-%d"

        parsed = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)

        # Mixed-format date columns are common (e.g. some rows "01/02/2023",
        # others already ISO "2023-02-01") — a single dayfirst assumption
        # can't parse all of them. Retry failures with dayfirst flipped...
        still_missing = parsed.isna() & s.notna()
        if still_missing.any():
            alt = pd.to_datetime(s[still_missing], errors="coerce", dayfirst=not dayfirst)
            parsed.loc[still_missing] = alt

        # ...then per-cell dateutil parsing for whatever pandas' vectorized
        # parser still can't handle (e.g. "Jan 5, 2023", "5th of June 2023").
        still_missing = parsed.isna() & s.notna()
        if still_missing.any():
            from dateutil import parser as _dateutil_parser
            for i in s.index[still_missing]:
                try:
                    parsed.at[i] = _dateutil_parser.parse(str(s.at[i]), dayfirst=dayfirst)
                except Exception:
                    pass

        formatted = parsed.dt.strftime(fmt)
        meta["unresolved_count"] = int((parsed.isna() & s.notna()).sum())
        return formatted.where(parsed.notna(), s), meta

    if action_type == "standardize_number":
        from app.services.data_processing.type_detector import parse_numeric_series
        parsed, _info = parse_numeric_series(s)
        meta["unresolved_count"] = int((parsed.isna() & s.notna()).sum())
        return parsed.where(parsed.notna(), s), meta

    if action_type == "trim_whitespace":
        trimmed = s.astype(str).str.replace(r"\s{2,}", " ", regex=True).str.strip()
        return trimmed.where(s.notna(), s), meta

    if action_type == "change_case":
        case = params.get("case", "title")
        ss = s.astype(str)
        out = ss.str.upper() if case == "upper" else ss.str.lower() if case == "lower" else ss.str.title()
        return out.where(s.notna(), s), meta

    if action_type == "replace_value":
        frm, to = params.get("from"), params.get("to")
        if frm is None:
            return s, meta
        out = s.copy()
        mask = s.astype(str) == str(frm)
        out[mask] = to
        return out, meta

    if action_type == "fill_missing":
        val = params.get("value", "")
        return s.where(s.notna(), val), meta

    if action_type == "set_all":
        val = params.get("value", "")
        return pd.Series([val] * len(s), index=s.index), meta

    return s, meta


def _diff_examples(orig: pd.Series, new: pd.Series, limit: int = 5):
    """Rows where the value actually changes, for a before/after preview."""
    examples = []
    count = 0
    for i in orig.index:
        ov, nv = orig.at[i], new.at[i]
        ov_s = None if pd.isna(ov) else str(ov)
        nv_s = None if pd.isna(nv) else str(nv)
        if ov_s != nv_s:
            count += 1
            if len(examples) < limit:
                examples.append({"row": int(i), "from": ov_s, "to": nv_s})
    return count, examples


@router.post("/{dataset_id}/column-chat")
def column_chat(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Conversational assistant for an entire column (right-click a column
    header). Body: {column, message, history}. If the model proposes a bulk
    transform, a dry-run preview (affected count + before/after examples) is
    computed and returned alongside it — nothing is written until the user
    confirms via /apply-column-action.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    source = body.get("source", "raw")
    if source == "raw" and not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    column = body.get("column")
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not column or not message:
        raise HTTPException(status_code=400, detail="column and message are required")

    try:
        df = _load_source_df(dataset, source)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {e}")
    if column not in df.columns:
        raise HTTPException(status_code=400, detail="Unknown column")

    s = df[column]
    dtype_label = ("numeric" if pd.api.types.is_numeric_dtype(s)
                   else "datetime" if pd.api.types.is_datetime64_any_dtype(s)
                   else "text")
    sample_values = [str(v) for v in s.dropna().unique()[:15]]
    null_count = int(s.isna().sum())

    from app.services.nlp.cell_chat import chat_about_column
    result = chat_about_column(column, dtype_label, sample_values, null_count, len(s), message, history)
    if result is None:
        raise HTTPException(status_code=503,
                             detail="The AI assistant is unavailable right now — no model responded.")

    preview = None
    action = result.get("action")
    if action:
        try:
            new_series, meta = _compute_column_transform(df, column, action)
            count, examples = _diff_examples(s, new_series)
            preview = {"affected_count": count, "examples": examples,
                       "unresolved_count": meta.get("unresolved_count", 0)}
        except Exception as e:
            preview = {"error": str(e)}
            action = None

    return _sanitize({"reply": result["reply"], "action": action, "preview": preview})


# Staging a whole-column change into the same pending-edits/Save Changes flow
# as single-cell edits (rather than writing immediately) keeps both editors
# consistent and lets the user review/discard before anything is persisted.
_MAX_STAGED_COLUMN_EDITS = 20000


@router.post("/{dataset_id}/compute-column-diff")
def compute_column_diff(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full (uncapped, up to a safety limit) row-by-row diff for a column-chat
    action, so the frontend can stage every affected cell into the same
    pending-edits queue /apply-cell-edits already saves — instead of writing
    the whole column immediately.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    source = body.get("source", "raw")
    if source == "raw" and not os.path.exists(dataset.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")

    column = body.get("column")
    action = body.get("action")
    if not column or not isinstance(action, dict):
        raise HTTPException(status_code=400, detail="column and action are required")

    from app.services.nlp.cell_chat import COLUMN_ACTION_TYPES
    if action.get("type") not in COLUMN_ACTION_TYPES:
        raise HTTPException(status_code=400, detail="Unknown action type")

    try:
        df = _load_source_df(dataset, source)
        if column not in df.columns:
            raise HTTPException(status_code=400, detail="Unknown column")

        orig = df[column]
        new_series, meta = _compute_column_transform(df, column, action)

        edits = []
        truncated = False
        for i in orig.index:
            ov, nv = orig.at[i], new_series.at[i]
            ov_s = None if pd.isna(ov) else str(ov)
            nv_s = None if pd.isna(nv) else str(nv)
            if ov_s == nv_s:
                continue
            if len(edits) >= _MAX_STAGED_COLUMN_EDITS:
                truncated = True
                break
            edits.append({"row": int(i), "column": column, "value": nv_s})

        return _sanitize({
            "edits": edits,
            "applied_count": len(edits),
            "unresolved_count": meta.get("unresolved_count", 0),
            "truncated": truncated,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute column diff: {e}")


@router.patch("/{dataset_id}", response_model=DatasetSchema)
def rename_dataset(
    dataset_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a dataset's display name. Body: {name: str}."""
    new_name = (body.get("name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name is required")
    if len(new_name) > 255:
        raise HTTPException(status_code=400, detail="name must be 255 characters or fewer")

    dataset = crud_dataset.rename_dataset(db, dataset_id, current_user.id, new_name)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


@router.delete("/{dataset_id}", response_model=DatasetDeleteResponse)
def delete_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a dataset and its associated file
    """
    # Get dataset first to access file path
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Store file path before deletion
    file_path = dataset.file_path
    
    # Delete from database
    success = crud_dataset.delete_dataset(db, dataset_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete dataset"
        )
    
    # Delete physical file
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        # Log error but don't fail the request
        print(f"Warning: Failed to delete file {file_path}: {str(e)}")
    
    return DatasetDeleteResponse(
        message="Dataset deleted successfully",
        dataset_id=dataset_id
    )


@router.post("/{dataset_id}/process")
def process_dataset(
    dataset_id: int,
    clean_data: bool = True,
    cleaning_strategy: str = 'auto',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process and clean a dataset
    
    - Detects data types
    - Analyzes data quality (missing values, duplicates, outliers)
    - Cleans data (if requested)
    - Saves processed dataset and metadata
    
    cleaning_strategy options:
    - 'auto': Intelligent handling based on type
    - 'drop': Drop rows with missing values
    - 'impute_mean': Fill numeric with mean
    - 'impute_median': Fill numeric with median
    - 'impute_mode': Fill with most frequent value
    """
    # Get dataset
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check if file exists
    if not os.path.exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found on disk"
        )
    
    # Process dataset
    preprocessor = DataPreprocessor(processed_dir=str(PROCESSED_DIR))
    
    try:
        result = preprocessor.process_dataset(
            file_path=dataset.file_path,
            dataset_id=dataset_id,
            user_id=current_user.id,
            clean_data=clean_data,
            cleaning_strategy=cleaning_strategy
        )
        
        if not result.get('success'):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get('error', 'Processing failed')
            )
        
        # Update dataset metadata in database
        if clean_data and result.get('cleaning_report'):
            cleaned_shape = result['cleaned_shape']
            type_map = result['type_detection']['type_map']
            
            crud_dataset.update_dataset_metadata(
                db=db,
                dataset_id=dataset_id,
                row_count=cleaned_shape['rows'],
                column_count=cleaned_shape['columns'],
                data_types_json=json.dumps(type_map)
            )
            
            crud_dataset.update_dataset_processing_status(
                db=db,
                dataset_id=dataset_id,
                cleaned_status=True
            )
        
        return JSONResponse(content=_sanitize(result))
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )


@router.get("/{dataset_id}/analysis")
def analyze_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analyze dataset data quality without cleaning
    
    Returns:
    - Data types for each column
    - Missing value analysis
    - Duplicate row analysis
    - Outlier detection
    - Sample data preview
    """
    # Get dataset
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Check if file exists
    if not os.path.exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found on disk"
        )
    
    # Analyze dataset
    preprocessor = DataPreprocessor()
    
    result = preprocessor.analyze_only(dataset.file_path)
    
    if not result.get('success'):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get('error', 'Analysis failed')
        )
    
    # Sanitize NaN/Inf values before JSON serialisation (json.dumps rejects them)
    return JSONResponse(content=_sanitize(result))


@router.get("/{dataset_id}/cleaning-report")
def get_cleaning_report(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get cleaning report for a processed dataset
    
    Returns metadata about the cleaning process including:
    - Original vs cleaned statistics
    - Actions taken
    - Improvements made
    """
    # Get dataset
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    # Load metadata
    preprocessor = DataPreprocessor(processed_dir=str(PROCESSED_DIR))
    metadata = preprocessor.get_metadata(dataset_id, current_user.id)
    
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cleaning report not found. Dataset may need to be reprocessed."
        )
    
    return metadata


@router.get("/{dataset_id}/cleaned-preview")
def get_cleaned_preview(
    dataset_id: int,
    rows: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a preview (first N rows) of the cleaned/processed dataset file.
    Falls back to the original file if no cleaned version exists.
    """
    dataset = crud_dataset.get_dataset_by_id(db, dataset_id, current_user.id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    preprocessor = DataPreprocessor(processed_dir=str(PROCESSED_DIR))

    # Try cleaned file first
    df = preprocessor.get_processed_dataset(dataset_id, current_user.id)
    source = "cleaned"

    # Fall back to original
    if df is None:
        if not os.path.exists(dataset.file_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found on disk")
        df, _, _, _ = parse_dataset_file(dataset.file_path)
        source = "original"

    preview_df = df.head(rows)
    # Replace NaN with None so JSON serializes cleanly
    # Use to_json then parse back — pandas converts NaN → null properly
    preview_rows = json.loads(preview_df.to_json(orient='records'))

    # Surface whatever the cleaning pipeline couldn't/didn't fix — negative
    # values, statistical outliers, cross-column mismatches, out-of-range
    # dates, and (if a step was skipped) leftover missing/inconsistent
    # values — so "Cleaned Data" isn't presented as if it's now perfect.
    issues, row_issues, column_notices = [], [], []
    try:
        plan = _load_or_build_plan(df, dataset_id, current_user.id)
        issues, row_issues, column_notices = _compute_quality_issues(df, preview_df, plan)
    except Exception:
        pass  # preview still renders even if the quality pass fails

    return {
        "source": source,
        "total_rows": len(df),
        "column_names": df.columns.tolist(),
        "preview_rows": preview_rows,
        "row_indices": [int(i) for i in preview_df.index],
        "issues": _sanitize(issues),
        "row_issues": _sanitize(row_issues),
        "column_notices": column_notices,
        "needs_manual_review": bool(issues or row_issues or column_notices),
    }


@router.get("/{dataset_id}/queries")
async def get_query_history(
    dataset_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the query execution history for a dataset (newest first).
    Each entry includes template_type, parameters, optional NLP query text,
    execution time, and timestamp.
    """
    # Verify dataset ownership
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == current_user.id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    import json as _json
    history = crud_history.get_history(db, dataset_id, current_user.id, limit=limit)
    return [
        {
            "id":               h.id,
            "template_type":    h.template_type,
            "query_text":       h.query_text,
            "parameters":       _json.loads(h.parameters_json or "{}"),
            "nlp_mode":         h.nlp_mode,
            "execution_time_ms":h.execution_time_ms,
            "created_at":       h.created_at.isoformat() if h.created_at else None,
        }
        for h in history
    ]


@router.delete("/{dataset_id}/queries/{history_id}", status_code=204)
async def delete_query_history_item(
    dataset_id: int,
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single query history entry."""
    deleted = crud_history.delete_history_item(db, history_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History item not found")
    return None
