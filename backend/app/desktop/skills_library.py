"""Skills Library Bridge for FastAgent, interfacing with @hasna/skills (e:\\Inovvate\\skills)."""
import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SKILLS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "skills"))

# Standard skill packages provided by the skills library
LIBRARY_CATALOG = [
    {
        "id": "pdf-generator",
        "slug": "pdf_generator",
        "name": "PDF & Report Generator",
        "category": "documents",
        "description": "Compiles meeting minutes, schedules, and analytics into clean downloadable PDF documents.",
        "trigger_keywords": "pdf, generate pdf, export pdf, report, download pdf",
        "system_prompt": "You are a professional PDF document generation assistant. When the user requests a PDF, summarize the data cleanly with headers, tables, and timestamped sections."
    },
    {
        "id": "web-researcher",
        "slug": "web_researcher",
        "name": "Web Research & Intelligence",
        "category": "research",
        "description": "Performs quick research and web fact-checking for market updates, flights, hotels, or companies.",
        "trigger_keywords": "research, google search, find info, search web, look up",
        "system_prompt": "You are an executive research analyst. Provide concise, bulleted insights, verified facts, and direct actionable answers without fluff."
    },
    {
        "id": "cron-scheduler",
        "slug": "cron_scheduler",
        "name": "Recurring Automation & Reminders",
        "category": "automation",
        "description": "Sets up daily briefings, recurring reminders, and automated health checks.",
        "trigger_keywords": "remind me daily, recurring, every day, every morning, briefing",
        "system_prompt": "You are an automated scheduling bot. Formulate recurring daily or weekly reminders with exact times and clear summary checkpoints."
    },
    {
        "id": "code-auditor",
        "slug": "code_auditor",
        "name": "Desktop Code Reviewer",
        "category": "engineering",
        "description": "Reviews code snippets, inspects git diffs, and flags security vulnerabilities or lint errors.",
        "trigger_keywords": "review code, audit, inspect git, check diff, code review",
        "system_prompt": "You are a Senior Principal Software Engineer. Review the supplied code for bugs, race conditions, security flaws, and performance optimizations."
    },
    {
        "id": "sql-analyst",
        "slug": "sql_analyst",
        "name": "Database & Query Analyst",
        "category": "data",
        "description": "Queries databases, generates SQL reports, and explains database schemas.",
        "trigger_keywords": "sql, query database, database stats, db count, db status",
        "system_prompt": "You are a database engineer. Generate safe, read-only SELECT queries and format the query results in clean Markdown tables."
    }
]


class SkillsLibrary:
    """Manages skill discovery, catalog inspection, and installation from @hasna/skills."""

    def __init__(self, root_path: str = SKILLS_ROOT):
        self.root_path = root_path

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Returns all available skill definitions in the library catalog."""
        return LIBRARY_CATALOG

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific skill definition by ID or slug."""
        for s in LIBRARY_CATALOG:
            if s["id"] == skill_id or s["slug"] == skill_id:
                return s
        return None

    async def seed_default_skills(self, repository, user_id: str = "GLOBAL") -> List[Dict[str, Any]]:
        """Seeds the library's foundational skills into the repository if not already present."""
        existing = await repository.list_skills(user_id=user_id)
        existing_slugs = {s.get("slug") for s in existing if s.get("slug")}

        seeded = []
        for template in LIBRARY_CATALOG:
            if template["slug"] not in existing_slugs:
                skill = await repository.add_skill(
                    name=template["name"],
                    system_prompt=template["system_prompt"],
                    user_id=user_id,
                    description=template["description"],
                    trigger_keywords=template["trigger_keywords"],
                    slug=template["slug"]
                )
                seeded.append(skill)
        return seeded


skills_library = SkillsLibrary()
