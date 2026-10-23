"""Desktop Executor API: Presence, Outbound WebSocket Tunnel, and Remote Dispatch."""
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Header, HTTPException, status, Request
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.desktop.presence import presence_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/desktop", tags=["desktop"])


class PresenceResponse(BaseModel):
    user_id: str
    status: str  # online, offline
    last_heartbeat: Optional[float] = None
    connected_at: Optional[float] = None


class KillSwitchRequest(BaseModel):
    user_id: str


@router.get("/presence", response_model=PresenceResponse)
async def get_desktop_presence(user_id: str = Query(..., description="User ID or Phone/UUID")):
    """Returns real-time online/offline presence status for a user's desktop sidecar."""
    presence = presence_manager.get_presence(user_id)
    return PresenceResponse(**presence)


@router.websocket("/ws")
async def desktop_websocket_tunnel(
    websocket: WebSocket,
    user_id: str = Query(..., description="User ID"),
    x_desktop_secret: Optional[str] = Header(None)
):
    """
    WebSocket endpoint for outbound connections from local Python sidecar.
    Secured by shared secret authentication.
    """
    # Verify shared secret
    auth_secret = x_desktop_secret or websocket.query_params.get("secret")
    if auth_secret != settings.DESKTOP_SHARED_SECRET:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("Rejected unauthorized desktop WebSocket connection attempt for user %s", user_id)
        return

    await websocket.accept()
    presence_manager.register_connection(user_id, websocket)

    try:
        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                presence_manager.update_heartbeat(user_id)
                await websocket.send_json({"type": "heartbeat_ack", "timestamp": data.get("timestamp")})

            elif msg_type == "action_result":
                action_id = data.get("action_id")
                result_payload = data.get("result", {})
                if action_id:
                    presence_manager.handle_command_response(action_id, result_payload)

            elif msg_type == "kill_switch_ack":
                logger.info("Kill switch ACK received from sidecar for user %s", user_id)

    except WebSocketDisconnect:
        presence_manager.unregister_connection(user_id, websocket)
    except Exception as e:
        logger.error("Desktop WebSocket error for user %s: %s", user_id, e)
        presence_manager.unregister_connection(user_id, websocket)


@router.post("/kill-switch")
async def trigger_kill_switch_api(payload: KillSwitchRequest):
    """Triggers global kill switch on the user's desktop sidecar."""
    user_id = payload.user_id
    if not presence_manager.is_online(user_id):
        return {"success": False, "status": "offline", "error": "laptop offline"}

    res = await presence_manager.send_command_to_desktop(
        user_id=user_id,
        command_payload={"type": "kill_switch"},
        timeout=5.0
    )
    return res


@router.post("/voice/transcribe")
async def transcribe_voice_action(
    request: Request,
    user_id: str = Query(..., description="User ID or Phone/UUID"),
    execute_cascade: bool = Query(default=True, description="Whether to route transcribed text directly through cascade")
):
    """
    Ultra-low latency Speech-To-Text endpoint.
    Accepts raw audio bytes, transcribes via faster-whisper INT8 engine,
    and directly feeds the transcribed text into FastAgent's 4-stage cascade.
    """
    from backend.app.desktop.voice_stt import voice_stt_engine
    from backend.app.cascade.orchestrator import cascade_orchestrator

    body = await request.body()
    transcription = voice_stt_engine.transcribe_audio(body)
    heard_text = transcription.get("text", "")

    cascade_result = None
    if execute_cascade and heard_text:
        cascade_result = await cascade_orchestrator.handle_message(
            user_id=user_id,
            message_text=heard_text,
            source_is_third_party=False
        )

    return {
        "status": "success",
        "transcription": transcription,
        "cascade": {
            "intent": cascade_result.intent if cascade_result else None,
            "status": cascade_result.status if cascade_result else None,
            "response_text": cascade_result.response_text if cascade_result else None,
            "stage_latencies_ms": cascade_result.stage_latencies_ms if cascade_result else {}
        } if cascade_result else None
    }


class ShedTaskRequest(BaseModel):
    prompt: str
    harness: Optional[str] = "auto"
    session_id: Optional[str] = None


@router.get("/shed/status")
async def get_shed_status():
    """Returns remote access status for Shed coding task plane."""
    from backend.app.desktop.shed_bridge import shed_bridge
    return await shed_bridge.get_status()


@router.get("/shed/sessions")
async def get_shed_sessions():
    """Lists running and recent sessions in Claude, Codex, Gemini, OpenCode via Shed."""
    from backend.app.desktop.shed_bridge import shed_bridge
    return await shed_bridge.list_sessions()


@router.post("/shed/task")
async def dispatch_shed_task(payload: ShedTaskRequest):
    """Dispatches a coding task to Shed."""
    from backend.app.desktop.shed_bridge import shed_bridge
    return await shed_bridge.dispatch_task(
        prompt=payload.prompt,
        harness=payload.harness or "auto",
        session_id=payload.session_id
    )


