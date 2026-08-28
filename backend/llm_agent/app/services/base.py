"""Base service class shared by all llm_agent domain services."""
from abc import ABC

from app.llm.interfaces import ILLMClient
from shared.logging import ServiceLogger
from app.core.config import Settings


class BaseService(ABC):
    """Shared constructor for services that depend on an LLM client."""

    def __init__(
        self,
        llm_client: ILLMClient,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        self.llm_client = llm_client
        self.logger = logger
        self.config = config
