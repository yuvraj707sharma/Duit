"""OpenTelemetry-Compatible Telemetry and Operational Metrics Collector for DUIT."""
import time
import threading
from typing import Dict, List, Any


class TelemetryCollector:
    """Thread-safe metrics accumulator tracking latencies, success rates, and queue states."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ingestion_latencies: List[float] = []
        self._model_latencies: List[float] = []
        self._retrieval_latencies: List[float] = []

        self._tool_calls_total = 0
        self._tool_calls_successful = 0

        self._approvals_created = 0
        self._approvals_converted = 0

        self._whatsapp_delivery_failures = 0
        self._desktop_execution_failures = 0
        self._duplicate_executions = 0
        self._oauth_failures = 0
        self._auth_failures = 0
        self._abnormal_pairing_attempts = 0
        self._cross_tenant_errors = 0

    def record_ingestion_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._ingestion_latencies.append(latency_ms)
            if len(self._ingestion_latencies) > 1000:
                self._ingestion_latencies = self._ingestion_latencies[-500:]

    def record_model_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._model_latencies.append(latency_ms)
            if len(self._model_latencies) > 1000:
                self._model_latencies = self._model_latencies[-500:]

    def record_retrieval_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._retrieval_latencies.append(latency_ms)
            if len(self._retrieval_latencies) > 1000:
                self._retrieval_latencies = self._retrieval_latencies[-500:]

    def record_tool_call(self, success: bool) -> None:
        with self._lock:
            self._tool_calls_total += 1
            if success:
                self._tool_calls_successful += 1

    def record_approval(self, converted: bool = False) -> None:
        with self._lock:
            self._approvals_created += 1
            if converted:
                self._approvals_converted += 1

    def record_delivery_failure(self) -> None:
        with self._lock:
            self._whatsapp_delivery_failures += 1

    def record_desktop_failure(self) -> None:
        with self._lock:
            self._desktop_execution_failures += 1

    def record_duplicate_execution(self) -> None:
        with self._lock:
            self._duplicate_executions += 1

    def record_oauth_failure(self) -> None:
        with self._lock:
            self._oauth_failures += 1

    def record_auth_failure(self) -> None:
        with self._lock:
            self._auth_failures += 1

    def record_abnormal_pairing(self) -> None:
        with self._lock:
            self._abnormal_pairing_attempts += 1

    def record_cross_tenant_error(self) -> None:
        with self._lock:
            self._cross_tenant_errors += 1

    def _calculate_p95(self, samples: List[float]) -> float:
        if not samples:
            return 0.0
        sorted_samples = sorted(samples)
        idx = int(len(sorted_samples) * 0.95)
        return round(sorted_samples[min(idx, len(sorted_samples) - 1)], 2)

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns OpenTelemetry-compatible metrics snapshot."""
        with self._lock:
            ingestion_p95 = self._calculate_p95(self._ingestion_latencies)
            model_p95 = self._calculate_p95(self._model_latencies)
            retrieval_p95 = self._calculate_p95(self._retrieval_latencies)

            tool_success_rate = (
                round(self._tool_calls_successful / self._tool_calls_total, 4)
                if self._tool_calls_total > 0 else 1.0
            )
            approval_conversion_rate = (
                round(self._approvals_converted / self._approvals_created, 4)
                if self._approvals_created > 0 else 0.0
            )

            return {
                "timestamp": time.time(),
                "latencies_p95_ms": {
                    "message_ingestion": ingestion_p95,
                    "model_decision": model_p95,
                    "retrieval": retrieval_p95
                },
                "counters": {
                    "tool_calls_total": self._tool_calls_total,
                    "tool_calls_successful": self._tool_calls_successful,
                    "tool_success_rate": tool_success_rate,
                    "approvals_created": self._approvals_created,
                    "approvals_converted": self._approvals_converted,
                    "approval_conversion_rate": approval_conversion_rate,
                    "whatsapp_delivery_failures": self._whatsapp_delivery_failures,
                    "desktop_execution_failures": self._desktop_execution_failures,
                    "duplicate_execution_count": self._duplicate_executions,
                    "oauth_failures": self._oauth_failures,
                    "auth_failures": self._auth_failures,
                    "abnormal_pairing_attempts": self._abnormal_pairing_attempts,
                    "cross_tenant_errors": self._cross_tenant_errors
                }
            }


telemetry_collector = TelemetryCollector()

