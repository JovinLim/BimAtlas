"""Database connection settings for BimAtlas API."""

import os

# PostgreSQL / Apache AGE connection settings
DB_HOST = os.getenv("BIMATLAS_DB_HOST", "localhost")
DB_PORT = int(os.getenv("BIMATLAS_DB_PORT", "5432"))
DB_NAME = os.getenv("BIMATLAS_DB_NAME", "bimatlas")
DB_USER = os.getenv("BIMATLAS_DB_USER", "bimatlas")
DB_PASSWORD = os.getenv("BIMATLAS_DB_PASSWORD", "bimatlas")

# AGE graph name
AGE_GRAPH = os.getenv("BIMATLAS_AGE_GRAPH", "bimatlas")
