"""Abstract base class for all RAG service classes.

Every concrete service in the rag service layer inherits from BaseRAGService.
This enforces a standard (config, logger) constructor contract and gives
the service layer a common ancestor for isinstance checks and DI.
"""
from __future__ import annotations

from abc import ABC
from typing import Any

from app.core.config import RAGConfig


class BaseRAGService(ABC):
    """Shared foundation for all RAG service classes.

    Subclasses may extend __init__ with additional dependencies but must
    call ``super().__init__(config, logger)`` to satisfy the contract.
    """

    def __init__(self, config: RAGConfig, logger: Any) -> None:
        self.config = config
        self.logger = logger
