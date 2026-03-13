"""FastAPI app entry -- mounts Strawberry GraphQL.

Run with::

    uvicorn src.main:app --reload --timeout-graceful-shutdown 5

Or use run.sh (includes DB check and timeout).
"""

import asyncio
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import strawberry
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from strawberry.fastapi import GraphQLRouter

from .db import (
    add_chat_message,
    close_pool,
    create_agent_chat,
    create_agent_config,
    delete_agent_chat,
    delete_agent_config,
    delete_ifc_schema_with_rules,
    fetch_agent_chats,
    fetch_agent_configs_for_project,
    fetch_applied_filter_sets,
    fetch_branch,
    fetch_chat_messages,
    fetch_project,
    fetch_entities_at_revision,
    fetch_entities_with_filter_sets,
    fetch_entity_attributes_for_global_ids,
    fetch_shape_reps_for_products,
    get_latest_revision_seq,
    init_pool,
    insert_validation_rules,
    update_agent_chat,
    update_agent_config,
    validation_schema_exists,
)
from .schema.queries import Mutation, Query as GraphQLQuery, row_to_stream_product
from .services.ifc.ingestion import ingest_ifc
from .services.agent.api_spec import build_agent_api_spec
from .services.agent.live_streams import live_chat_streams
from .services.agent.sandbox import sandbox_manager

logger = logging.getLogger("bimatlas")
_agent_api_spec_cache: dict | None = None
_session_by_chat: dict[str, str] = {}


async def _sandbox_cleanup_loop() -> None:
    while True:
        try:
            sandbox_manager.cleanup_expired_sessions()
        except Exception:
            logger.exception("sandbox cleanup loop failed")
        await asyncio.sleep(300)


def _ingestion_result_payload(result) -> dict:
    return {
        "revision_id": result.revision_id,
        "revision_seq": result.revision_seq,
        "branch_id": result.branch_id,
        "total_products": result.total_products,
        "added": result.added,
        "modified": result.modified,
        "deleted": result.deleted,
        "unchanged": result.unchanged,
        "edges_created": result.edges_created,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup / shutdown lifecycle."""
    logger.info("Starting BimAtlas API -- initialising connection pool")
    try:
        init_pool()
    except Exception as e:
        if "Connection refused" in str(e) or "connection" in str(e).lower():
            raise RuntimeError(
                "Database connection refused. Start PostgreSQL first:\n"
                "  cd infra && docker compose up -d\n"
                "Then wait a few seconds for PostgreSQL to be ready."
            ) from e
        raise
    cleanup_task = asyncio.create_task(_sandbox_cleanup_loop())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down BimAtlas API -- closing connection pool")
    close_pool()


schema = strawberry.Schema(query=GraphQLQuery, mutation=Mutation)
graphql_app = GraphQLRouter(schema)

app = FastAPI(
    title="BimAtlas API",
    description="Extensible Spatial-Graph Engine for IFC models",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graphql_app, prefix="/graphql")


def get_agent_api_spec() -> dict:
    global _agent_api_spec_cache
    if _agent_api_spec_cache is None:
        _agent_api_spec_cache = build_agent_api_spec(app, schema)
    return _agent_api_spec_cache


def _resolve_session_id(chat_id: str | None, provided: str | None) -> str:
    if provided:
        try:
            UUID(provided)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid sessionId")
        if chat_id:
            _session_by_chat[chat_id] = provided
        return provided
    if chat_id:
        existing = _session_by_chat.get(chat_id)
        if existing:
            return existing
    import uuid

    sid = str(uuid.uuid4())
    if chat_id:
        _session_by_chat[chat_id] = sid
    return sid


@app.get("/health")
async def health():
    """Basic liveness check."""
    return {"status": "ok"}


@app.post("/table/entity-attributes")
async def table_entity_attributes(
    body: dict = Body(...),
):
    """Return entity attributes for given global IDs, optionally restricted to requested top-level keys.
    Request body: { "branchId": str, "revision": int | null, "globalIds": str[], "paths": str[] | null }.
    paths: e.g. ["PropertySets", "Name"]; if null or empty, all attributes are returned.
    Response: { "attributesByGlobalId": { [globalId]: { ...attributes } } }.
    """
    try:
        branch_id = body.get("branchId")
        revision = body.get("revision")
        global_ids = body.get("globalIds") or []
        paths = body.get("paths")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid body")
    if not branch_id or not isinstance(global_ids, list):
        raise HTTPException(status_code=400, detail="branchId and globalIds required")
    try:
        UUID(branch_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Branch not found")
    rev = revision if revision is not None else get_latest_revision_seq(branch_id)
    if rev is None:
        raise HTTPException(status_code=404, detail="No revisions on branch")
    include_validations = (
        paths is None or len(paths) == 0 or "Validations" in (paths or [])
    )
    rows = fetch_entity_attributes_for_global_ids(rev, branch_id, global_ids, include_validations=include_validations)
    attributes_by_global_id = {}
    for row in rows:
        gid = row["ifc_global_id"]
        attrs = row.get("attributes") or {}
        if paths and len(paths) > 0:
            attrs = {k: attrs[k] for k in paths if k in attrs}
        attributes_by_global_id[gid] = attrs
    return {"attributesByGlobalId": attributes_by_global_id}


def _stream_ifc_products_generator(
    branch_id: str,
    revision: int | None,
    ifc_class: str | None,
    ifc_classes: list[str] | None,
    contained_in: str | None,
    name: str | None,
    object_type: str | None,
    tag: str | None,
    description: str | None,
    global_id: str | None,
    relation_types: list[str] | None = None,
):
    """Yield SSE events for IFC products stream."""
    rev = revision
    if rev is None:
        rev = get_latest_revision_seq(branch_id)
        if rev is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No revisions on this branch'})}\n\n"
            return

    try:
        applied = fetch_applied_filter_sets(branch_id)
        if applied["filter_sets"]:
            filter_sets_data = [
                {"logic": fs.get("logic", "AND"), "filters": fs.get("filters", [])}
                for fs in applied["filter_sets"]
            ]
            rows = fetch_entities_with_filter_sets(
                rev,
                branch_id,
                filter_sets_data,
                combination_logic=applied["combination_logic"],
            )
        else:
            rows = fetch_entities_at_revision(
                rev,
                branch_id,
                ifc_class=ifc_class,
                ifc_classes=ifc_classes,
                contained_in=contained_in,
                name=name,
                object_type=object_type,
                tag=tag,
                description=description,
                global_id=global_id,
                relation_types=relation_types,
            )
    except Exception as exc:
        logger.exception("Failed to stream IFC products")
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'start', 'total': len(rows)})}\n\n"

    # Batch-fetch shape representations for all products to avoid N+1 queries.
    product_gids = [row["ifc_global_id"] for row in rows]
    shape_reps_by_product = fetch_shape_reps_for_products(product_gids, rev, branch_id)

    for i, row in enumerate(rows):
        product = row_to_stream_product(
            dict(row),
            rev=rev,
            branch_id=branch_id,
            shape_rows=shape_reps_by_product.get(row["ifc_global_id"]),
        )
        yield f"data: {json.dumps({'type': 'product', 'product': product, 'current': i + 1, 'total': len(rows)})}\n\n"

    yield f"data: {json.dumps({'type': 'end'})}\n\n"


@app.get("/stream/ifc-products")
async def stream_ifc_products(
    branch_id: str = Query(..., description="Branch ID (UUID)"),
    revision: int | None = Query(None, description="Revision ID (default: latest)"),
    ifc_class: str | None = Query(None, description="Filter by IFC class"),
    ifc_classes: list[str] | None = Query(None, description="Filter by IFC classes"),
    contained_in: str | None = Query(None, description="Filter by container GlobalId"),
    name: str | None = Query(None, description="Filter by name (ILIKE)"),
    object_type: str | None = Query(None, description="Filter by object type (ILIKE)"),
    tag: str | None = Query(None, description="Filter by tag (ILIKE)"),
    description: str | None = Query(None, description="Filter by description (ILIKE)"),
    global_id: str | None = Query(None, description="Filter by GlobalId (ILIKE)"),
    relation_types: list[str] | None = Query(None, description="Filter by IFC relation types"),
):
    """Stream IFC products with geometry as Server-Sent Events.
    
    Events: start { total }, product { product, current, total }, end.
    """
    # Validate branch_id early to avoid DB casting errors
    try:
        UUID(branch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")
    return StreamingResponse(
        _stream_ifc_products_generator(
            branch_id=branch_id,
            revision=revision,
            ifc_class=ifc_class,
            ifc_classes=ifc_classes,
            contained_in=contained_in,
            name=name,
            object_type=object_type,
            tag=tag,
            description=description,
            global_id=global_id,
            relation_types=relation_types,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/upload-ifc")
async def upload_ifc(
    file: UploadFile = File(...),
    branch_id: str = Form(...),
    label: str | None = Form(None),
):
    """Accept an IFC file upload, ingest it into a branch, and return the revision summary.

    The file is written to a temporary directory, processed by the ingestion
    pipeline (parse -> diff -> DB + graph), then cleaned up.

    Args:
        file: The IFC file to upload.
        branch_id: The branch to ingest the file into.
        label: Optional human-readable label for the revision.
    """
    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail="Only .ifc files are accepted")

    # Validate branch_id format early so invalid values return a clean 404
    try:
        UUID(branch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    # Verify branch exists
    branch = fetch_branch(branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        contents = await file.read()
        tmp_path.write_bytes(contents)

        try:
            result = ingest_ifc(str(tmp_path), branch_id=branch_id, label=label)
        except (OSError, ValueError) as e:
            logger.exception("IFC ingestion failed")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse IFC file: {e!s}",
            ) from e

    return _ingestion_result_payload(result)


@app.post("/upload-ifc/stream")
async def upload_ifc_stream(
    file: UploadFile = File(...),
    branch_id: str = Form(...),
    label: str | None = Form(None),
):
    """Stream IFC ingestion progress and final result as NDJSON."""
    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail="Only .ifc files are accepted")

    try:
        UUID(branch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    branch = fetch_branch(branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail=f"Branch {branch_id} not found")

    contents = await file.read()

    async def generate():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def push(event: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def worker() -> None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / file.filename
                tmp_path.write_bytes(contents)
                try:
                    result = ingest_ifc(
                        str(tmp_path),
                        branch_id=branch_id,
                        label=label,
                        progress_callback=push,
                    )
                    push({"type": "result", "result": _ingestion_result_payload(result)})
                except (OSError, ValueError) as exc:
                    logger.exception("IFC ingestion failed")
                    push({"type": "error", "message": f"Failed to parse IFC file: {exc!s}"})
                except Exception as exc:
                    logger.exception("IFC ingestion failed")
                    push({"type": "error", "message": str(exc)})
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(event) + "\n"
        finally:
            await task

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/ifc-schema", status_code=201)
async def upload_ifc_schema(
    schema_json: dict = Body(
        ...,
        description=(
            "IFC schema JSON matching the generator output shape, including a "
            "top-level 'schema' name and 'entities' map."
        ),
    ),
):
    """Register a new IFC schema definition in ifc_schema/validation_rule.

    The payload must include a top-level ``schema`` field (schema identifier,
    e.g. ``\"IFC4X3_ADD2\"``) and an ``entities`` object describing classes,
    inheritance, and attributes.

    This endpoint enforces **one row per schema name**; attempting to upload a
    duplicate schema name returns HTTP 409.
    """
    schema_name = schema_json.get("schema")
    if not isinstance(schema_name, str) or not schema_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Schema JSON must include a non-empty top-level 'schema' string field.",
        )

    if validation_schema_exists(schema_name):
        raise HTTPException(
            status_code=409,
            detail=f"Schema '{schema_name}' already exists. Duplicate schema names are not allowed.",
        )

    # Basic shape check – entities map should be present and dict-like.
    entities = schema_json.get("entities")
    if not isinstance(entities, dict) or not entities:
        raise HTTPException(
            status_code=400,
            detail="Schema JSON must include a non-empty 'entities' object.",
        )

    insert_validation_rules(schema_name, schema_json)
    return {"schema": schema_name}


@app.delete("/ifc-schema/{schema_name}")
async def delete_ifc_schema(schema_name: str):
    """Delete an IFC schema and all attached validation rules."""
    try:
        result = delete_ifc_schema_with_rules(schema_name)
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Failed to delete schema '{schema_name}'. "
                "It may still be referenced by projects."
            ),
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{schema_name}' not found.",
        )
    return result


# ---------------------------------------------------------------------------
# Agent endpoints (FEAT-004 Agentic Filtering Framework)
# ---------------------------------------------------------------------------


@app.get("/agent/api-spec")
async def agent_api_spec():
    """Return curated API discovery payload for autonomous agent workflows."""
    return get_agent_api_spec()


@app.post("/agent/upload")
async def agent_upload(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """Upload a file into the sandbox workspace for this chat session."""
    try:
        content = await file.read()
        saved = sandbox_manager.save_upload(session_id, file.filename or "upload.bin", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {
        "filename": saved["filename"],
        "size_bytes": saved["size_bytes"],
        "content_type": file.content_type or "application/octet-stream",
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# Agent IFC skills (semantic search, create, frontmatter list)
# ---------------------------------------------------------------------------


@app.get("/agent/skills/frontmatter")
async def agent_skills_frontmatter(
    project_id: str = Query(..., description="Project ID"),
    branch_id: str | None = Query(None, description="Optional branch ID to scope"),
    limit: int = Query(50, ge=1, le=200, description="Max skills to return"),
):
    """List IFC skill metadata (frontmatter only) for project/branch scope."""
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project_id")
    if branch_id:
        try:
            UUID(branch_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid branch_id")
    from .services.agent.skills import list_skills_frontmatter

    rows = list_skills_frontmatter(project_id, branch_id, limit)
    return {"skills": rows}


@app.post("/agent/skills/search")
async def agent_skills_search(body: dict = Body(...)):
    """Semantic search over IFC skills by intent. Returns matching skills with content."""
    intent = body.get("intent")
    project_id = body.get("projectId")
    branch_id = body.get("branchId")
    top_k = body.get("topK", 5)
    api_key = body.get("apiKey")
    if not intent or not project_id:
        raise HTTPException(status_code=400, detail="intent and projectId are required")
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid projectId")
    if branch_id:
        try:
            UUID(branch_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid branchId")
    from .services.agent.skills import search_skills

    try:
        results = search_skills(intent, project_id, branch_id, top_k=int(top_k), api_key=api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"skills": results}


@app.post("/agent/skills", status_code=201)
async def agent_skills_create(body: dict = Body(...)):
    """Create and persist an IFC skill with embedding. Returns created skill metadata."""
    project_id = body.get("projectId")
    title = body.get("title")
    intent = body.get("intent")
    frontmatter = body.get("frontmatter", {})
    content_md = body.get("contentMd", body.get("content_md", ""))
    branch_id = body.get("branchId")
    api_key = body.get("apiKey")
    if not project_id or not title or not intent:
        raise HTTPException(status_code=400, detail="projectId, title, and intent are required")
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid projectId")
    if branch_id:
        try:
            UUID(branch_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid branchId")
    from .services.agent.skills import create_ifc_skill

    try:
        row = create_ifc_skill(
            project_id=project_id,
            title=title,
            intent=intent,
            frontmatter=frontmatter if isinstance(frontmatter, dict) else {},
            content_md=content_md,
            branch_id=branch_id,
            api_key=api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@app.post("/agent/chat")
async def agent_chat(body: dict = Body(...)):
    """Stream an agentic filtering conversation turn.

    Supports persistent chat history via ``chatId``. When provided, the
    backend loads prior messages from the DB, appends the user message
    before streaming, and saves the assistant reply on completion.
    """
    message = body.get("message")
    provider = body.get("provider")
    model = body.get("model")
    api_key = body.get("apiKey")
    branch_id = body.get("branchId")
    revision = body.get("revision")
    base_url = body.get("baseUrl")
    pre_prompt = body.get("prePrompt")
    chat_id = body.get("chatId")
    session_id = body.get("sessionId")
    project_id = body.get("projectId")
    files = body.get("files") or []

    if not message or not provider or not model or not branch_id:
        raise HTTPException(
            status_code=400,
            detail="message, provider, model, and branchId are required",
        )
    if not api_key and provider not in ("ollama",):
        raise HTTPException(status_code=400, detail="apiKey is required for this provider")

    try:
        UUID(branch_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Invalid branchId")

    chat_history: list[dict[str, str]] | None = None
    if chat_id:
        try:
            UUID(chat_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid chatId")
        msgs = fetch_chat_messages(chat_id)
        chat_history = [
            {"role": m["role"], "content": m["content"]}
            for m in msgs
            if m["role"] in ("user", "assistant")
        ]
    if files is not None and not isinstance(files, list):
        raise HTTPException(status_code=400, detail="files must be an array of filenames")
    uploaded_files = [str(f) for f in files if isinstance(f, str) and f.strip()]
    resolved_session_id = _resolve_session_id(chat_id, session_id)

    from .services.agent.workflow import run_agent_streaming

    # Chats are resumable across page refresh. For persisted chats, run the
    # agent in a background task and stream through live_chat_streams.
    if chat_id:
        started = await live_chat_streams.start(chat_id)
        if not started:
            raise HTTPException(status_code=409, detail="A response is already running for this chat")
        add_chat_message(chat_id, "user", message)

        async def run_in_background() -> None:
            collected_content = ""
            collected_error = ""
            collected_tools: list[dict] = []
            collected_usage: dict | None = None
            try:
                async for event in run_agent_streaming(
                    message=message,
                    branch_id=branch_id,
                    provider=provider,
                    model=model,
                    api_key=api_key or "",
                    revision=revision,
                    base_url=base_url,
                    pre_prompt=pre_prompt,
                    chat_history=chat_history,
                    session_id=resolved_session_id,
                    uploaded_files=uploaded_files,
                    api_spec_provider=get_agent_api_spec,
                    project_id=project_id,
                ):
                    etype = event.get("type")
                    if etype == "message":
                        collected_content = event.get("content", "")
                    elif etype == "error":
                        collected_error = event.get("content", "")
                    elif etype == "tool_call":
                        collected_tools.append({
                            "name": event.get("name"),
                            "arguments": event.get("arguments"),
                            "result": event.get("result"),
                        })
                    elif etype == "usage":
                        collected_usage = {
                            "prompt_tokens": event.get("prompt_tokens", 0),
                            "completion_tokens": event.get("completion_tokens", 0),
                            "total_tokens": event.get("total_tokens", 0),
                            "cost_usd": event.get("cost_usd"),
                        }
                    await live_chat_streams.publish(chat_id, event)
            except Exception as exc:
                logger.exception("Background chat stream failed")
                err_event = {"type": "error", "content": f"Agent error: {exc}"}
                await live_chat_streams.publish(chat_id, err_event)
                collected_error = err_event["content"]
            finally:
                try:
                    if collected_content:
                        add_chat_message(
                            chat_id,
                            "assistant",
                            collected_content,
                            tool_calls=collected_tools if collected_tools else None,
                            usage=collected_usage,
                        )
                    elif collected_error:
                        add_chat_message(chat_id, "assistant", collected_error)
                finally:
                    await live_chat_streams.finish(chat_id)

        asyncio.create_task(run_in_background())

        async def live_event_generator():
            queue = await live_chat_streams.subscribe(chat_id)
            if queue is None:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        break
            except asyncio.CancelledError:
                pass
            finally:
                await live_chat_streams.unsubscribe(chat_id, queue)

        return StreamingResponse(
            live_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-persistent ad-hoc chat request (no chat_id): stream directly.
    async def direct_event_generator():
        async for event in run_agent_streaming(
            message=message,
            branch_id=branch_id,
            provider=provider,
            model=model,
            api_key=api_key or "",
            revision=revision,
            base_url=base_url,
            pre_prompt=pre_prompt,
            chat_history=chat_history,
            session_id=resolved_session_id,
            uploaded_files=uploaded_files,
            api_spec_provider=get_agent_api_spec,
            project_id=project_id,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        direct_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- Agent context (project/branch names for UI) ---

@app.get("/agent/context")
async def agent_context(
    project_id: str = Query(..., description="Project ID"),
    branch_id: str = Query(..., description="Branch ID"),
):
    """Return project and branch display names for the agent chat UI."""
    try:
        UUID(project_id)
        UUID(branch_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project_id or branch_id")
    proj = fetch_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    branch = fetch_branch(branch_id)
    if not branch or str(branch.get("project_id")) != str(project_id):
        raise HTTPException(status_code=404, detail="Branch not found")
    return {
        "project_name": proj.get("name", "Unknown"),
        "branch_name": branch.get("name", "Unknown"),
    }


# -- Agent config (IfcAgent saved models) CRUD ---

@app.get("/agent/configs")
async def list_agent_configs(
    project_id: str = Query(..., description="Project ID"),
):
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project_id")
    return fetch_agent_configs_for_project(project_id)


@app.post("/agent/configs", status_code=201)
async def create_config(body: dict = Body(...)):
    project_id = body.get("projectId")
    name = body.get("name")
    provider = body.get("provider")
    model_name = body.get("model")
    api_key = body.get("apiKey", "")
    base_url = body.get("baseUrl")
    pre_prompt = body.get("prePrompt")

    if not project_id or not name or not provider or not model_name:
        raise HTTPException(status_code=400, detail="projectId, name, provider, model required")
    if provider == "custom" and not base_url:
        raise HTTPException(status_code=400, detail="baseUrl required for custom provider")
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid projectId")

    return create_agent_config(project_id, name, provider, model_name, api_key, base_url, pre_prompt)


@app.put("/agent/configs/{config_id}")
async def update_config(config_id: str, body: dict = Body(...)):
    try:
        UUID(config_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid config_id")
    row = update_agent_config(
        config_id,
        name=body.get("name"),
        provider=body.get("provider"),
        model=body.get("model"),
        api_key=body.get("apiKey"),
        base_url=body.get("baseUrl"),
        pre_prompt=body.get("prePrompt"),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return row


@app.delete("/agent/configs/{config_id}")
async def delete_config(config_id: str):
    try:
        UUID(config_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid config_id")
    if not delete_agent_config(config_id):
        raise HTTPException(status_code=404, detail="Config not found")
    return {"deleted": True}


# -- Agent chat CRUD ---

@app.get("/agent/chats")
async def list_agent_chats(
    project_id: str = Query(...),
    branch_id: str | None = Query(None),
):
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project_id")
    return fetch_agent_chats(project_id, branch_id)


@app.post("/agent/chats", status_code=201)
async def create_chat(body: dict = Body(...)):
    project_id = body.get("projectId")
    branch_id = body.get("branchId")
    title = body.get("title", "New chat")
    if not project_id or not branch_id:
        raise HTTPException(status_code=400, detail="projectId and branchId required")
    try:
        UUID(project_id)
        UUID(branch_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid IDs")
    return create_agent_chat(project_id, branch_id, title)


@app.put("/agent/chats/{chat_id}")
async def rename_chat(chat_id: str, body: dict = Body(...)):
    try:
        UUID(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    title = body.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    row = update_agent_chat(chat_id, title)
    if row is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return row


@app.delete("/agent/chats/{chat_id}")
async def remove_chat(chat_id: str):
    try:
        UUID(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    if not delete_agent_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"deleted": True}


@app.get("/agent/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: str):
    try:
        UUID(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    return fetch_chat_messages(chat_id)


@app.get("/agent/chats/{chat_id}/live-state")
async def get_chat_live_state(chat_id: str):
    """Return in-flight stream snapshot for a chat, if currently running."""
    try:
        UUID(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    snapshot = await live_chat_streams.snapshot(chat_id)
    if not snapshot or snapshot.get("status") != "running":
        return {"running": False}
    return {"running": True, **snapshot}


@app.get("/agent/chats/{chat_id}/live-stream")
async def stream_chat_live(chat_id: str):
    """SSE stream for an in-progress chat response (refresh-resumable)."""
    try:
        UUID(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")

    async def event_generator():
        queue = await live_chat_streams.subscribe(chat_id)
        if queue is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await live_chat_streams.unsubscribe(chat_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stream/agent-events")
async def stream_agent_events(
    branch_id: str = Query(..., description="Branch ID (UUID) to subscribe to"),
):
    """SSE endpoint for real-time agent event notifications.

    Pushes events when the agent applies filters (filter-applied),
    reports progress (agent-thinking), or encounters errors (agent-error).
    """
    try:
        UUID(branch_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid branch_id")

    from .services.agent.events import event_bus

    queue = event_bus.subscribe(branch_id)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'branchId': branch_id})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(branch_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
