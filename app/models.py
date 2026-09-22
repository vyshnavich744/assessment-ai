from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ShortURL(Base):
    __tablename__ = "short_urls"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(16), unique=True, index=True, nullable=False)
    long_url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_custom_alias = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)  # supports soft delete
    owner = Column(String(128), nullable=True)  # optional API-key/user tag

    clicks = relationship("ClickEvent", back_populates="short_url", cascade="all, delete-orphan")


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    short_url_id = Column(Integer, ForeignKey("short_urls.id"), nullable=False)
    clicked_at = Column(DateTime, default=utcnow)
    referrer = Column(String(512), nullable=True)
    user_agent = Column(String(512), nullable=True)
    ip_hash = Column(String(64), nullable=True)  # hashed, never raw IP (privacy)

    short_url = relationship("ShortURL", back_populates="clicks")
