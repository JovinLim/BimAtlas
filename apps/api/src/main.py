"""FastAPI app entry -- mounts Strawberry GraphQL.

Run with::

    uvicorn src.main:app --reload
"""

import json
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import strawberry
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from strawberry.fastapi import GraphQLRouter

from .db import (
    close_pool,
    fetch_branch,
    fetch_products_at_revision,
    get_latest_revision_id,
    init_pool,
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


def _stream_ifc_products_generator(
    branch_id: int,
    revision: int | None,
    ifc_class: str | None,
    ifc_classes: list[str] | None,
    contained_in: str | None,
    name: str | None,
    object_type: str | None,
    tag: str | None,
    description: str | None,
    global_id: str | None,
):
    """Yield SSE events for IFC products stream."""
    rev = revision
    if rev is None:
        rev = get_latest_revision_id(branch_id)
        if rev is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No revisions on this branch'})}\n\n"
            return

    rows = fetch_products_at_revision(
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
    )

    yield f"data: {json.dumps({'type': 'start', 'total': len(rows)})}\n\n"

    for i, row in enumerate(rows):
        product = row_to_stream_product(dict(row))
        yield f"data: {json.dumps({'type': 'product', 'product': product, 'current': i + 1, 'total': len(rows)})}\n\n"

    yield f"data: {json.dumps({'type': 'end'})}\n\n"


@app.get("/stream/ifc-products")
async def stream_ifc_products(
    branch_id: int = Query(..., description="Branch ID"),
    revision: int | None = Query(None, description="Revision ID (default: latest)"),
    ifc_class: str | None = Query(None, description="Filter by IFC class"),
    ifc_classes: list[str] | None = Query(None, description="Filter by IFC classes"),
    contained_in: str | None = Query(None, description="Filter by container GlobalId"),
    name: str | None = Query(None, description="Filter by name (ILIKE)"),
    object_type: str | None = Query(None, description="Filter by object type (ILIKE)"),
    tag: str | None = Query(None, description="Filter by tag (ILIKE)"),
    description: str | None = Query(None, description="Filter by description (ILIKE)"),
    global_id: str | None = Query(None, description="Filter by GlobalId (ILIKE)"),
):
    """Stream IFC products with geometry as Server-Sent Events.

    Events: start { total }, product { product, current, total }, end.
    """
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
    branch_id: int = Form(...),
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
        "branch_id": result.branch_id,
        "total_products": result.total_products,
        "added": result.added,
        "modified": result.modified,
        "deleted": result.deleted,
        "unchanged": result.unchanged,
        "edges_created": result.edges_created,
    }
