"""Warm Latency Matrix Benchmark: Measures warm p50/p95/p99 latency over requests (excluding 5 warmup)."""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.bench_routers import DirectLayaRouterWrapper, EmbedRouterWrapper, get_system_specs

TEST_PROMPTS = [
    "Schedule a meeting with Rahul tomorrow at 4pm",
    "Move my 3pm call to 5pm",
    "Cancel tomorrow's sync with design team",
    "Am I free between 2pm and 4pm today?",
    "Reply yes to Rahul's email about the roadmap",
    "Summarize my unread emails from this morning",
    "Send an email to alex@example.com with the budget sheet",
    "Book an Uber to the airport for 6pm",
    "What is the weather in Delhi today?",
    "Tell me a joke about coding",
]


async def measure_warm_latencies(model_wrapper, num_warmup: int = 5, num_eval: int = 100) -> Tuple[float, float, float, float]:
    # 1. Warmup runs (excluded from measurements)
    for i in range(num_warmup):
        prompt = TEST_PROMPTS[i % len(TEST_PROMPTS)]
        await model_wrapper.decide(prompt)

    # 2. Measured warm evaluation requests
    latencies: List[float] = []
    for i in range(num_eval):
        prompt = TEST_PROMPTS[i % len(TEST_PROMPTS)]
        t0 = time.perf_counter()
        await model_wrapper.decide(prompt)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    avg = sum(latencies) / len(latencies)
    return p50, p95, p99, avg


async def run_latency_matrix(num_warmup: int = 5, num_requests: int = 100):
    specs = get_system_specs()
    print("=" * 85)
    print(f">> FastAgent Latency Benchmark: {num_requests} Warm Requests Matrix (Excluding {num_warmup} Warmup)")
    print(f">> Host CPU:  {specs['cpu']} ({specs['cpu_cores_logical']} logical cores)")
    print(f">> System RAM: {specs['ram_available_gb']} GB available / {specs['ram_total_gb']} GB total")
    print("=" * 85)

    results = []

    # 1. Embed Classifier (1 Question)
    print(f">> Benchmarking Embed Classifier (1-Question, {num_requests} requests)...")
    train_path = Path(__file__).parent / "dataset" / "train.jsonl"
    embed_model = EmbedRouterWrapper(train_path=train_path)
    p50, p95, p99, avg = await measure_warm_latencies(embed_model, num_warmup, num_requests)
    results.append({
        "configuration": "Embed Classifier (TF-IDF + LogReg)",
        "questions": "1-Question (Intent only)",
        "runtime": "scikit-learn / CPU",
        "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "avg_ms": avg
    })

    # 2. PyTorch fp32 Laya (1 Question - Intent Only)
    print(f">> Benchmarking PyTorch fp32 Laya (1-Question Intent Only, {num_requests} requests)...")
    laya_1q = DirectLayaRouterWrapper(use_single_question=True, preload=False)
    p50, p95, p99, avg = await measure_warm_latencies(laya_1q, num_warmup, num_requests)
    results.append({
        "configuration": "PyTorch fp32 Laya (convaiinnovations/laya)",
        "questions": "1-Question (Intent only)",
        "runtime": "PyTorch CPU",
        "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "avg_ms": avg
    })

    # 3. PyTorch fp32 Laya (2 Questions - Intent + Risk)
    print(f">> Benchmarking PyTorch fp32 Laya (2-Questions Intent + Risk, {num_requests} requests)...")
    laya_2q = DirectLayaRouterWrapper(use_single_question=False, preload=False)
    p50, p95, p99, avg = await measure_warm_latencies(laya_2q, num_warmup, num_requests)
    results.append({
        "configuration": "PyTorch fp32 Laya (convaiinnovations/laya)",
        "questions": "2-Questions (Intent + Risk)",
        "runtime": "PyTorch CPU",
        "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "avg_ms": avg
    })

    # Output Latency Table
    print("\n" + "=" * 95)
    print(f"{'Configuration':<38} | {'Questions':<22} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'p99 (ms)':<10}")
    print("-" * 95)
    for r in results:
        print(f"{r['configuration']:<38} | {r['questions']:<22} | {r['p50_ms']:<10.2f} | {r['p95_ms']:<10.2f} | {r['p99_ms']:<10.2f}")
    print("=" * 95)
    print("Note on ONNX INT8: Laya ModernBERT split architecture export requires custom onnxscript graph export.")


def main():
    parser = argparse.ArgumentParser(description="FastAgent Warm Latency Benchmark Matrix")
    parser.add_argument("--num-requests", type=int, default=20,
                        help="Number of warm evaluation requests (default: 20 for quick run, >=100 for full matrix)")
    parser.add_argument("--num-warmup", type=int, default=5,
                        help="Number of warmup requests to exclude (default: 5)")
    args = parser.parse_args()

    asyncio.run(run_latency_matrix(num_warmup=args.num_warmup, num_requests=args.num_requests))


if __name__ == "__main__":
    main()
