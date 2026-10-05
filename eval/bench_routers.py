"""Benchmark router accuracy, latency, and calibration across router backends (Laya, Embed, Mock, LLM)."""
import argparse
import asyncio
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import psutil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from backend.app.cascade.decision import MockDecisionModel, LayaDecisionModel, DecisionOutput
from backend.app.policy.confirmations import INTENT_RISK_MAP
from backend.app.llm.mock import MockLLMProvider


class DirectLayaRouterWrapper:
    """Wrapper that calls native Laya Router directly in-process with threadpool execution."""
    def __init__(self, use_single_question: bool = True, default_model: str = "english", preload: bool = False):
        self.use_single_question = use_single_question
        self.default_model = default_model
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        sys.path.insert(0, str(Path(__file__).parent.parent / "laya"))
        from laya.router import Router
        print(f">> Initializing native in-process Laya Router (default={default_model}, preload={preload})...")
        self.native_router = Router(default=default_model, preload=preload)

    async def decide(self, message: str) -> DecisionOutput:
        # Question definition
        questions = {
            "intent": {
                "type": "choice",
                "instructions": "Classify the user intent into one of the available choices.",
                "criteria": {
                    "schedule_meeting": "Create a new meeting or calendar event",
                    "reschedule_meeting": "Move, change time, or reschedule an existing meeting",
                    "cancel_meeting": "Delete or cancel a meeting",
                    "check_calendar": "Check schedule, availability, or free slots",
                    "reply_email": "Reply to or answer an existing email",
                    "summarize_email": "Summarize unread emails or inbox",
                    "send_email": "Draft or send a new email",
                    "book_something": "Book a ticket, restaurant, or ride",
                    "other": "General conversation or other requests"
                }
            }
        }
        if not self.use_single_question:
            questions["risk"] = {
                "type": "choice",
                "instructions": "Classify the risk level of this operation.",
                "criteria": {
                    "low": "Read-only actions or queries",
                    "medium": "Standard scheduling updates or draft emails",
                    "high": "Cancellations, external sends, financial bookings"
                }
            }

        # Run blocking inference in worker thread to prevent blocking event loop
        res = await asyncio.to_thread(self.native_router.system_one, message, questions)
        answers = res.get("answers", {})
        intent_ans = answers.get("intent", {})
        
        intent = intent_ans.get("choice", "other")
        conf = float(intent_ans.get("confidence", 0.0))

        # If single question mode: derive risk in code from INTENT_RISK_MAP
        if self.use_single_question:
            risk, needs_conf_base = INTENT_RISK_MAP.get(intent, ("low", False))
            needs_conf = needs_conf_base or risk in ("medium", "high") or conf < 0.75
        else:
            risk_ans = answers.get("risk", {})
            risk = risk_ans.get("choice", "medium")
            needs_conf = (risk in ("medium", "high") or conf < 0.75)

        routing_info = res.get("routing", {})
        checkpoint_used = routing_info.get("model", self.default_model)

        return DecisionOutput(
            intent=intent,
            risk=risk,
            needs_confirmation=needs_conf,
            confidence=conf,
            detected_language=routing_info.get("reason", "multilingual"),
            model_used=f"laya-{checkpoint_used}",
            reasoning_tag=f"laya_checkpoint:{checkpoint_used}"
        )


class EmbedRouterWrapper:
    """Multilingual character/word n-gram TF-IDF + LogisticRegression head."""
    def __init__(self, train_path: Path):
        print(f">> Training EmbedRouter on {train_path}...")
        with open(train_path, "r", encoding="utf-8") as f:
            train_samples = [json.loads(line) for line in f if line.strip()]

        X_train = [s["text"] for s in train_samples]
        y_train = [s["expected_intent"] for s in train_samples]

        self.pipeline = make_pipeline(
            TfidfVectorizer(ngram_range=(1, 3), analyzer="char_wb", min_df=1),
            LogisticRegression(max_iter=500, C=10.0)
        )
        self.pipeline.fit(X_train, y_train)
        print(f">> EmbedRouter trained successfully on {len(X_train)} samples across {len(set(y_train))} classes.")

    async def decide(self, message: str) -> DecisionOutput:
        # Pre-fitted model inference in threadpool
        def _predict():
            probs = self.pipeline.predict_proba([message])[0]
            classes = self.pipeline.classes_
            best_idx = np.argmax(probs)
            intent = classes[best_idx]
            conf = float(probs[best_idx])
            return intent, conf

        intent, conf = await asyncio.to_thread(_predict)
        risk, needs_conf_base = INTENT_RISK_MAP.get(intent, ("low", False))

        return DecisionOutput(
            intent=intent,
            risk=risk,
            needs_confirmation=(needs_conf_base or risk in ("medium", "high") or conf < 0.75),
            confidence=conf,
            detected_language="multilingual",
            model_used="embed-tfidf-logreg",
            reasoning_tag="embed_logistic_regression"
        )


class LLMOnlyRouterWrapper:
    """Wrapper that prompts an LLM provider for intent classification."""
    def __init__(self):
        self.provider = MockLLMProvider()

    async def decide(self, message: str) -> DecisionOutput:
        schema = {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "schedule_meeting", "reschedule_meeting", "cancel_meeting",
                        "check_calendar", "reply_email", "summarize_email",
                        "send_email", "book_something", "other"
                    ]
                }
            },
            "required": ["intent"]
        }
        res = await self.provider.extract_arguments(message, "intent_classification", schema)
        intent = res.arguments.get("intent", "other") if res.success else "other"
        risk, needs_conf_base = INTENT_RISK_MAP.get(intent, ("low", False))
        return DecisionOutput(
            intent=intent,
            risk=risk,
            needs_confirmation=needs_conf_base,
            confidence=0.88 if res.success else 0.40,
            detected_language="en",
            model_used="llm-only",
            reasoning_tag="llm_extraction_intent"
        )


def get_system_specs() -> Dict[str, Any]:
    ram = psutil.virtual_memory()
    return {
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "ram_total_gb": round(ram.total / (1024 ** 3), 2),
        "ram_available_gb": round(ram.available / (1024 ** 3), 2),
        "os": f"{platform.system()} {platform.release()}"
    }


async def run_benchmark(router_type: str, dataset_path: Path, train_path: Path, single_q: bool = True):
    specs = get_system_specs()

    print("=" * 75)
    print(">> FastAgent Router Benchmark Suite")
    print(f">> Active Router:    {router_type.upper()}")
    print(f">> Question Mode:    {'Single Question (Intent Only - Risk in Code)' if single_q else 'Two Questions (Intent + Risk)'}")
    print(f">> Host Platform:    {specs['os']}")
    print(f">> CPU Specs:        {specs['cpu']} ({specs['cpu_cores_logical']} logical cores)")
    print(f">> System RAM:       {specs['ram_available_gb']} GB available / {specs['ram_total_gb']} GB total")
    print(f">> Dataset Path:     {dataset_path}")
    if "synthetic" in str(dataset_path).lower():
        print(">> [SYNTHETIC DATASET] Note: Loaded dataset is synthetic development data.")

    if router_type == "mock":
        print(">> [NOTICE] Running MOCK baseline router (deterministic rules). This is NOT model accuracy.")
        model = MockDecisionModel()
    elif router_type == "laya":
        print(">> Running REAL LAYA router on native CPU/host (threadpool async).")
        model = DirectLayaRouterWrapper(use_single_question=single_q)
    elif router_type == "embed":
        print(">> Running EMBED router (Sentence/TF-IDF vectorizer + Logistic Regression).")
        model = EmbedRouterWrapper(train_path=train_path)
    elif router_type == "llm-only":
        print(">> Running LLM-ONLY intent router.")
        model = LLMOnlyRouterWrapper()
    else:
        raise ValueError(f"Unknown router type: {router_type}")

    print("=" * 75)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found at {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()]

    total = len(samples)
    correct = 0
    latencies: List[float] = []
    by_lang: Dict[str, Dict[str, int]] = {}
    checkpoints_served: Dict[str, int] = {}
    hinglish_predictions = []

    for item in samples:
        text = item["text"]
        expected = item["expected_intent"]
        lang = item.get("language", "en")

        if lang not in by_lang:
            by_lang[lang] = {"total": 0, "correct": 0}
        by_lang[lang]["total"] += 1

        t0 = time.perf_counter()
        res = await model.decide(text)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

        is_correct = (res.intent == expected)
        if is_correct:
            correct += 1
            by_lang[lang]["correct"] += 1

        ckpt = res.model_used
        checkpoints_served[ckpt] = checkpoints_served.get(ckpt, 0) + 1

        if lang in ("hi-Latn", "hi"):
            hinglish_predictions.append({
                "text": text,
                "expected": expected,
                "predicted": res.intent,
                "checkpoint": res.model_used,
                "confidence": res.confidence,
                "correct": is_correct
            })

        status_marker = "[PASS]" if is_correct else "[FAIL]"
        print(f"{status_marker} [{lang:<7}] '{text[:34]:<34}' -> Predicted: {res.intent:<18} (Ckpt: {res.model_used}, Conf: {res.confidence:.2f}, Latency: {dt_ms:.1f}ms)")

    accuracy = (correct / total) * 100.0 if total > 0 else 0.0
    latencies_sorted = sorted(latencies)
    p50_latency = latencies_sorted[int(len(latencies_sorted) * 0.50)] if latencies else 0.0
    p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies else 0.0
    p99_latency = latencies_sorted[int(len(latencies_sorted) * 0.99)] if latencies else 0.0
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    print("\n" + "=" * 75)
    print(f"BENCHMARK RESULTS: {router_type.upper()}")
    print(f"- Router Under Test:    {router_type}")
    print(f"- Total Samples:        {total}")
    print(f"- Overall Accuracy:     {accuracy:.2f}% ({correct}/{total})")
    for lang, stats in by_lang.items():
        lang_acc = (stats["correct"] / stats["total"]) * 100.0 if stats["total"] > 0 else 0.0
        print(f"- {lang:<7} Accuracy:    {lang_acc:.1f}% ({stats['correct']}/{stats['total']})")
    print(f"- Checkpoints Served:   {dict(checkpoints_served)}")
    print(f"- p50 Latency:          {p50_latency:.2f} ms")
    print(f"- p95 Latency:          {p95_latency:.2f} ms")
    print(f"- p99 Latency:          {p99_latency:.2f} ms")
    print(f"- Avg Latency:          {avg_latency:.2f} ms")
    print("=" * 75)

    if hinglish_predictions:
        print("\nHINGLISH SAMPLES BREAKDOWN:")
        for hp in hinglish_predictions:
            mark = "[PASS]" if hp["correct"] else "[FAIL]"
            print(f"  {mark} [{hp['checkpoint']}] '{hp['text']}' -> Pred: {hp['predicted']} (Exp: {hp['expected']}, Conf: {hp['confidence']:.2f})")
        print("=" * 75)


def main():
    parser = argparse.ArgumentParser(description="FastAgent Router Benchmark Suite")
    parser.add_argument("--router", choices=["mock", "laya", "embed", "llm-only"], default="mock",
                        help="Router to benchmark (mock | laya | embed | llm-only)")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Path to jsonl test dataset (defaults to eval/dataset/test.jsonl or synthetic_dev.jsonl)")
    parser.add_argument("--train-dataset", type=str, default=None,
                        help="Path to jsonl train dataset (for embed router)")
    parser.add_argument("--two-questions", action="store_true", default=False,
                        help="Ask both intent and risk questions (default is single question intent-only)")

    args = parser.parse_args()

    dataset_path = Path(args.dataset) if args.dataset else (Path(__file__).parent / "dataset" / "test.jsonl")
    if not dataset_path.exists():
        dataset_path = Path(__file__).parent / "dataset" / "synthetic_dev.jsonl"

    train_path = Path(args.train_dataset) if args.train_dataset else (Path(__file__).parent / "dataset" / "train.jsonl")

    asyncio.run(run_benchmark(args.router, dataset_path, train_path, single_q=not args.two_questions))


if __name__ == "__main__":
    main()
