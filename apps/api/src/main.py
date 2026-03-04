"""FastAPI app entry -- mounts Strawberry GraphQL.

Run with::

    uvicorn src.main:app --reload
"""

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
    close_pool,
    delete_ifc_schema_with_rules,
    fetch_branch,
    fetch_applied_filter_sets,
    fetch_entities_at_revision,
    fetch_entities_with_filter_sets,
    fetch_entity_attributes_for_global_ids,
    fetch_shape_reps_for_products,
    get_latest_revision_seq,
    init_pool,
    insert_validation_rules,
    validation_schema_exists,
)
from .schema.queries import Mutation, Query as GraphQLQuery, row_to_stream_product
from .services.ifc.ingestion import ingest_ifc

logger = logging.getLogger("bimatlas")


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
    yield
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
    rows = fetch_entity_attributes_for_global_ids(rev, branch_id, global_ids)
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
