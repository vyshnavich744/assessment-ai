from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.core.config import settings
from app.core.rate_limiter import rate_limiter

router = APIRouter(prefix="/api/urls", tags=["urls"])


@router.post("", response_model=schemas.ShortenResponse, status_code=201)
def shorten_url(payload: schemas.ShortenRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded, try again later")

    try:
        record = crud.create_short_url(
            db, long_url=str(payload.long_url), custom_alias=payload.custom_alias, ttl_seconds=payload.ttl_seconds
        )
    except crud.AliasTakenError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except crud.CodeCollisionError as e:
        # Bounded retries exhausted -- surfaced as 503 so the client can retry,
        # rather than a generic 500. This is the kind of failure mode the
        # orchestration layer's "reliability" narrative documents.
        raise HTTPException(status_code=503, detail=str(e))

    return schemas.ShortenResponse(
        code=record.code,
        short_url=f"{settings.BASE_HOST}/{record.code}",
        long_url=record.long_url,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.get("", response_model=list[schemas.ShortenResponse])
def list_urls(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    records = crud.list_urls(db, limit=limit, offset=offset)
    return [
        schemas.ShortenResponse(
            code=r.code,
            short_url=f"{settings.BASE_HOST}/{r.code}",
            long_url=r.long_url,
            created_at=r.created_at,
            expires_at=r.expires_at,
        )
        for r in records
    ]


@router.delete("/{code}", status_code=204)
def delete_url(code: str, db: Session = Depends(get_db)):
    from app.core.cache import redirect_cache
    ok = crud.deactivate_url(db, code)
    if not ok:
        raise HTTPException(status_code=404, detail="short code not found")
    redirect_cache.invalidate(code)
    return None
