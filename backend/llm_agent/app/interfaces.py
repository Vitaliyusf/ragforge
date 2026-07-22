"""Consolidated interfaces module for llm_agent service."""
from app.messaging.interfaces import IProducer, IConsumer
from app.llm.interfaces import ILLMClient
from app.cache.interfaces import IModelCache

__all__ = ["IProducer", "IConsumer", "ILLMClient", "IModelCache"]
