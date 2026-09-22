from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.core.cache import redirect_cache

router = APIRouter(tags=["redirect"])


@router.get("/{code}")
def redirect_to_long_url(code: str, request: Request, db: Session = Depends(get_db)):
    cached = redirect_cache.get(code)
    if cached is not None:
        short_url_id, long_url = cached
    else:
        record = crud.get_active_url_by_code(db, code)
        if record is None:
            raise HTTPException(status_code=404, detail="short URL not found or expired")
        short_url_id, long_url = record.id, record.long_url
        redirect_cache.set(code, (short_url_id, long_url))

    # Click recording is best-effort: a failure here must never break the
    # redirect itself (availability of the redirect > completeness of analytics).
    try:
        crud.record_click(
            db,
            short_url_id=short_url_id,
            referrer=request.headers.get("referer"),
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except Exception:
        db.rollback()

    return RedirectResponse(url=long_url, status_code=302)
