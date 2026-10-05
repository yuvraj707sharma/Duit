"""Evaluates empirical test accuracy vs number of user corrections (N = 0, 5, 10, 20, 40) using kNN semantic memory."""
import asyncio
import json
import sys
from pathlib import Path

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.learning.knn import knn_retriever
from backend.app.learning.log import learning_logger
from backend.app.learning.thresholds import threshold_calibrator
from backend.app.cascade.decision import MockDecisionModel

TEST_PATH = Path(__file__).parent / "dataset" / "test.jsonl"
if not TEST_PATH.exists():
    TEST_PATH = Path(__file__).parent / "dataset" / "synthetic_dev.jsonl"

TRAIN_PATH = Path(__file__).parent / "dataset" / "train.jsonl"


async def evaluate_learning_curve():
    print("=" * 80)
    print(">> FastAgent Active Learning Curve Evaluation (kNN Semantic Correction Loop)")
    print("=" * 80)
    print(f"Test Dataset:   {TEST_PATH} (held-out test split)")
    print(f"Train Dataset:  {TRAIN_PATH} (source of logged corrections)")
    print("Method: Base router augmented with kNN semantic retrieval over user corrections.")
    print("=" * 80)

    # 1. Load test and train datasets
    with open(TEST_PATH, "r", encoding="utf-8") as f:
        test_samples = [json.loads(line) for line in f if line.strip()]

    with open(TRAIN_PATH, "r", encoding="utf-8") as f:
        train_samples = [json.loads(line) for line in f if line.strip()]

    total_test = len(test_samples)
    base_model = MockDecisionModel()
    user_id = "eval_active_learner_user"

    print(f"{'Corrections (N)':<16} | {'Logged Corrections':<18} | {'Auto-Approve Thresh':<20} | {'Test Accuracy':<16}")
    print("-" * 80)

    accuracies = []
    correction_steps = [0, 5, 10, 20, 40]

    for n_target in correction_steps:
        # Reset and populate memory with exactly first n_target corrections from train.jsonl
        knn_retriever.clear()
        learning_logger._records = [r for r in learning_logger._records if r.user_id != user_id]

        target_train_slice = train_samples[:n_target]
        for item in target_train_slice:
            learning_logger.log_correction(
                user_id=user_id,
                query_text=item["text"],
                predicted_intent=item["expected_intent"],
                user_action="approve",
                corrected_intent=item["expected_intent"]
            )

        # Compute dynamic threshold
        thresh = threshold_calibrator.calculate_threshold(user_id, "schedule_meeting")
        thresh_str = f"{thresh:.2f}" if thresh is not None else "None (Safe Gate)"

        # Evaluate combined pipeline (kNN semantic memory -> base router)
        correct_count = 0
        knn_hits = 0

        for sample in test_samples:
            knn_res = knn_retriever.find_nearest_correction(user_id, sample["text"])
            if knn_res is not None:
                predicted_intent = knn_res[0]
                knn_hits += 1
            else:
                base_out = await base_model.decide(sample["text"])
                predicted_intent = base_out.intent

            if predicted_intent == sample["expected_intent"]:
                correct_count += 1

        acc_pct = (correct_count / total_test) * 100.0
        accuracies.append(acc_pct)
        logged_cnt = len(learning_logger.get_records_for_user(user_id))

        print(f"{n_target:<16} | {logged_cnt:<18} | {thresh_str:<20} | {acc_pct:.1f}% ({correct_count}/{total_test}) [kNN matches: {knn_hits}]")

    print("=" * 80)
    delta_acc = accuracies[-1] - accuracies[0]
    if delta_acc > 0:
        print(f"Summary: Test accuracy improved from {accuracies[0]:.1f}% to {accuracies[-1]:.1f}% (+{delta_acc:.1f}%) as corrections scaled.")
    elif delta_acc < 0:
        print(f"Summary: Test accuracy decreased by {abs(delta_acc):.1f}%.")
    else:
        print(f"Summary: Test accuracy remained steady at {accuracies[0]:.1f}%. (Base model was already optimal or test set has no overlapping failure modes).")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(evaluate_learning_curve())
