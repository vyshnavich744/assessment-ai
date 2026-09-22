from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field, field_validator


class ShortenRequest(BaseModel):
    long_url: HttpUrl
    custom_alias: Optional[str] = Field(default=None, min_length=3, max_length=16)
    ttl_seconds: Optional[int] = Field(default=None, gt=0, description="Optional expiry in seconds")

    @field_validator("custom_alias")
    @classmethod
    def alias_must_be_alnum(cls, v):
        if v is not None and not v.isalnum():
            raise ValueError("custom_alias must be alphanumeric")
        return v


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    long_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClickEventOut(BaseModel):
    clicked_at: datetime
    referrer: Optional[str] = None

    class Config:
        from_attributes = True


class AnalyticsResponse(BaseModel):
    code: str
    long_url: str
    total_clicks: int
    created_at: datetime
    is_active: bool
    last_10_clicks: List[ClickEventOut]
