"""Base64 scalar for binary geometry blobs in GraphQL."""

import base64
from typing import NewType

import strawberry

Base64Bytes = strawberry.scalar(
    NewType("Base64Bytes", bytes),
    serialize=lambda v: base64.b64encode(v).decode("utf-8"),
    parse_value=lambda v: base64.b64decode(v.encode("utf-8")),
)
