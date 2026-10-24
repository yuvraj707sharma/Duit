"""Shed Remote Access Bridge for Desktop Coding Agents (Codex, Claude Code, Gemini, OpenCode)."""
import os
import json
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SHED_BASE_URL = os.environ.get("SHED_BASE_URL", "http://127.0.0.1:4378").rstrip("/")


def get_shed_token() -> str:
    token = os.environ.get("LAYA_TOKEN") or os.environ.get("JEV_TOKEN")
    if token:
        return token.strip()
    token_file = "e:/Inovvate/shed/.laya-token"
    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


class ShedBridge:
    """Interfaces with Shed task plane for remote coding agent orchestration."""

    def __init__(self, base_url: str = SHED_BASE_URL):
        self.base_url = base_url

    def _headers(self) -> Dict[str, str]:
        token = get_shed_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def is_online(self) -> bool:
        """Checks if local or remote Shed task plane is reachable."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/auth/status")
                return res.status_code == 200
        except Exception:
            return False

    async def get_status(self) -> Dict[str, Any]:
        """Returns health status, available harnesses, and live session counts."""
        online = await self.is_online()
        if not online:
            return {
                "online": False,
                "url": self.base_url,
                "harnesses": {},
                "active_sessions_count": 0,
                "notice": f"Shed server offline at {self.base_url}."
            }

        headers = self._headers()
        harnesses: Dict[str, Any] = {}
        laya_info: Dict[str, Any] = {}
        sessions_list: List[Dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                me_res = await client.get(f"{self.base_url}/api/me", headers=headers)
                if me_res.status_code == 200:
                    me_data = me_res.json()
                    laya_info = me_data.get("laya", {})
                    available = me_data.get("available", {})
                    for k, v in available.items():
                        harnesses[k] = {"installed": v, "status": "ready" if v else "offline"}

                sess_res = await client.get(f"{self.base_url}/api/sessions", headers=headers)
                if sess_res.status_code == 200:
                    sessions_list = sess_res.json().get("sessions", [])
        except Exception as e:
            logger.warning("Error querying Shed detailed status: %s", e)

        return {
            "online": True,
            "url": self.base_url,
            "harnesses": harnesses,
            "laya": laya_info,
            "active_sessions_count": len(sessions_list),
            "sessions": sessions_list[:5],
            "status": "ready"
        }

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists active and recent agent sessions tracked by Shed."""
        if not await self.is_online():
            return []
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/api/sessions", headers=self._headers())
                if res.status_code == 200:
                    return res.json().get("sessions", [])
        except Exception as e:
            logger.error("Error fetching Shed sessions: %s", e)
        return []

    async def list_tasks(self) -> List[Dict[str, Any]]:
        """Lists running and recent tasks handled by Shed."""
        if not await self.is_online():
            return []
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/api/tasks", headers=self._headers())
                if res.status_code == 200:
                    return res.json().get("tasks", [])
        except Exception as e:
            logger.error("Error fetching Shed tasks: %s", e)
        return []

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a specific task."""
        if not await self.is_online():
            return None
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/api/tasks/{task_id}", headers=self._headers())
                if res.status_code == 200:
                    return res.json().get("task")
        except Exception as e:
            logger.error("Error fetching Shed task %s: %s", task_id, e)
        return None

    async def dispatch_task(self, prompt: str, harness: str = "auto", session_id: Optional[str] = None) -> Dict[str, Any]:
        """Dispatches a prompt to an agent session via Shed."""
        if not await self.is_online():
            return {
                "success": False,
                "error": f"Shed task plane is offline at {self.base_url}. Please ensure Shed is running."
            }

        payload = {
            "prompt": prompt,
            "harness": harness,
            "sessionId": session_id
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{self.base_url}/api/tasks", json=payload, headers=self._headers())
                if res.status_code in (200, 201):
                    return {"success": True, "task": res.json().get("task", res.json())}
                else:
                    return {"success": False, "error": f"Shed responded with HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to dispatch task to Shed: {str(e)}"}


shed_bridge = ShedBridge()
