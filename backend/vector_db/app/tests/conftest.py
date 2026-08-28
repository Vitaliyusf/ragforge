"""Fixtures shared by every vector_db lane.

None are autouse: each test names the store or service double it needs.
"""
from app.tests._vector_harness import (  # noqa: F401
    live_service,
    mock_logger,
    mock_producer,
    mock_qdrant_client,
    mock_vector_store,
    vector_service,
)
