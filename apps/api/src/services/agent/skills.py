"""IFC skill service: frontmatter extraction, embeddings, semantic search.

Provides frontmatter-first retrieval for search_skills and save_ifc_skill tools.
Embeddings use OpenAI text-embedding-3-small (1536 dims) for pgvector cosine search.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import yaml

from ...db import (
    fetch_ifc_skill_content,
    insert_ifc_skill,
    list_ifc_skill_frontmatter,
    search_ifc_skills_semantic,
)

logger = logging.getLogger("bimatlas.agent.skills")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter from markdown. Returns (frontmatter_dict, body)."""
    if not text or not text.strip():
        return {}, ""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text.strip()
    yaml_block, body = match.group(1), match.group(2)
    try:
        fm = yaml.safe_load(yaml_block) or {}
        return dict(fm) if isinstance(fm, dict) else {}, body.strip()
    except yaml.YAMLError:
        return {}, text.strip()


def get_embedding(text: str, api_key: str | None = None) -> list[float]:
    """Generate embedding for text using OpenAI. Returns 1536-dim vector."""
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OpenAI API key required for embeddings (OPENAI_API_KEY or api_key)")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return [float(x) for x in resp.data[0].embedding]
    except Exception as exc:
        logger.exception("Embedding generation failed")
        raise ValueError(f"Embedding failed: {exc}") from exc


def search_skills(
    intent: str,
    project_id: str,
    branch_id: str | None = None,
    top_k: int = 5,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over IFC skills. Returns frontmatter + content for top matches."""
    emb = get_embedding(intent, api_key)
    rows = search_ifc_skills_semantic(emb, project_id, branch_id, top_k)
    results: list[dict[str, Any]] = []
    for r in rows:
        full = fetch_ifc_skill_content(str(r["skill_id"]))
        if full:
            results.append({
                "skill_id": str(full["skill_id"]),
                "title": full.get("title", ""),
                "intent": full.get("intent", ""),
                "frontmatter": full.get("frontmatter", {}),
                "content_md": full.get("content_md", ""),
                "distance": r.get("distance"),
            })
    return results


def list_skills_frontmatter(
    project_id: str,
    branch_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List skill metadata only (no content_md). For frontmatter-first selection."""
    return list_ifc_skill_frontmatter(project_id, branch_id, limit)


def create_ifc_skill(
    project_id: str,
    title: str,
    intent: str,
    frontmatter: dict[str, Any],
    content_md: str,
    branch_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create and persist an IFC skill with embedding. Returns created row."""
    text_to_embed = f"{title}\n{intent}\n{content_md[:2000]}"
    emb = get_embedding(text_to_embed, api_key)
    row = insert_ifc_skill(
        project_id=project_id,
        title=title,
        intent=intent,
        frontmatter=frontmatter,
        content_md=content_md,
        embedding=emb,
        branch_id=branch_id,
    )
    return {
        "skill_id": str(row["skill_id"]),
        "title": row.get("title", ""),
        "intent": row.get("intent", ""),
        "created_at": str(row.get("created_at", "")),
    }
