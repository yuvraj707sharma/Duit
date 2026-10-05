"""FastAgent Stage Latency & Metrics Tracking."""
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from collections import defaultdict


class MetricsCollector:
    def __init__(self):
        self.stage_timings: Dict[str, list] = defaultdict(list)
        self.request_counts: Dict[str, int] = defaultdict(int)
        self.intent_counts: Dict[str, int] = defaultdict(int)
        self.total_tokens_saved: int = 0
        self.total_cost_saved_usd: float = 0.0
        self.decision_errors: int = 0

    def record_decision_error(self):
        self.decision_errors += 1

    def record_stage_latency(self, stage_name: str, duration_ms: float):
        # Keep last 1000 records for stats
        timings = self.stage_timings[stage_name]
        if len(timings) >= 1000:
            timings.pop(0)
        timings.append(duration_ms)

    def record_intent(self, intent: str):
        self.intent_counts[intent] += 1
        self.request_counts["total"] += 1

    def record_token_savings(self, input_chars: int):
        # Average LLM call avoided = ~500 tokens
        self.total_tokens_saved += 500
        # Average saved cost at $0.50 / 1M tokens = ~$0.00025 per avoid
        self.total_cost_saved_usd += 0.00025

    def get_summary(self) -> Dict[str, Any]:
        summary = {
            "total_requests": self.request_counts["total"],
            "decision_errors": self.decision_errors,
            "intent_distribution": dict(self.intent_counts),
            "tokens_saved": self.total_tokens_saved,
            "cost_saved_usd": round(self.total_cost_saved_usd, 4),
            "stage_latencies_ms": {}
        }
        for stage, times in self.stage_timings.items():
            if times:
                summary["stage_latencies_ms"][stage] = {
                    "avg": round(sum(times) / len(times), 2),
                    "p50": round(sorted(times)[len(times) // 2], 2),
                    "p95": round(sorted(times)[int(len(times) * 0.95)], 2),
                    "p99": round(sorted(times)[int(len(times) * 0.99)], 2),
                    "min": round(min(times), 2),
                    "max": round(max(times), 2),
                    "count": len(times)
                }
            else:
                summary["stage_latencies_ms"][stage] = {"avg": 0.0, "count": 0}
        return summary


metrics_collector = MetricsCollector()


class StageTimer:
    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.start_time: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        metrics_collector.record_stage_latency(self.stage_name, duration_ms)
