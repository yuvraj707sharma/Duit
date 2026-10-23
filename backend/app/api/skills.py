"""Skills Management API for FastAgent."""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.app.db.repository import repository

router = APIRouter(prefix="/api/skills", tags=["Skills"])


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
async def create_skill(req: CreateSkillRequest):
    """Registers a new skill."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Skill name cannot be empty")
    if not req.system_prompt.strip():
        raise HTTPException(status_code=400, detail="System prompt cannot be empty")

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
async def delete_skill(skill_id: str):
    """Deletes or deactivates a skill."""
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
async def install_library_skill(req: InstallLibrarySkillRequest):
    """Installs/activates a skill from the library into the active pool."""
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

