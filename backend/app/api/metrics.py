"""Per-stage Latency & Telemetry Metrics Endpoint."""
from fastapi import APIRouter
from backend.app.metrics import metrics_collector

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("")
async def get_metrics():
    """Exposes real-time per-stage latency timings and token/cost savings."""
    return metrics_collector.get_summary()
