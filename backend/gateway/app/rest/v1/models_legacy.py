"""Legacy models API routes."""
from fastapi import APIRouter, Depends

from app.core.config import GatewayConfig
from app.core.constants import ModelsAction
from app.core.deps import get_config, get_rabbitmq_client
from app.core.errors import handle_exception
from app.core.rabbitmq_client import RabbitMQClient
from app.core.auth import get_current_user

router = APIRouter(prefix="/models", tags=["models-legacy"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_models(
    rabbitmq_client: RabbitMQClient = Depends(get_rabbitmq_client),
    config: GatewayConfig = Depends(get_config),
):
    """Get available models (legacy endpoint)."""
    try:
        return await rabbitmq_client.send_request(
            config.request_topics["models"],
            {"action": ModelsAction.FETCH_MODELS},
            timeout=config.short_timeout,
        )
    except Exception as e:
        raise handle_exception(e)
