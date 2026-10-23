"""Python Desktop Sidecar Agent: Outbound WebSocket client, heartbeats, journal & kill-switch."""
import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional
import aiohttp

from backend.app.config import settings
from backend.app.desktop.skills import skill_executor, SkillValidationError
from backend.app.desktop.journal import journal, WriteAheadJournal
from backend.app.desktop.context_store import context_store, ContextStore

logger = logging.getLogger(__name__)


class DesktopSidecarAgent:
    def __init__(
        self,
        user_id: str = "default_user",
        backend_ws_url: Optional[str] = None,
        shared_secret: Optional[str] = None,
        journal_instance: Optional[WriteAheadJournal] = None,
        context_store_instance: Optional[ContextStore] = None
    ):
        self.user_id = user_id
        self.backend_ws_url = backend_ws_url or f"ws://localhost:{settings.PORT}/api/desktop/ws"
        self.shared_secret = shared_secret or settings.DESKTOP_SHARED_SECRET
        self.journal = journal_instance or journal
        self.context_store = context_store_instance or context_store
        
        self.is_running = False
        self.kill_switch_active = False
        self._current_task: Optional[asyncio.Task] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

    def trigger_kill_switch(self) -> Dict[str, Any]:
        """Global Kill-Switch: Immediately aborts any running desktop task and sets kill switch flag."""
        self.kill_switch_active = True
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        logger.warning("Global Kill-Switch triggered! All active desktop operations aborted.")
        return {"success": True, "kill_switch_active": True, "message": "Kill-switch activated. Operations aborted."}

    def reset_kill_switch(self) -> None:
        self.kill_switch_active = False

    async def execute_action_safely(self, action_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single desktop action with WAL journaling, TTL verification, and kill-switch checks.
        """
        action_id = action_payload.get("action_id") or f"act_{int(time.time()*1000)}"
        intent = action_payload.get("intent", "")
        args = action_payload.get("arguments", {})
        is_read_only = skill_executor.is_read_only(intent)
        is_voice = bool(action_payload.get("is_voice", False))
        idempotency_key = args.get("idempotency_key") or action_id
        created_at = action_payload.get("created_at", time.time())

        # 1. Record 'received' in WAL journal
        self.journal.record_received(
            action_id=action_id,
            user_id=self.user_id,
            intent=intent,
            arguments=args,
            is_read_only=is_read_only,
            is_voice_command=is_voice,
            idempotency_key=idempotency_key,
            created_at=created_at
        )

        # 2. Check TTL (30s voice / 5m confirmation)
        if self.journal.check_ttl_expired(action_id):
            return {
                "success": False,
                "action_id": action_id,
                "status": "expired",
                "error": "Action expired: TTL exceeded before execution."
            }

        # 3. Check Kill Switch
        if self.kill_switch_active:
            self.journal.transition_state(action_id, "interrupted", error_message="Aborted by kill-switch")
            return {
                "success": False,
                "action_id": action_id,
                "status": "interrupted",
                "error": "Action blocked: Global kill-switch is active."
            }

        # 4. Invariant: Write 'started' with fsync BEFORE executing
        self.journal.transition_state(action_id, "started")

        # 5. Execute skill
        try:
            if intent == "clear_history":
                res = self.context_store.clear_history()
            else:
                res = skill_executor.execute_skill(intent, args)

            # Check if kill switch was triggered during execution
            if self.kill_switch_active:
                self.journal.transition_state(action_id, "interrupted", error_message="Aborted by kill-switch")
                return {
                    "success": False,
                    "action_id": action_id,
                    "status": "interrupted",
                    "error": "Aborted by kill-switch during execution."
                }

            # 6. Write 'completed' to WAL
            self.journal.transition_state(action_id, "completed", result_data=res)
            # 7. Record sanitized metadata to encrypted Context Store
            self.context_store.record_operation(intent, args, status="completed")

            return {
                "success": True,
                "action_id": action_id,
                "status": "completed",
                "result": res
            }

        except SkillValidationError as sve:
            err_msg = f"Validation Error: {sve}"
            self.journal.transition_state(action_id, "failed", error_message=err_msg)
            self.context_store.record_operation(intent, args, status="failed")
            return {
                "success": False,
                "action_id": action_id,
                "status": "failed",
                "error": err_msg
            }
        except asyncio.CancelledError:
            self.journal.transition_state(action_id, "interrupted", error_message="Operation cancelled")
            return {
                "success": False,
                "action_id": action_id,
                "status": "interrupted",
                "error": "Operation was cancelled."
            }
        except Exception as e:
            err_msg = f"Execution Error: {e}"
            self.journal.transition_state(action_id, "failed", error_message=err_msg)
            self.context_store.record_operation(intent, args, status="failed")
            return {
                "success": False,
                "action_id": action_id,
                "status": "failed",
                "error": err_msg
            }

    async def run(self) -> None:
        """Connects outbound to backend WebSocket with automatic reconnection and heartbeat loop."""
        self.is_running = True
        reconciled = self.journal.reconcile_on_startup()
        if reconciled:
            logger.info("Startup reconciliation complete: %d items processed", len(reconciled))

        while self.is_running:
            try:
                ws_target = f"{self.backend_ws_url}?user_id={self.user_id}"
                headers = {"X-Desktop-Secret": self.shared_secret}
                
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_target, headers=headers) as ws:
                        self._ws = ws
                        logger.info("Connected to backend WebSocket at %s", ws_target)

                        # Start heartbeat background task
                        heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                msg_type = data.get("type")

                                if msg_type == "execute_action":
                                    payload = data.get("payload", {})
                                    action_id = payload.get("action_id")
                                    # Execute task
                                    self._current_task = asyncio.create_task(self.execute_action_safely(payload))
                                    res = await self._current_task
                                    # Send back result
                                    await ws.send_json({
                                        "type": "action_result",
                                        "action_id": action_id,
                                        "result": res
                                    })

                                elif msg_type == "kill_switch":
                                    self.trigger_kill_switch()
                                    await ws.send_json({
                                        "type": "kill_switch_ack",
                                        "status": "kill_switch_active"
                                    })

                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break

                        heartbeat_task.cancel()
            except Exception as e:
                logger.warning("Sidecar WebSocket connection error (%s). Reconnecting in 3s...", e)
                await asyncio.sleep(3.0)

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Sends heartbeats every 5 seconds to maintain active presence."""
        while True:
            try:
                await asyncio.sleep(5.0)
                await ws.send_json({
                    "type": "heartbeat",
                    "user_id": self.user_id,
                    "timestamp": time.time()
                })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat error: %s", e)
                break


sidecar_agent = DesktopSidecarAgent()
