"""Per-stage Latency & Telemetry Metrics Endpoint."""
from fastapi import APIRouter
from backend.app.metrics import metrics_collector
from backend.app.observability.metrics import telemetry_collector
from backend.app.observability.alerts import alert_manager

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("")
async def get_metrics():
    """Exposes real-time per-stage latency timings and token/cost savings."""
    return metrics_collector.get_summary()


@router.get("/telemetry")
async def get_telemetry():
    """Exposes OpenTelemetry-compatible latency percentiles, error counters, and queue metrics."""
    return telemetry_collector.get_snapshot()


@router.get("/alerts")
async def get_alerts():
    """Exposes active operational alert conditions including delivery spikes and auth failures."""
    return alert_manager.evaluate_alerts()
