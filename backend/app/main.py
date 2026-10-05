from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.api.webhooks import router as webhooks_router
from backend.app.api.approvals import router as approvals_router
from backend.app.api.auth import router as auth_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.logs import router as logs_router

app = FastAPI(
    title="FastAgent API",
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

# Include API routers
app.include_router(webhooks_router)
app.include_router(approvals_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(logs_router)


@app.get("/")
async def root():
    return {
        "app": "FastAgent",
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "env": settings.APP_ENV,
        "decision_layer": "laya-multilingual"
    }
