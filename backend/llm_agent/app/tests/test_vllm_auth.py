"""Authentication regression tests for the protected vLLM boundary."""
from types import SimpleNamespace
from unittest.mock import Mock

from app.llm.implementations.vllm import VLLMClient


def _config():
    return SimpleNamespace(
        vllm_base_url="http://vllm:8000",
        vllm_api_key="private-vllm-token",
        max_concurrent_requests=1,
        vllm_max_tokens=128,
        vllm_temperature=0.1,
        vllm_top_p=0.9,
        vllm_top_k=20,
    )


def test_model_listing_uses_vllm_bearer_authentication(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": [{"id": "model-a"}]}
    get = Mock(return_value=response)
    monkeypatch.setattr("app.llm.implementations.vllm.httpx.get", get)

    client = VLLMClient(_config())
    assert client.list_models() == ["model-a"]
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer private-vllm-token"}
