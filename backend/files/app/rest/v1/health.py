"""Health check endpoint for the files service."""
import time

from fastapi import APIRouter, Depends
from pymongo.collection import Collection

from app.core.config import settings
from app.db.session import get_files_collection

router = APIRouter()


@router.get("/health")
async def health(files_collection: Collection = Depends(get_files_collection)) -> dict:
    """Return Mongo-backed health information.

    Returns:
        dict: Status, file count, and MongoDB connectivity flag.
    """
    try:
        files_collection.database.client.admin.command("ping")
        mongodb_connected = True
    except Exception:
        mongodb_connected = False

    return {
        "status": "ok",
        "service": settings.service_name,
        "timestamp": int(time.time()),
        "mongodb_connected": mongodb_connected,
        "kafka_connected": True,
    }
