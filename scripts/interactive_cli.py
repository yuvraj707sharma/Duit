"""Interactive CLI Chat to test FastAgent locally on your laptop."""
import asyncio
import sys
import time
from pathlib import Path

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.cascade.decision import MockDecisionModel
from backend.app.channels.mock import MockChannel
from backend.app.learning.log import learning_logger
from eval.bench_routers import EmbedRouterWrapper


async def main():
    print("=" * 70)
    print("🤖  FastAgent Interactive Laptop Testing Session")
    print("=" * 70)
    print("Choose your decision router:")
    print("  1. Embed Router (Fast ML: Sentence/TF-IDF + LogisticRegression) [Recommended]")
    print("  2. Mock Router (Deterministic rules & Hindi/Hinglish patterns)")
    print("=" * 70)

    choice = input("Enter choice (1 or 2, default 1): ").strip() or "1"

    if choice == "1":
        train_path = Path(__file__).parent.parent / "eval" / "dataset" / "train.jsonl"
        decision_model = EmbedRouterWrapper(train_path=train_path)
        router_name = "Embed ML Router"
    else:
        decision_model = MockDecisionModel()
        router_name = "Mock Rule Router"

    mock_channel = MockChannel()
    orch = CascadeOrchestrator(
        decision_model=decision_model,
        messaging_channel=mock_channel
    )

    user_id = "+919876543210"
    print(f"\n>> Router active: {router_name}")
    print(f">> Simulated User Channel ID: {user_id}")
    print("\n💡 Try typing:")
    print("  • 'Schedule a sync with Rahul tomorrow at 4pm'")
    print("  • 'Kal subah 10 baje Amit ke saath meeting fix kar do'")
    print("  • 'Don\\'t cancel my 3pm, but move my 5pm to 6pm'")
    print("  • 'Summarize my unread emails'")
    print("  • 'Send an email to alex@example.com with budget'")
    print("  • 'yes' / 'no' (to confirm or reject pending actions)")
    print("  • 'stop all' / 'ruk jao' (emergency halt)")
    print("  • 'exit' / 'quit' (to end session)")
    print("-" * 70)

    while True:
        try:
            user_input = input("\nYou > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("\n👋 Ending session. Have a great day!")
                break

            t0 = time.perf_counter()
            resp = await orch.handle_message(
                user_id=user_id,
                message_text=user_input
            )
            total_dt_ms = (time.perf_counter() - t0) * 1000.0

            print(f"\n[Agent Response] ({total_dt_ms:.1f}ms total)")
            print(f"Status:     {resp.status.upper()}")
            print(f"Intent:     {resp.intent}")
            print(f"Risk:       {resp.risk}")
            print(f"Confidence: {resp.confidence:.2f}")

            if resp.stage_latencies_ms:
                lat_str = ", ".join(f"{k}: {v:.1f}ms" for k, v in resp.stage_latencies_ms.items())
                print(f"Latencies:  {lat_str}")

            print(f"\nMessage:    {resp.response_text}")

            if resp.tool_result:
                print(f"Tool Data:  {resp.tool_result}")

            # Check if a confirmation prompt was sent to the channel
            if mock_channel.confirmation_prompts:
                last_prompt = mock_channel.confirmation_prompts[-1]
                print(f"\n⚠️  [Pending Confirmation Sent to User]:")
                print(last_prompt["text"])

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Session ended.")
            break


if __name__ == "__main__":
    asyncio.run(main())
