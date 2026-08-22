"""
Anomaly Detection API Endpoints
"""
import os
import logging
from typing import List, Optional

import pandas as pd
from app.services.data_processing.io_utils import read_tabular
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.dataset import Dataset
from app.models.anomaly import Anomaly
from app.services.analytics.anomaly_detection import detect_anomalies
from app.services.data_processing import DataPreprocessor

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_df(dataset: Dataset) -> pd.DataFrame:
    preprocessor = DataPreprocessor()
    df = preprocessor.get_processed_dataset(dataset.id, dataset.user_id)
    if df is None:
        ext = os.path.splitext(dataset.file_path)[1].lower()
        df = read_tabular(dataset.file_path)
    return df


@router.get("/datasets/{dataset_id}/anomalies")
async def get_anomalies(
    dataset_id: int,
    column:        Optional[str]   = Query(None,       description="Column to scan (default: all numeric)"),
    method:        str             = Query("zscore",    description="zscore | isolation_forest | auto"),
    threshold:     float           = Query(3.0,         description="Z-score sigma threshold (zscore method)"),
    contamination: float           = Query(0.05,        description="Expected outlier fraction (isolation_forest)"),
    refresh:       bool            = Query(False,       description="Re-run detection even if cached results exist"),
    db:            Session         = Depends(get_db),
    current_user:  User            = Depends(get_current_user),
):
    """
    Detect anomalies in a dataset column.

    Returns cached DB results unless `refresh=true` is passed, in which case
    detection runs fresh and results are saved (replacing previous run for the
    same column+method).
    """
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == current_user.id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    col_key = column or "__all__"

    # Return cached unless refresh requested
    if not refresh:
        cached = (
            db.query(Anomaly)
            .filter(
                Anomaly.dataset_id == dataset_id,
                Anomaly.column_name == col_key,
                Anomaly.method == method,
            )
            .all()
        )
        if cached:
            return {
                "success":    True,
                "dataset_id": dataset_id,
                "column":     col_key,
                "method":     method,
                "count":      len(cached),
                "anomalies":  [a.to_dict() for a in cached],
                "cached":     True,
            }

    # Run detection
    try:
        df = _load_df(dataset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load dataset: {exc}")

    label_col = None
    if column:
        # Try to find a date/label column to use as labels
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]) or "date" in c.lower() or "time" in c.lower():
                label_col = c
                break

    raw = detect_anomalies(
        df,
        column=column,
        method=method,
        threshold=threshold,
        contamination=contamination,
        label_column=label_col,
    )

    # Persist — delete old results for same column+method first
    db.query(Anomaly).filter(
        Anomaly.dataset_id == dataset_id,
        Anomaly.column_name == col_key,
        Anomaly.method == method,
    ).delete(synchronize_session=False)

    saved: List[Anomaly] = []
    for a in raw:
        val = a.get("value")
        scalar_val = None
        extra_val  = None
        if isinstance(val, dict):
            extra_val = val
        else:
            try:
                scalar_val = float(val)
            except (TypeError, ValueError):
                scalar_val = None

        # An "all columns" zscore scan tags each result with its real source
        # column (a["column_name"]) — column_name itself stays "__all__" so
        # the existing cache/replace-on-refresh logic (keyed on col_key)
        # still works, but the real column is preserved in `extra` so the
        # UI can show which column each anomaly actually came from instead
        # of every row looking like it's from the same "multiple" bucket.
        if col_key == "__all__" and a.get("column_name"):
            extra_val = {**(extra_val or {}), "source_column": a["column_name"]}

        record = Anomaly(
            dataset_id    = dataset_id,
            column_name   = col_key,
            method        = method,
            row_index     = a.get("index"),
            label         = a.get("label"),
            value         = scalar_val,
            zscore        = a.get("zscore"),
            anomaly_score = a.get("anomaly_score"),
            severity      = a["severity"],
            extra         = extra_val,
        )
        db.add(record)
        saved.append(record)

    db.commit()
    for r in saved:
        db.refresh(r)

    return {
        "success":    True,
        "dataset_id": dataset_id,
        "column":     col_key,
        "method":     method,
        "count":      len(saved),
        "anomalies":  [r.to_dict() for r in saved],
        "cached":     False,
    }


@router.delete("/datasets/{dataset_id}/anomalies")
async def clear_anomalies(
    dataset_id:   int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """Delete all stored anomaly records for a dataset."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == current_user.id,
    ).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    deleted = (
        db.query(Anomaly)
        .filter(Anomaly.dataset_id == dataset_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"success": True, "deleted": deleted}
