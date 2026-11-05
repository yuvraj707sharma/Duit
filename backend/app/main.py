import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.app.config import settings
from backend.app.api.webhooks import router as webhooks_router
from backend.app.api.approvals import router as approvals_router
from backend.app.api.auth import router as auth_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.logs import router as logs_router
from backend.app.api.desktop import router as desktop_router
from backend.app.api.whatsapp import router as whatsapp_router
from backend.app.api.skills import router as skills_router

app = FastAPI(
    title="DUIT API",
    description="Deterministic 4-stage cascade for fast, cheap, safe AI scheduling & email assistance.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for landing page and branding assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include API routers
app.include_router(webhooks_router)
app.include_router(approvals_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(logs_router)
app.include_router(desktop_router)
app.include_router(whatsapp_router)
app.include_router(skills_router)


@app.get("/")
async def root():
    """Serves the DUIT landing page for users and beta testers."""
    landing_path = os.path.join(static_dir, "index.html")
    if os.path.exists(landing_path):
        return FileResponse(landing_path, media_type="text/html")
    return {
        "app": "DUIT",
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/download/DUITDesktop.exe")
async def download_desktop_app():
    """Download route for the standalone Windows desktop application binary."""
    exe_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dist", "DUITDesktop.exe"))
    if os.path.exists(exe_path):
        return FileResponse(
            exe_path,
            media_type="application/vnd.microsoft.portable-executable",
            filename="DUITDesktop.exe"
        )
    return JSONResponse(
        status_code=404,
        content={"error": "DUITDesktop.exe is currently compiling or not found."}
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "env": settings.APP_ENV,
        "decision_layer": "laya-multilingual"
    }
