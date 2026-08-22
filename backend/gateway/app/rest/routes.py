"""REST API routes configuration."""
from fastapi import FastAPI

from app.rest.v1 import admin_users, auth, chat, chat_history, config, files, health, llm, logs, long_term_memory, models, models_legacy, rag
from app.utils.common import setup_cors


def setup_routes(app: FastAPI) -> None:
    """Setup all API routes and CORS."""
    # Setup CORS
    setup_cors(app)
    
    # Mount v1 API routers
    app.include_router(auth.router, prefix="/v1")
    app.include_router(admin_users.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(llm.router, prefix="/v1")
    app.include_router(files.router, prefix="/v1")
    app.include_router(chat_history.router, prefix="/v1")
    app.include_router(models.router, prefix="/v1")
    app.include_router(models_legacy.router, prefix="/v1")
    app.include_router(config.router, prefix="/v1")
    app.include_router(logs.router, prefix="/v1")
    app.include_router(long_term_memory.router, prefix="/v1")
    app.include_router(rag.router, prefix="/v1")
    app.include_router(health.router)
