"""Desktop Presence and WebSocket Connection Manager."""
import time
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DesktopPresenceManager:
    def __init__(self, heartbeat_timeout: float = 30.0):
        self.heartbeat_timeout = heartbeat_timeout
        # Map: user_id -> {"socket": WebSocket, "last_heartbeat": float, "connected_at": float}
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._pending_commands: Dict[str, asyncio.Future] = {}

    def register_connection(self, user_id: str, websocket: WebSocket) -> None:
        now = time.time()
        self._connections[user_id] = {
            "socket": websocket,
            "last_heartbeat": now,
            "connected_at": now
        }
        logger.info("Desktop sidecar registered for user %s", user_id)

    def unregister_connection(self, user_id: str, websocket: Optional[WebSocket] = None) -> None:
        rec = self._connections.get(user_id)
        if rec:
            if websocket is None or rec.get("socket") == websocket:
                self._connections.pop(user_id, None)
                logger.info("Desktop sidecar unregistered for user %s", user_id)

    def update_heartbeat(self, user_id: str) -> None:
        rec = self._connections.get(user_id)
        if rec:
            rec["last_heartbeat"] = time.time()

    def is_online(self, user_id: str) -> bool:
        rec = self._connections.get(user_id)
        if not rec and ("default_user" in self._connections or len(self._connections) == 1):
            rec = self._connections.get("default_user") or next(iter(self._connections.values()), None)
        if not rec:
            return False
        elapsed = time.time() - rec.get("last_heartbeat", 0.0)
        return elapsed <= self.heartbeat_timeout

    def get_presence(self, user_id: str) -> Dict[str, Any]:
        rec = self._connections.get(user_id)
        if not rec and ("default_user" in self._connections or len(self._connections) == 1):
            rec = self._connections.get("default_user") or next(iter(self._connections.values()), None)
        if not rec:
            return {
                "user_id": user_id,
                "status": "offline",
                "last_heartbeat": None
            }
        elapsed = time.time() - rec.get("last_heartbeat", 0.0)
        is_active = elapsed <= self.heartbeat_timeout
        return {
            "user_id": user_id,
            "status": "online" if is_active else "offline",
            "last_heartbeat": rec.get("last_heartbeat"),
            "connected_at": rec.get("connected_at")
        }

    async def send_command_to_desktop(
        self,
        user_id: str,
        command_payload: Dict[str, Any],
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Dispatches an action to the user's active desktop sidecar and awaits result."""
        if not self.is_online(user_id):
            return {
                "success": False,
                "status": "offline",
                "error": "laptop offline"
            }

        rec = self._connections.get(user_id)
        if not rec and ("default_user" in self._connections or len(self._connections) == 1):
            rec = self._connections.get("default_user") or next(iter(self._connections.values()), None)

        ws: WebSocket = rec["socket"]
        action_id = command_payload.get("action_id") or f"act_{int(time.time()*1000)}"
        command_payload["action_id"] = action_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_commands[action_id] = fut

        try:
            await ws.send_json({
                "type": "execute_action",
                "payload": command_payload
            })
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {
                "success": False,
                "status": "timeout",
                "error": f"Desktop action '{action_id}' timed out after {timeout}s"
            }
        except Exception as e:
            logger.error("Error sending command to desktop: %s", e)
            return {
                "success": False,
                "status": "failed",
                "error": str(e)
            }
        finally:
            self._pending_commands.pop(action_id, None)

    def handle_command_response(self, action_id: str, result_payload: Dict[str, Any]) -> None:
        fut = self._pending_commands.get(action_id)
        if fut and not fut.done():
            fut.set_result(result_payload)


presence_manager = DesktopPresenceManager()
