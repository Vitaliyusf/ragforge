"""Common utility functions for the gateway service."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import GatewayConfig


def setup_cors(app: FastAPI) -> None:
    """Setup CORS middleware for FastAPI app."""
    config = GatewayConfig()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Request-ID", "X-Trace-ID"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
