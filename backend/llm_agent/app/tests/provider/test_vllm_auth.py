"""Authentication regression tests for the protected vLLM boundary."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.llm.implementations.vllm import VLLMClient
from app.llm.interfaces import LLMInvocation, ProviderProtocolError


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


def test_model_listing_uses_vllm_bearer_authentication():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": [{"id": "model-a"}]}
    get = Mock(return_value=response)
    client = VLLMClient(_config(), http_client=Mock(get=get))
    assert client.list_models() == ["model-a"]
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer private-vllm-token"}


def test_model_info_uses_collection_without_model_specific_probe():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": [{"id": "model-a", "max_model_len": 10240}]
    }
    get = Mock(return_value=response)
    client = VLLMClient(_config(), http_client=Mock(get=get))
    assert client.get_model_info("model-a") == {
        "id": "model-a",
        "max_model_len": 10240,
    }
    assert get.call_args.args[0] == "http://vllm:8000/v1/models"


def _completion_response(text='{"ok":true}'):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"text": text, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    return response


def test_json_schema_transport_uses_response_format_without_legacy_fallback():
    post = Mock(return_value=_completion_response())
    client = VLLMClient(_config(), http_client=Mock(post=post))
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }

    client.generate(
        LLMInvocation(
            system_prompt="system",
            raw_prompt="prompt",
            model="model-a",
            metadata={
                "structured_output_hint": "json_object",
                "structured_output_transport": "json_schema",
                "structured_output_schema": schema,
            },
        )
    )

    payload = post.call_args.kwargs["json"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"] == schema
    assert "guided_json" not in payload


def test_unsupported_structured_transport_fails_explicitly():
    post = Mock()
    client = VLLMClient(_config(), http_client=Mock(post=post))

    with pytest.raises(ProviderProtocolError, match="Unsupported"):
        client.generate(
            LLMInvocation(
                system_prompt="system",
                raw_prompt="prompt",
                model="model-a",
                metadata={
                    "structured_output_hint": "json_object",
                    "structured_output_transport": "unknown",
                },
            )
        )

    post.assert_not_called()


def test_json_schema_capability_probe_proves_enforcement_and_uses_auth():
    post = Mock(return_value=_completion_response('{"probe_value":7}'))
    client = VLLMClient(_config(), http_client=Mock(post=post))

    assert client.probe_json_schema_support("model-a") == {
        "transport": "json_schema",
        "schema_enforced": True,
    }
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer private-vllm-token"
    }
    schema = post.call_args.kwargs["json"]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["probe_value"]["const"] == 7


def test_json_schema_capability_probe_rejects_unenforced_output():
    post = Mock(return_value=_completion_response('{"probe_value":"wrong"}'))
    client = VLLMClient(_config(), http_client=Mock(post=post))

    with pytest.raises(ProviderProtocolError, match="did not enforce"):
        client.probe_json_schema_support("model-a")
