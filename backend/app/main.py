import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from backend.app.config import settings
from backend.app.db.database import engine, Base
import backend.app.db.models  # Ensure all SQLAlchemy models are registered
from backend.app.api.webhooks import router as webhooks_router
from backend.app.api.approvals import router as approvals_router
from backend.app.api.auth import router as auth_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.logs import router as logs_router
from backend.app.api.desktop import router as desktop_router
from backend.app.api.whatsapp import router as whatsapp_router
from backend.app.api.skills import router as skills_router
from backend.app.api.linking import router as linking_router
from backend.app.api.archive import router as archive_router
from backend.app.api.outbox import router as outbox_router
from backend.app.api.privacy import router as privacy_router
from backend.app.security.payload_limit import RequestSizeLimitMiddleware
from backend.app.security.rate_limiter import rate_limiter, extract_client_ip


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: automatically initialize database tables on startup."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"[Warning] Database auto-creation failed (check connection): {e}")
    yield


# In production, disable interactive docs and schemas to obscure API from scanners
docs_url = None if settings.is_production else "/docs"
redoc_url = None if settings.is_production else "/redoc"
openapi_url = None if settings.is_production else "/openapi.json"

app = FastAPI(
    title="DUIT API",
    description="Deterministic 4-stage cascade for fast, cheap, safe AI scheduling & email assistance.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url
)

# CORS Middleware
cors_origins = list(settings.CORS_ORIGINS) if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
if "https://yuvraj707sharma.github.io" not in cors_origins:
    cors_origins.append("https://yuvraj707sharma.github.io")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=5 * 1024 * 1024)


@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    """Enforces sliding-window rate limits across IP, User, Account, and Device dimensions."""
    path = request.url.path
    # Exclude internal / health / doc endpoints from rate limiting
    if path.startswith(("/health", "/docs", "/redoc", "/openapi.json")):
        return await call_next(request)

    client_ip = extract_client_ip(request)
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")
    account_id = request.headers.get("x-account-id")
    device_id = request.headers.get("x-device-id")

    try:
        rate_limiter.enforce(
            client_ip=client_ip,
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=account_id,
            device_id=device_id
        )
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
            headers=exc.headers
        )

    return await call_next(request)


# Include API routers
app.include_router(webhooks_router)
app.include_router(approvals_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(logs_router)
app.include_router(desktop_router)
app.include_router(whatsapp_router)
app.include_router(skills_router)
app.include_router(linking_router)
app.include_router(archive_router)
app.include_router(outbox_router)
app.include_router(privacy_router)


@app.get("/", status_code=404)
async def root():
    """Hides backend root from bots, scanners, and unauthorized visitors with a generic 404 response."""
    return HTMLResponse(
        content="""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>404 Not Found</title>
</head><body style="background:#ffffff;color:#000000;font-family:sans-serif;padding:30px;">
<h1>404 Not Found</h1>
<p>The requested URL was not found on this server.</p>
<hr>
<address>Apache/2.4.52 Server</address>
</body></html>""",
        status_code=404
    )


from pydantic import BaseModel
from sqlalchemy import select
from backend.app.db.database import engine, Base, AsyncSessionLocal
from backend.app.db.models import BetaRegistration


class WaitlistPayload(BaseModel):
    email: str
    phone: str


@app.post("/api/waitlist")
async def join_beta_waitlist(payload: WaitlistPayload):
    """Collects early access requests for whitelist approval."""
    clean_email = payload.email.strip().lower()
    clean_phone = payload.phone.strip()

    if not clean_email or "@" not in clean_email or "." not in clean_email:
        return JSONResponse(status_code=400, content={"error": "Please provide a valid Gmail address."})

    if not clean_phone or len(clean_phone) < 8:
        return JSONResponse(status_code=400, content={"error": "Please provide a valid WhatsApp number."})

    for attempt in range(2):
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(BetaRegistration).where(BetaRegistration.email == clean_email)
                res = await session.execute(stmt)
                existing = res.scalars().first()

                if existing:
                    return {
                        "status": "already_registered",
                        "message": "You are already on the beta waitlist! We are reviewing accounts and will notify you soon."
                    }

                entry = BetaRegistration(
                    email=clean_email,
                    phone_number=clean_phone,
                    status="pending"
                )
                session.add(entry)
                await session.commit()

            return {
                "status": "success",
                "message": "Registration received! We will whitelist your Gmail in Google Workspace and reach out on WhatsApp."
            }
        except Exception as e:
            if attempt == 0:
                # Table might not exist yet; auto-initialize tables and retry
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            else:
                return JSONResponse(status_code=500, content={"error": "Could not save registration. Please try again."})


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
    import time
    start_db = time.perf_counter()
    db_status = "ok"
    try:
        from backend.app.db.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"
    db_latency_ms = round((time.perf_counter() - start_db) * 1000, 2)

    from backend.app.desktop.presence import presence_manager
    active_desktops = len(presence_manager._connections)

    llm_status = "live" if (settings.meta_api_key or settings.GEMINI_API_KEY) and not settings.USE_MOCK_LLM else "mock"
    router_status = "mock"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "env": settings.APP_ENV,
        "decision_layer": "laya-multilingual",
        "services": {
            "database": {
                "status": db_status,
                "latency_ms": db_latency_ms
            },
            "llm_provider": {
                "active": settings.DEFAULT_LLM_PROVIDER,
                "status": llm_status
            },
            "decision_router": router_status,
            "google_oauth": "configured" if bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET) else "unconfigured",
            "gateway_auth": "configured" if bool(settings.GATEWAY_SHARED_SECRET) else "missing",
            "active_desktop_connections": active_desktops
        }
    }


@app.get("/api/health/ready")
async def readiness_probe():
    """Readiness probe checking database connectivity, roundtrip latency, and connection pool state."""
    import time
    from sqlalchemy import text
    from backend.app.db.database import engine

    start_time = time.perf_counter()
    db_status = "ok"
    error_msg = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "unreachable"
        error_msg = str(exc)

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    pool = getattr(engine, "sync_engine", engine).pool
    pool_stats = {
        "size": getattr(pool, "size", lambda: 0)(),
        "checked_in": getattr(pool, "checkedin", lambda: 0)(),
        "checked_out": getattr(pool, "checkedout", lambda: 0)(),
        "overflow": getattr(pool, "overflow", lambda: 0)()
    }

    is_ready = db_status == "ok"
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "database": {
                "status": db_status,
                "latency_ms": latency_ms,
                "error": error_msg,
                "pool": pool_stats
            }
        }
    )
