import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import models
from app.core.config import settings
from app.core.shortcode import generate_code


class CodeCollisionError(Exception):
    """Raised when a random code cannot be allocated after bounded retries."""


class AliasTakenError(Exception):
    """Raised when a requested custom alias is already in use."""


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


def create_short_url(db: Session, long_url: str, custom_alias: str | None, ttl_seconds: int | None) -> models.ShortURL:
    expires_at = None
    if ttl_seconds:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    if custom_alias:
        existing = db.query(models.ShortURL).filter(models.ShortURL.code == custom_alias).first()
        if existing:
            raise AliasTakenError(f"alias '{custom_alias}' already in use")
        record = models.ShortURL(
            code=custom_alias, long_url=long_url, is_custom_alias=True, expires_at=expires_at
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    # Random code path: bounded retries on collision (see shortcode.py docstring).
    last_error = None
    for _ in range(settings.MAX_RETRIES_CODE_COLLISION):
        code = generate_code(settings.CODE_LENGTH)
        record = models.ShortURL(code=code, long_url=long_url, expires_at=expires_at)
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
            return record
        except IntegrityError as e:
            db.rollback()
            last_error = e
            continue
    raise CodeCollisionError("could not allocate a unique short code after retries") from last_error


def get_active_url_by_code(db: Session, code: str) -> models.ShortURL | None:
    record = db.query(models.ShortURL).filter(models.ShortURL.code == code, models.ShortURL.is_active.is_(True)).first()
    if record is None:
        return None
    if record.expires_at is not None and record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    return record


def record_click(db: Session, short_url_id: int, referrer: str | None, user_agent: str | None, ip: str | None):
    event = models.ClickEvent(
        short_url_id=short_url_id,
        referrer=referrer,
        user_agent=user_agent,
        ip_hash=hash_ip(ip),
    )
    db.add(event)
    db.commit()


def deactivate_url(db: Session, code: str) -> bool:
    record = db.query(models.ShortURL).filter(models.ShortURL.code == code).first()
    if not record:
        return False
    record.is_active = False
    db.commit()
    return True


def get_analytics(db: Session, code: str) -> models.ShortURL | None:
    return db.query(models.ShortURL).filter(models.ShortURL.code == code).first()


def list_urls(db: Session, limit: int = 50, offset: int = 0):
    return (
        db.query(models.ShortURL)
        .order_by(models.ShortURL.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
