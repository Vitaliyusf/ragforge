"""Factory kept for import compatibility — gateway wires RPC client directly in main.py."""
from app.core.config import GatewayConfig


class MessageQueueFactory:
    @staticmethod
    def create_producer(config: GatewayConfig):
        return None

    @staticmethod
    def create_consumer(config: GatewayConfig, *args, **kwargs):
        return None
