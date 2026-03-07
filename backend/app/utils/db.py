"""Database utility helpers for route handlers."""

from typing import Type, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


def get_or_404(db: Session, model: Type[T], id: int) -> T:
    """Fetch a record by primary key or raise HTTP 404."""
    obj = db.query(model).filter(model.id == id).first()
    if obj is None:
        raise HTTPException(
            status_code=404, detail=f"{model.__name__} not found"
        )
    return obj
