"""Agent meta-tools for API discovery, uploaded file reading, and API requests."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Any, Callable

import httpx
from duckduckgo_search import DDGS
from llama_index.core.tools import FunctionTool

from .sandbox import sandbox_manager

MAX_RESPONSE_CHARS = 50_000
ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
BLOCKED_ENDPOINT_PREFIXES = ("/agent/chat", "/agent/chats", "/stream/")


def _inject_runtime_context(
    payload: Any,
    *,
    branch_id: str | None = None,
    revision: int | None = None,
    project_id: str | None = None,
) -> Any:
    """Recursively inject runtime branch/project/revision into API examples."""
    if isinstance(payload, dict):
        updated: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "branchId" and branch_id:
                updated[key] = branch_id
                continue
            if key == "projectId" and project_id:
                updated[key] = project_id
                continue
            if key == "revision" and revision is not None:
                updated[key] = revision
                continue
            updated[key] = _inject_runtime_context(
                value,
                branch_id=branch_id,
                revision=revision,
                project_id=project_id,
            )
        return updated
    if isinstance(payload, list):
        return [
            _inject_runtime_context(
                item,
                branch_id=branch_id,
                revision=revision,
                project_id=project_id,
            )
            for item in payload
        ]
    if isinstance(payload, str):
        if branch_id and payload in {"CURRENT_BRANCH_ID", "BRANCH_ID", "branch-uuid"}:
            return branch_id
        if project_id and payload in {"CURRENT_PROJECT_ID", "PROJECT_ID", "project-uuid"}:
            return project_id
    return payload


def discover_api(
    api_spec_provider: Callable[[], dict[str, Any]],
    branch_id: str | None = None,
    revision: int | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return curated API discovery metadata with runtime context in examples."""
    spec = deepcopy(api_spec_provider())
    return _inject_runtime_context(
        spec,
        branch_id=branch_id,
        revision=revision,
        project_id=project_id,
    )


def execute_request(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | list[Any] | None = None,
    query_params: dict[str, Any] | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Execute one HTTP request against the BimAtlas API.

    The request is made server-side so authentication can remain private to
    backend execution context. Large responses are truncated to protect the
    model context window.
    """
    normalized_method = (method or "").upper().strip()
    if normalized_method not in ALLOWED_HTTP_METHODS:
        allowed = ", ".join(sorted(ALLOWED_HTTP_METHODS))
        raise ValueError(f"Unsupported method '{method}'. Allowed: {allowed}")
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        raise ValueError("endpoint must start with '/'")
    if endpoint.startswith(BLOCKED_ENDPOINT_PREFIXES):
        raise ValueError("endpoint is blocked for execute_request")

    base_url = os.environ.get("BIMATLAS_API_URL", "http://localhost:8000").rstrip("/")
    url = f"{base_url}{endpoint}"
    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            normalized_method,
            url,
            json=payload,
            params=query_params,
        )

    raw_text = response.text
    truncated = len(raw_text) > MAX_RESPONSE_CHARS
    body_text = raw_text[:MAX_RESPONSE_CHARS] if truncated else raw_text

    body_json: Any | None = None
    try:
        body_json = response.json()
    except ValueError:
        body_json = None

    result: dict[str, Any] = {
        "method": normalized_method,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "ok": response.is_success,
        "content_type": response.headers.get("content-type"),
        "body": body_json if body_json is not None else body_text,
        "truncated": truncated,
    }
    if description:
        result["description"] = description
    if truncated:
        result["notice"] = (
            f"Response truncated at {MAX_RESPONSE_CHARS} chars. "
            "Use API pagination (limit/offset/cursor), narrower filters, or GraphQL field selection."
        )
    if body_json is not None:
        serialized = json.dumps(body_json, ensure_ascii=False)
        result["body_chars"] = len(serialized)
    else:
        result["body_chars"] = len(raw_text)
    return result


def _read_pdf_text(data: bytes) -> tuple[str, int]:
    import io

    import pdfplumber  # pylint: disable=import-error

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return ("\n\n".join(pages)).strip(), len(pages)


def read_uploaded_file(session_id: str, filename: str) -> dict[str, Any]:
    """Read user-uploaded file content from uploads directory.

    PDFs are text-extracted automatically. Large extracted content is truncated.
    """
    data = sandbox_manager.read_upload(session_id, filename)
    ext = Path(filename).suffix.lower()
    max_chars = 50_000
    page_count: int | None = None

    if ext == ".pdf":
        try:
            text, page_count = _read_pdf_text(data)
        except Exception as exc:
            raise ValueError(f"Failed to parse PDF: {exc}") from exc
    elif ext in {".txt", ".csv", ".json", ".xml"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
    elif ext == ".xlsx":
        # Return metadata and ask for tabular-friendly upload format.
        return {
            "filename": filename,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": len(data),
            "text": (
                "Binary XLSX file uploaded. Convert to CSV/TXT for inline content "
                "inspection, or request API operations that process this file format."
            ),
            "truncated": False,
        }
    else:
        raise ValueError(f"Unsupported uploaded file type: {ext}")

    truncated = len(text) > max_chars
    content = text[:max_chars] if truncated else text
    response: dict[str, Any] = {
        "filename": filename,
        "size_bytes": len(data),
        "text": content,
        "truncated": truncated,
    }
    if page_count is not None:
        response["pages"] = page_count
        response["content_type"] = "application/pdf"
    if truncated:
        response["notice"] = (
            "Content truncated at 50,000 characters. For complete processing, "
            "use smaller sections or request targeted API queries."
        )
    return response


def list_uploaded_files(session_id: str) -> dict[str, Any]:
    """List files uploaded by the user for this chat session."""
    return {"uploads": sandbox_manager.list_uploads(session_id)}


def search_skills(
    intent: str,
    project_id: str,
    branch_id: str | None = None,
    top_k: int = 5,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Search IFC skills by semantic intent. Returns matching skills with content.

    Call this FIRST for filter requests. Use project_id and branch_id from context.
    """
    from .skills import search_skills as _search

    results = _search(intent, project_id, branch_id, top_k=top_k, api_key=api_key)
    return {"skills": results, "count": len(results)}


def ask_user_for_guidance(question: str, context: str = "") -> dict[str, Any]:
    """Request domain guidance from the user when the IFC path is unclear.

    Do NOT guess. Call this immediately when discover_api or search_skills
    does not provide a clear relational path for the user's request.
    """
    return {
        "type": "guidance_request",
        "question": question,
        "context": context or "",
        "message": "Execution paused. Awaiting user guidance.",
    }


def search_web(query: str, max_results: int = 5) -> str:
    """Search the public web and return structured Markdown results.

    Use this tool to find up-to-date information, building codes, or manufacturer
    specifications on the internet.

    This tool only returns snippets and URLs. To read the full content of a page,
    you must pass the chosen URL from these results into the fetch_webpage tool.

    Keep your search queries concise and targeted.
    """
    try:
        results = list(DDGS().text(query, max_results=max_results))
    except Exception as exc:  # broad catch to keep agent loop resilient
        return (
            "Search failed due to network or rate limit error: "
            f"{str(exc)}. Try a different query or rely on internal knowledge."
        )

    if not results:
        return f"No results found for the query: '{query}'."

    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        title = str(result.get("title", "")).strip() or "Untitled"
        href = str(result.get("href", "")).strip() or "URL unavailable"
        body = str(result.get("body", "")).strip() or "No snippet available."
        lines.append(
            f"{index}. **Title:** {title}\n"
            f"   **URL:** {href}\n"
            f"   **Snippet:** {body}"
        )
    return "\n\n".join(lines)


def save_ifc_skill(
    project_id: str,
    title: str,
    intent: str,
    frontmatter: dict[str, Any],
    content_md: str,
    branch_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Save a learned IFC skill for future search. Call after user provides guidance."""
    from .skills import create_ifc_skill

    return create_ifc_skill(
        project_id=project_id,
        title=title,
        intent=intent,
        frontmatter=frontmatter,
        content_md=content_md,
        branch_id=branch_id,
        api_key=api_key,
    )


def get_api_tools(
    session_id: str,
    api_spec_provider: Callable[[], dict[str, Any]],
    include_discover: bool = True,
    branch_id: str | None = None,
    revision: int | None = None,
    project_id: str | None = None,
    api_key: str | None = None,
) -> list[FunctionTool]:
    """Return FunctionTool wrappers bound to the chat session."""
    discover = partial(
        discover_api,
        api_spec_provider,
        branch_id=branch_id,
        revision=revision,
        project_id=project_id,
    )
    run_request = execute_request
    read_upload = partial(read_uploaded_file, session_id)
    list_uploads_fn = partial(list_uploaded_files, session_id)
    search_skills_fn = partial(
        search_skills,
        project_id=project_id or "",
        branch_id=branch_id,
        api_key=api_key,
    )
    save_skill_fn = partial(
        save_ifc_skill,
        project_id=project_id or "",
        branch_id=branch_id,
        api_key=api_key,
    )

    tools: list[FunctionTool] = []
    if include_discover:
        tools.append(
            FunctionTool.from_defaults(
                fn=discover,
                name="discover_api",
                description=(
                    "Return the curated BimAtlas API contract (REST + GraphQL queries/mutations "
                    "with examples). Call this at the start of tasks that need API operations."
                ),
            )
        )
    tools.extend([
        FunctionTool.from_defaults(
            fn=list_uploads_fn,
            name="list_uploaded_files",
            description=(
                "List user-uploaded files available in this chat session workspace."
            ),
        ),
        FunctionTool.from_defaults(
            fn=read_upload,
            name="read_uploaded_file",
            description=(
                "Read one uploaded file by filename. Supports PDF (text extraction), "
                "CSV/TXT/JSON/XML text files, and XLSX metadata hints."
            ),
        ),
        FunctionTool.from_defaults(
            fn=search_web,
            name="search_web",
            description=(
                "Search the web for recent or external references and return result "
                "snippets with URLs. Use selected URLs with fetch_webpage for full content."
            ),
        ),
        FunctionTool.from_defaults(
            fn=run_request,
            name="execute_request",
            description=(
                "Execute one HTTP request against the BimAtlas API. Use this for REST "
                "and GraphQL calls after discovering endpoint contracts."
            ),
        ),
        FunctionTool.from_defaults(
            fn=search_skills_fn,
            name="search_skills",
            description=(
                "Search IFC skills by intent (e.g. 'ground floor windows'). "
                "Call FIRST for filter requests. Returns skills with content."
            ),
        ),
        FunctionTool.from_defaults(
            fn=ask_user_for_guidance,
            name="ask_user_for_guidance",
            description=(
                "Request domain guidance when the IFC relational path is unclear. "
                "Do NOT guess. Call immediately when discover_api and search_skills "
                "do not provide a clear path."
            ),
        ),
        FunctionTool.from_defaults(
            fn=save_skill_fn,
            name="save_ifc_skill",
            description=(
                "Save a learned IFC skill after user provides guidance. "
                "Requires title, intent, frontmatter, content_md."
            ),
        ),
    ])
    return tools


def get_sandbox_tools(
    session_id: str,
    api_spec_provider: Callable[[], dict[str, Any]],
    include_discover: bool = True,
    branch_id: str | None = None,
    revision: int | None = None,
    project_id: str | None = None,
    api_key: str | None = None,
) -> list[FunctionTool]:
    """Backward-compatible alias."""
    return get_api_tools(
        session_id,
        api_spec_provider,
        include_discover=include_discover,
        branch_id=branch_id,
        revision=revision,
        project_id=project_id,
        api_key=api_key,
    )
