"""Real-Time Operational Alerts Engine for DUIT."""
from typing import Dict, List, Any
from backend.app.observability.metrics import telemetry_collector


class OperationalAlertManager:
    """Evaluates metrics against operational thresholds to surface actionable alerts."""

    def __init__(self):
        pass

    def evaluate_alerts(self, db_latency_ms: float = 0.0, queue_depth: int = 0) -> List[Dict[str, Any]]:
        """Evaluates operational alert conditions and returns active alerts."""
        snapshot = telemetry_collector.get_snapshot()
        counters = snapshot["counters"]
        active_alerts = []

        # 1. Abnormal pairing attempts
        if counters.get("abnormal_pairing_attempts", 0) >= 5:
            active_alerts.append({
                "alert": "ABNORMAL_PAIRING_ATTEMPTS",
                "severity": "warning",
                "count": counters["abnormal_pairing_attempts"],
                "message": "Multiple abnormal device or WhatsApp pairing attempts detected."
            })

        # 2. Repeated authentication failures
        if counters.get("auth_failures", 0) >= 5:
            active_alerts.append({
                "alert": "REPEATED_AUTH_FAILURES",
                "severity": "critical",
                "count": counters["auth_failures"],
                "message": "High rate of authentication failures detected. Possible brute-force or credential stuffing."
            })

        # 3. Cross-tenant authorization violations
        if counters.get("cross_tenant_errors", 0) >= 1:
            active_alerts.append({
                "alert": "CROSS_TENANT_VIOLATION_DETECTED",
                "severity": "critical",
                "count": counters["cross_tenant_errors"],
                "message": "Security boundary alert: cross-tenant access attempt was blocked."
            })

        # 4. WhatsApp delivery failure spike
        if counters.get("whatsapp_delivery_failures", 0) >= 10:
            active_alerts.append({
                "alert": "WHATSAPP_DELIVERY_FAILURE_SPIKE",
                "severity": "warning",
                "count": counters["whatsapp_delivery_failures"],
                "message": "Outbox delivery failures exceeded threshold. Check Baileys gateway connectivity."
            })

        # 5. Database latency spike
        if db_latency_ms > 500.0:
            active_alerts.append({
                "alert": "DATABASE_LATENCY_SPIKE",
                "severity": "warning",
                "latency_ms": db_latency_ms,
                "message": f"Database roundtrip latency ({db_latency_ms}ms) exceeded 500ms threshold."
            })

        # 6. Delivery queue backlog
        if queue_depth > 50:
            active_alerts.append({
                "alert": "DELIVERY_QUEUE_BACKLOG",
                "severity": "warning",
                "queue_depth": queue_depth,
                "message": f"Outbox event queue depth ({queue_depth}) exceeds backlog threshold."
            })

        return active_alerts


alert_manager = OperationalAlertManager()

