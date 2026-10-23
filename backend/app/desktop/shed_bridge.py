"""Shed Remote Access Bridge for Desktop Coding Agents (Codex, Claude Code, Gemini, OpenCode)."""
import os
import json
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SHED_BASE_URL = os.environ.get("SHED_BASE_URL", "http://localhost:4378").rstrip("/")


class ShedBridge:
    """Interfaces with Shed task plane for remote coding agent orchestration."""

    def __init__(self, base_url: str = SHED_BASE_URL):
        self.base_url = base_url

    async def is_online(self) -> bool:
        """Checks if local or remote Shed task plane is reachable."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/health")
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
                "harnesses": {
                    "codex": {"installed": False, "status": "offline"},
                    "claude": {"installed": False, "status": "offline"},
                    "gemini": {"installed": False, "status": "offline"},
                    "opencode": {"installed": False, "status": "offline"}
                },
                "active_sessions_count": 0,
                "notice": "Shed server offline at http://localhost:4378. Start with 'npm start' in e:\\Inovvate\\shed."
            }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/status")
                if res.status_code == 200:
                    data = res.json()
                    return {"online": True, "url": self.base_url, **data}
        except Exception as e:
            logger.warning("Error querying Shed status: %s", e)

        return {
            "online": True,
            "url": self.base_url,
            "active_sessions_count": 0,
            "status": "ready"
        }

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists active and recent agent sessions tracked by Shed."""
        if not await self.is_online():
            return []
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/api/sessions")
                if res.status_code == 200:
                    return res.json().get("sessions", [])
        except Exception as e:
            logger.error("Error fetching Shed sessions: %s", e)
        return []

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{self.base_url}/api/tasks", json=payload)
                if res.status_code in (200, 201):
                    return {"success": True, "task": res.json()}
                else:
                    return {"success": False, "error": f"Shed responded with HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to dispatch task to Shed: {str(e)}"}


shed_bridge = ShedBridge()
