"""FastAPI app entry -- mounts Strawberry GraphQL.

Run with::

    uvicorn src.main:app --reload
"""

import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import strawberry
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from .db import close_pool, fetch_branch, init_pool
from .schema.queries import Mutation, Query
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


schema = strawberry.Schema(query=Query, mutation=Mutation)
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
