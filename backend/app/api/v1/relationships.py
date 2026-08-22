"""
Dataset Relationships — define join links between datasets and materialize
them into joined datasets (the "data model" layer).

A materialized join becomes a regular dataset, so every downstream feature
(cleaning, NLP queries, charts, dashboards, exports) works on it unchanged.
"""
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

import pandas as pd
from app.services.data_processing.io_utils import read_tabular
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.dataset import Dataset
from app.models.relationship import DatasetRelationship
from app.schemas.dataset import DatasetCreate
from app.crud import dataset as crud_dataset
from app.services.data_processing.preprocessor import DataPreprocessor

router = APIRouter()

UPLOAD_DIR = Path("data/uploads")


# ── Schemas ───────────────────────────────────────────────────────────────────

class RelationshipCreate(BaseModel):
    left_dataset_id:  int
    left_column:      str
    right_dataset_id: int
    right_column:     str
    join_type:        str = Field("inner", pattern="^(inner|left|right|outer)$")
    cardinality:      Optional[str] = Field(
        None, pattern="^(one_to_one|one_to_many|many_to_one|many_to_many)$")


class RelationshipOut(BaseModel):
    id:                 int
    left_dataset_id:    int
    left_dataset_name:  str
    left_column:        str
    right_dataset_id:   int
    right_dataset_name: str
    right_column:       str
    join_type:          str
    cardinality:        Optional[str] = None

    class Config:
        from_attributes = True


class MaterializeRequest(BaseModel):
    # CH-09.4: explicit acknowledgement required when the join multiplies rows
    confirm_fanout: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _own_dataset(db: Session, dataset_id: int, user_id: int) -> Optional[Dataset]:
    return db.query(Dataset).filter(
        Dataset.id == dataset_id, Dataset.user_id == user_id
    ).first()


def _load_df(dataset: Dataset, user_id: int) -> pd.DataFrame:
    """Prefer the cleaned/processed version; fall back to the original file."""
    pre = DataPreprocessor()
    df = pre.get_processed_dataset(dataset.id, user_id)
    if df is None:
        ext = os.path.splitext(dataset.file_path)[1].lower()
        df = read_tabular(dataset.file_path)
    return df


def _rel_out(db: Session, rel: DatasetRelationship) -> RelationshipOut:
    left  = db.query(Dataset).filter(Dataset.id == rel.left_dataset_id).first()
    right = db.query(Dataset).filter(Dataset.id == rel.right_dataset_id).first()
    return RelationshipOut(
        id=rel.id,
        left_dataset_id=rel.left_dataset_id,
        left_dataset_name=(left.original_filename or left.filename) if left else "(deleted)",
        left_column=rel.left_column,
        right_dataset_id=rel.right_dataset_id,
        right_dataset_name=(right.original_filename or right.filename) if right else "(deleted)",
        right_column=rel.right_column,
        join_type=rel.join_type,
        cardinality=getattr(rel, "cardinality", None),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    body: RelationshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Define a join link between two of the caller's datasets."""
    left  = _own_dataset(db, body.left_dataset_id, current_user.id)
    right = _own_dataset(db, body.right_dataset_id, current_user.id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="One or both datasets not found")
    if body.left_dataset_id == body.right_dataset_id:
        raise HTTPException(status_code=400, detail="Cannot relate a dataset to itself")

    # Validate the join columns actually exist
    try:
        left_cols  = set(_load_df(left, current_user.id).columns)
        right_cols = set(_load_df(right, current_user.id).columns)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read datasets: {e}")

    if body.left_column not in left_cols:
        raise HTTPException(status_code=400,
                            detail=f"Column '{body.left_column}' not found in {left.original_filename}")
    if body.right_column not in right_cols:
        raise HTTPException(status_code=400,
                            detail=f"Column '{body.right_column}' not found in {right.original_filename}")

    # CH-09: compute cardinality at create time when not supplied by a suggestion
    cardinality = body.cardinality
    if cardinality is None:
        try:
            ldf = _load_df(left, current_user.id)
            rdf = _load_df(right, current_user.id)
            lu = ldf[body.left_column].dropna()
            ru = rdf[body.right_column].dropna()
            from app.services.data_processing import config as C
            l_unique = (lu.nunique() / len(lu) if len(lu) else 0) >= C.REL_UNIQUE_RATIO
            r_unique = (ru.nunique() / len(ru) if len(ru) else 0) >= C.REL_UNIQUE_RATIO
            cardinality = ("one_to_one" if l_unique and r_unique
                           else "one_to_many" if l_unique
                           else "many_to_one" if r_unique
                           else "many_to_many")
        except Exception:
            cardinality = None

    rel = DatasetRelationship(
        user_id=current_user.id,
        left_dataset_id=body.left_dataset_id,
        left_column=body.left_column,
        right_dataset_id=body.right_dataset_id,
        right_column=body.right_column,
        join_type=body.join_type,
        cardinality=cardinality,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return _rel_out(db, rel)


@router.get("/suggest")
async def suggest_relationships_endpoint(
    dataset_ids: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    CH-09: scan the caller's datasets for likely join keys. Pure suggestion —
    never creates anything. Evidence is value overlap; name similarity only
    nudges confidence, so same-named-but-unrelated 'id' columns don't link.
    """
    q = db.query(Dataset).filter(Dataset.user_id == current_user.id)
    if dataset_ids:
        try:
            ids = [int(x) for x in dataset_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="dataset_ids must be a comma-separated list of ints")
        q = q.filter(Dataset.id.in_(ids))
    else:
        q = q.order_by(Dataset.id.desc()).limit(6)   # bound the O(n²) column scan

    datasets = q.all()
    if len(datasets) < 2:
        return {"candidates": [], "message": "Need at least two datasets to suggest relationships."}

    dfs, names = {}, {}
    for ds in datasets:
        try:
            df = _load_df(ds, current_user.id)
        except Exception:
            continue
        if df is not None and not df.empty:
            dfs[ds.id] = df
            names[ds.id] = ds.original_filename or ds.filename

    if len(dfs) < 2:
        return {"candidates": [], "message": "Could not read enough datasets to compare."}

    from app.services.data_processing.relationship_detector import suggest_relationships
    candidates = suggest_relationships(dfs, names)
    return {"candidates": candidates,
            "message": (f"{len(candidates)} candidate relationship(s) found."
                        if candidates else
                        "No strong relationships found — these files don't appear to share key values.")}


@router.get("", response_model=List[RelationshipOut])
async def list_relationships(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rels = db.query(DatasetRelationship).filter(
        DatasetRelationship.user_id == current_user.id
    ).all()
    return [_rel_out(db, r) for r in rels]


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    relationship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rel = db.query(DatasetRelationship).filter(
        DatasetRelationship.id == relationship_id,
        DatasetRelationship.user_id == current_user.id,
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")
    db.delete(rel)
    db.commit()
    return None


@router.post("/{relationship_id}/materialize", status_code=status.HTTP_201_CREATED)
async def materialize_join(
    relationship_id: int,
    background_tasks: BackgroundTasks,
    body: Optional[MaterializeRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute the join and register the result as a new dataset.
    The joined dataset then works with every existing feature (queries,
    charts, dashboards) without special-casing.
    """
    rel = db.query(DatasetRelationship).filter(
        DatasetRelationship.id == relationship_id,
        DatasetRelationship.user_id == current_user.id,
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    left  = _own_dataset(db, rel.left_dataset_id, current_user.id)
    right = _own_dataset(db, rel.right_dataset_id, current_user.id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="One of the linked datasets was deleted")

    try:
        ldf = _load_df(left, current_user.id)
        rdf = _load_df(right, current_user.id)

        # Align join-key dtypes (a numeric ID in one sheet is often text in the other)
        lkey, rkey = rel.left_column, rel.right_column
        if ldf[lkey].dtype != rdf[rkey].dtype:
            ldf[lkey] = ldf[lkey].astype(str).str.strip()
            rdf[rkey] = rdf[rkey].astype(str).str.strip()

        # CH-09.4: N:M fan-out guard — a many-to-many join can silently multiply
        # rows, which double-counts every SUM downstream. Require explicit consent.
        if getattr(rel, "cardinality", None) == "many_to_many" and not (body and body.confirm_fanout):
            from app.services.data_processing.relationship_detector import estimate_join_rows
            from app.services.data_processing import config as C
            projected = estimate_join_rows(ldf, lkey, rdf, rkey)
            if projected > C.REL_FANOUT_MULTIPLE * max(len(ldf), len(rdf)):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"This many-to-many join would produce ≈{projected:,} rows "
                        f"(inputs: {len(ldf):,} and {len(rdf):,}). Sums computed on the "
                        "result would double-count. Send {\"confirm_fanout\": true} to proceed anyway."
                    ),
                )

        merged = ldf.merge(
            rdf, how=rel.join_type, left_on=lkey, right_on=rkey,
            suffixes=("", f"_{(right.original_filename or 'right').split('.')[0][:12]}"),
        )
    except HTTPException:
        raise   # deliberate 4xx (e.g. the fan-out guard) — don't wrap as 500
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Join column missing: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Join failed: {e}")

    if merged.empty:
        raise HTTPException(
            status_code=400,
            detail="Join produced 0 rows — check that the key columns share values "
                   "(an inner join drops rows without a match; try a left join).",
        )

    # Register merged frame as a new dataset
    user_dir = UPLOAD_DIR / f"user_{current_user.id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4()}.csv"
    fpath = user_dir / fname
    merged.to_csv(fpath, index=False)

    lname = (left.original_filename or "left").rsplit(".", 1)[0]
    rname = (right.original_filename or "right").rsplit(".", 1)[0]
    display = f"{lname} ⋈ {rname} (joined).csv"

    ds = crud_dataset.create_dataset(db, DatasetCreate(
        user_id=current_user.id,
        filename=fname,
        original_filename=display,
        file_path=str(fpath),
        row_count=len(merged),
        column_count=len(merged.columns),
        data_types_json=json.dumps({}),
    ))

    # CH-09.5: consent — the joined dataset goes through the same analyze-first
    # review flow as uploads and connector imports; nothing value-level is
    # applied without the user's approval (consistent with CP-08).
    from app.api.v1.datasets import _analyze_dataset_in_background
    ds.processing_status = "processing"
    db.commit()
    background_tasks.add_task(
        _analyze_dataset_in_background, ds.id, current_user.id, str(fpath))

    return {
        "dataset_id": ds.id,
        "name": display,
        "row_count": len(merged),
        "column_count": len(merged.columns),
        "message": (f"Joined dataset created with {len(merged):,} rows — it is being "
                    "analyzed and will appear for cleaning review like any import."),
    }
