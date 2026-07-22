"""Dependency-injection getters used by FastAPI route handlers via Depends().

All singletons live in app.main; getters here use deferred imports to avoid
circular-import issues at startup.
"""
from typing import List, Optional

from app.llm.interfaces import ILLMClient


def get_llm_client() -> Optional[ILLMClient]:
    """Return the active LLM client singleton."""
    from app.main import llm_client  # deferred — avoids circular import
    return llm_client


def get_consumers() -> List:
    """Return the list of active RabbitMQ consumers for liveness checks."""
    from app.main import _consumers  # deferred — avoids circular import
    return _consumers


def get_llm_service():
    """Return the LLMService singleton."""
    from app.main import llm_service  # deferred — avoids circular import
    if llm_service is None:
        raise RuntimeError("LLMService not initialised")
    return llm_service


def get_summary_service():
    """Return the SummaryService singleton."""
    from app.main import summary_service  # deferred — avoids circular import
    if summary_service is None:
        raise RuntimeError("SummaryService not initialised")
    return summary_service


def get_metadata_service():
    """Return the MetadataService singleton."""
    from app.main import metadata_service  # deferred — avoids circular import
    if metadata_service is None:
        raise RuntimeError("MetadataService not initialised")
    return metadata_service


def get_model_service():
    """Return the ModelService singleton."""
    from app.main import model_service  # deferred — avoids circular import
    if model_service is None:
        raise RuntimeError("ModelService not initialised")
    return model_service


def get_config_service():
    """Return the ConfigService singleton."""
    from app.main import config_service  # deferred — avoids circular import
    if config_service is None:
        raise RuntimeError("ConfigService not initialised")
    return config_service
