import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers import admin, assistant, auth, draft, draftboard, league, news, pipeline, players, preferences, teams
from backend.websocket.manager import news_ws_manager

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantasy Football AI Platform",
    version="0.1.0",
    description="AI-powered fantasy football management system",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://fantasymanager-production.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(admin.router)
app.include_router(assistant.router)
app.include_router(auth.router)
app.include_router(draft.router)
app.include_router(draftboard.router)
app.include_router(league.router)
app.include_router(news.router)
app.include_router(pipeline.router)
app.include_router(players.router)
app.include_router(preferences.router)
app.include_router(teams.router)

_scheduler = None


@app.on_event("startup")
async def startup_checks():
    global _scheduler
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

    # Start Beat Reporter daily scheduler (7am cron)
    from backend.agents.beat_reporter import setup_scheduler
    _scheduler = setup_scheduler()
    _scheduler.start()
    logger.info("Beat Reporter scheduler started (daily at 7am)")


@app.on_event("shutdown")
async def shutdown_checks():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Beat Reporter scheduler stopped")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "local")[:8],
    }


@app.websocket("/ws/news")
async def news_websocket(websocket: WebSocket):
    """Live push of new beat reporter signals."""
    await news_ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        news_ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Frontend static file serving (production — single Railway service)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Serve /assets (JS, CSS bundles)
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/favicon.svg")
    async def favicon():
        return FileResponse(FRONTEND_DIST / "favicon.svg")

    @app.get("/icons.svg")
    async def icons():
        return FileResponse(FRONTEND_DIST / "icons.svg")

    # Catch-all: serve index.html for any non-API route
    # (React Router handles client-side routing)
    _API_PREFIXES = (
        "admin", "assistant", "auth", "draft", "draftboard",
        "league", "news", "pipeline", "players", "preferences",
        "teams", "health", "docs", "openapi.json", "redoc",
        "ws/", "api/",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path and any(full_path.startswith(p) for p in _API_PREFIXES):
            raise HTTPException(status_code=404)
        return FileResponse(FRONTEND_DIST / "index.html")

else:
    @app.get("/")
    async def root():
        return {"status": "ok", "message": "API running — no frontend build found"}
