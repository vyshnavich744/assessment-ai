from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routers import shorten, redirect, analytics


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Agentic URL Shortener",
    description="URL shortener core service, built as the target system for "
                "the agentic SDLC orchestration prototype.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(shorten.router)
app.include_router(analytics.router)
app.include_router(redirect.router)  # registered last: catch-all /{code} path
