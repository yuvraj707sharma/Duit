"""Skills Management API for DUIT."""
import hmac
import ipaddress
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
from backend.app.db.repository import repository
from backend.app.config import settings

router = APIRouter(prefix="/api/skills", tags=["Skills"])


# --- Private IP / SSRF protection ---
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]


def _validate_webhook_url(url: Optional[str]) -> None:
    """Reject webhook URLs that target private/internal networks or use non-HTTPS schemes."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid webhook URL")
    # Block IPs in private ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise HTTPException(status_code=400, detail="Webhook URL must not target private/internal networks")
    except ValueError:
        lower = hostname.lower()
        if lower in ("localhost", "metadata.google.internal") or lower.endswith((".local", ".internal")):
            raise HTTPException(status_code=400, detail="Webhook URL must not target internal hosts")


def _require_gateway_auth(x_gateway_secret: Optional[str]) -> None:
    """Verify gateway shared secret."""
    if not settings.is_production and not x_gateway_secret:
        return
    expected = settings.GATEWAY_SHARED_SECRET
    if not expected:
        raise HTTPException(status_code=401, detail="Gateway secret not configured")
    if not x_gateway_secret or not hmac.compare_digest(x_gateway_secret.strip(), expected.strip()):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid gateway secret")


class CreateSkillRequest(BaseModel):
    user_id: Optional[str] = "GLOBAL"
    name: str
    description: Optional[str] = ""
    system_prompt: str
    trigger_keywords: Optional[str] = ""
    webhook_url: Optional[str] = None
    slug: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]])
async def list_skills(user_id: Optional[str] = Query(default=None)):
    """Lists global skill templates and user-specific skills."""
    return await repository.list_skills(user_id=user_id)


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_skill(
    req: CreateSkillRequest,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Registers a new skill. Requires admin/gateway authentication in production."""
    _require_gateway_auth(x_gateway_secret)

    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Skill name cannot be empty")
    if not req.system_prompt.strip():
        raise HTTPException(status_code=400, detail="System prompt cannot be empty")

    # Validate webhook URL against SSRF in all environments
    _validate_webhook_url(req.webhook_url)

    skill = await repository.add_skill(
        name=req.name.strip(),
        system_prompt=req.system_prompt.strip(),
        user_id=req.user_id or "GLOBAL",
        description=req.description or "",
        trigger_keywords=req.trigger_keywords or "",
        webhook_url=req.webhook_url,
        slug=req.slug
    )
    return skill


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Deletes or deactivates a skill. Requires admin/gateway authentication in production."""
    _require_gateway_auth(x_gateway_secret)

    success = await repository.delete_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "success", "message": f"Skill {skill_id} deleted"}


@router.get("/library", response_model=List[Dict[str, Any]])
async def get_skills_library():
    """Returns curated skills from the @hasna/skills library."""
    from backend.app.desktop.skills_library import skills_library
    return skills_library.get_catalog()


class InstallLibrarySkillRequest(BaseModel):
    skill_id: str
    user_id: Optional[str] = "GLOBAL"


@router.post("/library/install")
async def install_library_skill(
    req: InstallLibrarySkillRequest,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Installs/activates a skill from the library into the active pool."""
    _require_gateway_auth(x_gateway_secret)

    from backend.app.desktop.skills_library import skills_library
    template = skills_library.get_skill(req.skill_id)
    if not template:
        raise HTTPException(status_code=404, detail="Skill not found in library")

    skill = await repository.add_skill(
        name=template["name"],
        system_prompt=template["system_prompt"],
        user_id=req.user_id or "GLOBAL",
        description=template["description"],
        trigger_keywords=template["trigger_keywords"],
        slug=template["slug"]
    )
    return {"status": "success", "skill": skill}
