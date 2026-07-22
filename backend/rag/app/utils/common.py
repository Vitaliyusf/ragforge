"""Common utility functions for the RAG service."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(app: FastAPI) -> None:
    """Setup CORS middleware for FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[__import__("os").getenv("FRONTEND_URL", "http://localhost:3000")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Internal-Auth", "Authorization", "X-Request-ID", "X-Trace-ID"],
    )
