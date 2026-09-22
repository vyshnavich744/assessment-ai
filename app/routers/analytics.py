from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/urls", tags=["analytics"])


@router.get("/{code}/analytics", response_model=schemas.AnalyticsResponse)
def get_analytics(code: str, db: Session = Depends(get_db)):
    record = crud.get_analytics(db, code)
    if record is None:
        raise HTTPException(status_code=404, detail="short code not found")

    clicks_sorted = sorted(record.clicks, key=lambda c: c.clicked_at, reverse=True)
    return schemas.AnalyticsResponse(
        code=record.code,
        long_url=record.long_url,
        total_clicks=len(record.clicks),
        created_at=record.created_at,
        is_active=record.is_active,
        last_10_clicks=clicks_sorted[:10],
    )
