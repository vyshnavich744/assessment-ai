import os


class Settings:
    APP_NAME: str = "url-shortener"
    BASE_HOST: str = os.environ.get("BASE_HOST", "http://localhost:8000")
    CODE_LENGTH: int = 7
    RATE_LIMIT_REQUESTS: int = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "30"))
    CACHE_MAX_ENTRIES: int = int(os.environ.get("CACHE_MAX_ENTRIES", "5000"))
    MAX_RETRIES_CODE_COLLISION: int = 5


settings = Settings()
