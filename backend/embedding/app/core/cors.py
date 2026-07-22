"""CORS middleware setup for the embedding service."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(app: FastAPI) -> None:
    """Allow only explicitly configured internal origins."""
    origins = [value.strip() for value in os.getenv("INTERNAL_CORS_ORIGINS", "").split(",") if value.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "X-Internal-Auth", "X-Request-ID", "X-Trace-ID"],
    )
