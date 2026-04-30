import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import pipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantasy Football AI Platform",
    version="0.1.0",
    description="AI-powered fantasy football management system",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(pipeline.router)


@app.on_event("startup")
async def startup_checks():
    missing = []
    if not settings.yahoo_client_id:
        missing.append("YAHOO_CLIENT_ID")
    if not settings.yahoo_client_secret:
        missing.append("YAHOO_CLIENT_SECRET")
    if not settings.yahoo_league_id:
        missing.append("YAHOO_LEAGUE_ID")
    if not settings.yahoo_refresh_token:
        missing.append("YAHOO_REFRESH_TOKEN")
    if not settings.rapidapi_key:
        missing.append("RAPIDAPI_KEY")
    if missing:
        logger.warning("Optional settings not configured: %s", missing)
    logger.info(
        "App started — environment=%s, %d optional setting(s) not configured",
        settings.environment,
        len(missing),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
