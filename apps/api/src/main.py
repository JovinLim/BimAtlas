"""FastAPI app entry -- mounts Strawberry GraphQL.

Run with::

    uvicorn src.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

import strawberry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from .db import close_pool, init_pool
from .schema.queries import Query

logger = logging.getLogger("bimatlas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup / shutdown lifecycle."""
    logger.info("Starting BimAtlas API -- initialising connection pool")
    init_pool()
    yield
    logger.info("Shutting down BimAtlas API -- closing connection pool")
    close_pool()


schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(
    title="BimAtlas API",
    description="Extensible Spatial-Graph Engine for IFC models",
    version="0.1.0",
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
