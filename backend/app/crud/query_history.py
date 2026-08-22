"""
QueryHistory CRUD Operations
"""
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.query_history import QueryHistory


def save_query(
    db: Session,
    dataset_id: int,
    user_id: int,
    template_type: str,
    parameters: dict,
    query_text: Optional[str] = None,
    nlp_mode: Optional[str] = None,
    execution_time_ms: Optional[int] = None,
) -> QueryHistory:
    """Persist a query execution to history."""
    entry = QueryHistory(
        dataset_id=dataset_id,
        user_id=user_id,
        template_type=template_type,
        query_text=query_text,
        parameters_json=json.dumps(parameters, default=str),
        nlp_mode=nlp_mode,
        execution_time_ms=execution_time_ms,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_history(
    db: Session,
    dataset_id: int,
    user_id: int,
    limit: int = 20,
) -> List[QueryHistory]:
    """Return most-recent queries for a dataset, newest first."""
    return (
        db.query(QueryHistory)
        .filter(
            QueryHistory.dataset_id == dataset_id,
            QueryHistory.user_id == user_id,
        )
        .order_by(desc(QueryHistory.created_at))
        .limit(limit)
        .all()
    )


def delete_history_item(
    db: Session,
    history_id: int,
    user_id: int,
) -> bool:
    entry = (
        db.query(QueryHistory)
        .filter(QueryHistory.id == history_id, QueryHistory.user_id == user_id)
        .first()
    )
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True
