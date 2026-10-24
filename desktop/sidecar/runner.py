"""Standalone Desktop Sidecar Agent Runner.
Can be run directly with Python or compiled into a single .exe with PyInstaller.
"""
import sys
import os
import asyncio
import logging

# Ensure current directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from sidecar import DesktopSidecarAgent
from journal import journal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FastAgentDesktopSidecar")


async def main():
    user_id = os.getenv("FASTAGENT_USER_ID", "default_user")
    ws_url = os.getenv("FASTAGENT_WS_URL", "ws://127.0.0.1:8000/api/desktop/ws")
    secret = os.getenv("FASTAGENT_SECRET", "fastagent_desktop_secret_2026_dev")

    print("=" * 60)
    print("FastAgent Local Desktop Sidecar (Windows OS Executor)")
    print(f"User ID:     {user_id}")
    print(f"Gateway WS:  {ws_url}")
    print("=" * 60)

    # 1. Startup WAL crash reconciliation
    reconciled = journal.reconcile_on_startup()
    if reconciled:
        logger.warning("Reconciled %d interrupted/stuck operations from previous crash.", len(reconciled))
    else:
        logger.info("WAL journal healthy. Zero interrupted actions.")

    # 2. Launch Sidecar connection loop
    agent = DesktopSidecarAgent(
        user_id=user_id,
        backend_ws_url=ws_url,
        shared_secret=secret
    )

    try:
        await agent.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down Desktop Sidecar Agent gracefully.")
        await agent.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
