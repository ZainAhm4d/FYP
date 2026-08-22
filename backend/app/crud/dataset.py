"""
Dataset CRUD Operations
Create, Read, Update, Delete operations for datasets
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.dataset import Dataset
from app.schemas.dataset import DatasetCreate


def create_dataset(db: Session, dataset: DatasetCreate) -> Dataset:
    """
    Create a new dataset record in the database
    """
    db_dataset = Dataset(
        user_id=dataset.user_id,
        filename=dataset.filename,
        original_filename=dataset.original_filename,
        file_path=dataset.file_path,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        data_types_json=dataset.data_types_json,
        cleaned_status=False
    )
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)
    return db_dataset


def get_dataset_by_id(db: Session, dataset_id: int, user_id: int) -> Optional[Dataset]:
    """
    Get a dataset by ID (only if it belongs to the user)
    """
    return db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == user_id
    ).first()


def get_datasets_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Dataset]:
    """
    Get all datasets for a specific user with pagination
    """
    return db.query(Dataset).filter(
        Dataset.user_id == user_id
    ).order_by(desc(Dataset.upload_date)).offset(skip).limit(limit).all()


def update_dataset_processing_status(db: Session, dataset_id: int, cleaned_status: bool) -> Optional[Dataset]:
    """
    Update the cleaning/processing status of a dataset
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset:
        dataset.cleaned_status = cleaned_status
        db.commit()
        db.refresh(dataset)
    return dataset


def update_dataset_metadata(
    db: Session, 
    dataset_id: int, 
    row_count: Optional[int] = None,
    column_count: Optional[int] = None,
    data_types_json: Optional[str] = None
) -> Optional[Dataset]:
    """
    Update dataset metadata (row count, column count, data types)
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset:
        if row_count is not None:
            dataset.row_count = row_count
        if column_count is not None:
            dataset.column_count = column_count
        if data_types_json is not None:
            dataset.data_types_json = data_types_json
        db.commit()
        db.refresh(dataset)
    return dataset


def rename_dataset(db: Session, dataset_id: int, user_id: int, new_name: str) -> Optional[Dataset]:
    """
    Rename a dataset's display name (only if it belongs to the user).
    Only original_filename changes — filename (the on-disk name) and
    file_path are untouched, so no file needs to be renamed/moved.
    """
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, Dataset.user_id == user_id
    ).first()
    if dataset:
        dataset.original_filename = new_name
        db.commit()
        db.refresh(dataset)
    return dataset


def delete_dataset(db: Session, dataset_id: int, user_id: int) -> bool:
    """
    Delete a dataset (only if it belongs to the user)
    Returns True if deleted, False if not found
    """
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.user_id == user_id
    ).first()
    
    if dataset:
        db.delete(dataset)
        db.commit()
        return True
    return False


def count_user_datasets(db: Session, user_id: int) -> int:
    """
    Count total datasets for a user
    """
    return db.query(Dataset).filter(Dataset.user_id == user_id).count()
