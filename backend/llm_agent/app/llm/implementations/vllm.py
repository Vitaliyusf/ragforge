"""vLLM client implementation for concurrent inference and streaming."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Mapping, Optional

import httpx

from app.core.config import Settings
from app.llm.interfaces import (
    ILLMClient,
    LLMGenerationResult,
    LLMInvocation,
    LLMUsage,
    ProviderHTTPError,
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderTimeoutError,
)
from app.llm.provider_capacity import ProviderCapacity
from shared.metrics import METRICS


# Qwen3 is a reasoning model: over raw /v1/completions it emits a <think>…</think>
# block before its answer. That breaks JSON-only steps (thinking exhausts the token
# budget before any JSON) and leaks reasoning into chat answers. Prefilling the
# assistant turn with an already-closed, empty think block signals "reasoning done",
# so the model generates the final content directly — no thinking, no leaked tags.
_NO_THINK_SUFFIX = "\n\nAssistant:\n<think>\n\n</think>\n\n"


class VLLMClient(ILLMClient):
    """vLLM client for high-performance concurrent inference."""

    def __init__(self, config: Settings, http_client: Optional[httpx.Client] = None):
        self.config = config
        self.base_url = config.vllm_base_url
        self.service_name = getattr(config, "service_name", "llm_agent")
        self.headers = {"Authorization": f"Bearer {config.vllm_api_key}"}
        self.max_concurrent_requests = config.max_concurrent_requests
        self._capacity = ProviderCapacity(
            service=self.service_name,
            limit=self.max_concurrent_requests,
            admission_timeout=getattr(config, "provider_admission_timeout_seconds", 1.0),
        )
        self._connect_timeout = getattr(config, "vllm_connect_timeout", 5.0)
        self._write_timeout = getattr(config, "vllm_write_timeout", 10.0)
        self._pool_timeout = getattr(config, "vllm_pool_timeout", 1.0)
        self._default_read_timeout = getattr(config, "vllm_read_timeout", 60.0)
        limits = httpx.Limits(
            max_connections=self.max_concurrent_requests,
            max_keepalive_connections=self.max_concurrent_requests,
            keepalive_expiry=getattr(config, "vllm_keepalive_expiry", 30.0),
        )
        self._http = (
            http_client
            if http_client is not None
            else httpx.Client(
                headers=self.headers,
                limits=limits,
                timeout=self._timeout(self._default_read_timeout),
            )
        )
        self.default_max_tokens = config.vllm_max_tokens
        self.default_temperature = config.vllm_temperature
        self.default_top_p = config.vllm_top_p
        self.default_top_k = config.vllm_top_k

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """Generate text from a prompt using the vLLM OpenAI-compatible API."""
        with self._capacity.admit():
            return self._invoke_vllm(invocation)

    def _timeout(self, read_timeout: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self._connect_timeout,
            read=read_timeout,
            write=self._write_timeout,
            pool=self._pool_timeout,
        )

    def _invoke_vllm(self, invocation: LLMInvocation) -> LLMGenerationResult:
        payload = {
            "model": invocation.model,
            "prompt": f"{invocation.to_prompt()}{_NO_THINK_SUFFIX}",
            "max_tokens": invocation.max_tokens or self.default_max_tokens,
            "temperature": self.default_temperature,
            "top_p": self.default_top_p,
            "top_k": self.default_top_k,
            "stream": invocation.streaming,
        }
        if invocation.streaming:
            # vLLM emits authoritative token counts in a final, text-free SSE
            # event when this OpenAI-compatible stream option is enabled.
            payload["stream_options"] = {"include_usage": True}
        if invocation.metadata.get("structured_output_hint") == "json_object":
            payload["temperature"] = 0.0
            payload["stop"] = ["```"]
            # Grammar-constrain the output to a JSON object. Reasoning models
            # (e.g. Qwen3) otherwise emit <think>/prose around — or instead of —
            # the JSON the structured-output parsers require, which breaks
            # extraction. guided_json enforces this token-by-token so no
            # thinking/prose can precede the object.
            transport = invocation.metadata.get("structured_output_transport", "legacy")
            if transport == "json_schema":
                schema = invocation.metadata.get("structured_output_schema")
                if not isinstance(schema, Mapping):
                    raise ProviderProtocolError(
                        "JSON-schema transport requires an authoritative object schema"
                    )
                payload["response_format"] = self._json_schema_response_format(
                    "answer_evaluation", schema
                )
            elif transport == "legacy":
                payload["guided_json"] = {"type": "object"}
            else:
                raise ProviderProtocolError(
                    f"Unsupported structured-output transport: {transport!r}"
                )

        try:
            if invocation.streaming:
                return self._stream_generate(invocation, payload)
            return self._generate_once(invocation, payload)
        except httpx.ConnectError as exc:
            raise ProviderHTTPError(
                "The AI service is not available right now. Please try again in a moment."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 409, 415, 422}:
                raise ProviderProtocolError(
                    f"vLLM rejected the structured-output protocol (HTTP {exc.response.status_code})"
                ) from exc
            raise ProviderHTTPError(
                f"vLLM request failed (HTTP {exc.response.status_code})"
            ) from exc
        except httpx.PoolTimeout as exc:
            raise ProviderOverloadedError(
                "The vLLM HTTP connection pool is saturated. Please retry shortly."
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderTimeoutError(
                "The request took too long to process. Please try again."
            ) from exc
        except (httpx.ConnectTimeout, httpx.WriteTimeout) as exc:
            raise ProviderHTTPError("The vLLM HTTP transport timed out") from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The vLLM request timed out") from exc

    @staticmethod
    def _json_schema_response_format(name: str, schema: Mapping[str, Any]) -> Dict[str, Any]:
        """Build the OpenAI-compatible JSON Schema payload supported by vLLM 0.27.1."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "schema": dict(schema),
                "strict": True,
            },
        }

    def probe_json_schema_support(self, model: str, *, timeout: float = 30.0) -> Dict[str, Any]:
        """Prove schema enforcement with a tiny authenticated synthetic request."""
        schema = {
            "type": "object",
            "properties": {"probe_value": {"type": "integer", "const": 7}},
            "required": ["probe_value"],
            "additionalProperties": False,
        }
        payload: Dict[str, Any] = {
            "model": model,
            # Deliberately conflicts with the schema; enforcement must win.
            "prompt": f"Return probe_value as the string wrong.{_NO_THINK_SUFFIX}",
            "max_tokens": 32,
            "temperature": 0.0,
            "top_p": self.default_top_p,
            "top_k": self.default_top_k,
            "stream": False,
            "response_format": self._json_schema_response_format(
                "ragforge_structured_output_capability", schema
            ),
        }
        try:
            with self._capacity.admit():
                response = self._http.post(
                    f"{self.base_url}/v1/completions",
                    json=payload,
                    headers=self.headers,
                    timeout=self._timeout(timeout),
                )
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") if isinstance(body, dict) else None
            raw = choices[0].get("text") if choices else None
            parsed = json.loads(raw) if isinstance(raw, str) else None
        except httpx.HTTPStatusError as exc:
            raise ProviderProtocolError(
                f"vLLM does not accept JSON-schema response_format (HTTP {exc.response.status_code})"
            ) from exc
        except httpx.PoolTimeout as exc:
            raise ProviderOverloadedError(
                "The vLLM HTTP connection pool is saturated. Please retry shortly."
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderTimeoutError("JSON-schema capability probe timed out") from exc
        except (httpx.ConnectTimeout, httpx.WriteTimeout) as exc:
            raise ProviderHTTPError("JSON-schema capability probe transport timed out") from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("JSON-schema capability probe timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderHTTPError("JSON-schema capability probe could not reach vLLM") from exc
        except (json.JSONDecodeError, TypeError, ValueError, IndexError, AttributeError) as exc:
            raise ProviderProtocolError(
                "vLLM accepted JSON-schema response_format but returned invalid JSON"
            ) from exc
        if parsed != {"probe_value": 7}:
            raise ProviderProtocolError(
                "vLLM accepted JSON-schema response_format but did not enforce the schema"
            )
        return {"transport": "json_schema", "schema_enforced": True}

    def _generate_once(self, invocation: LLMInvocation, payload: Dict[str, object]) -> LLMGenerationResult:
        response = self._http.post(
            f"{self.base_url}/v1/completions",
            json=payload,
            headers=self.headers,
            timeout=self._timeout(invocation.timeout),
        )
        response.raise_for_status()
        result = response.json()
        usage = result.get("usage", {})
        raw_output = ""
        finish_reason = "completed"
        if result.get("choices"):
            choice = result["choices"][0]
            raw_output = choice.get("text", "")
            finish_reason = choice.get("finish_reason") or finish_reason
        return LLMGenerationResult(
            raw_output=raw_output,
            usage=LLMUsage(
                provider="vllm",
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            finish_reason=finish_reason,
        )

    def _stream_generate(self, invocation: LLMInvocation, payload: Dict[str, object]) -> LLMGenerationResult:
        chunks: List[str] = []
        finish_reason = "completed"
        usage = LLMUsage(provider="vllm")

        started = time.perf_counter()
        first_token_observed = False
        with self._http.stream(
            "POST",
            f"{self.base_url}/v1/completions",
            json=payload,
            headers=self.headers,
            timeout=self._timeout(invocation.timeout),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                payload_chunk = json.loads(data)
                provider_usage = payload_chunk.get("usage")
                if isinstance(provider_usage, dict):
                    usage = LLMUsage(
                        provider="vllm",
                        input_tokens=provider_usage.get("prompt_tokens"),
                        output_tokens=provider_usage.get("completion_tokens"),
                        total_tokens=provider_usage.get("total_tokens"),
                    )
                choices = payload_chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                token = choice.get("text", "")
                if token:
                    if not first_token_observed:
                        METRICS.vllm_ttft_seconds.labels(service=self.service_name).observe(
                            time.perf_counter() - started
                        )
                        first_token_observed = True
                    index = len(chunks)
                    chunks.append(token)
                    if invocation.on_token is not None:
                        invocation.on_token(token, index)
                finish_reason = choice.get("finish_reason") or finish_reason

        return LLMGenerationResult(
            raw_output="".join(chunks),
            usage=usage,
            finish_reason=finish_reason,
        )

    def list_models(self) -> List[str]:
        """List available models from the vLLM server."""
        try:
            response = self._http.get(
                f"{self.base_url}/v1/models",
                headers=self.headers,
                timeout=self._timeout(5.0),
            )
            response.raise_for_status()
            data = response.json()
            models = []
            if "data" in data:
                for model in data["data"]:
                    model_id = model.get("id", "")
                    if model_id and model_id not in models:
                        models.append(model_id)
            return models
        except httpx.ConnectError:
            # vLLM not reachable — return empty list rather than crashing callers
            return []
        except httpx.TimeoutException:
            return []
        except Exception as exc:
            raise RuntimeError(f"Error listing models: {str(exc)}") from exc

    def get_context_window(self, model: str) -> Optional[int]:
        """Return the served context window in tokens, or None if unavailable.

        vLLM reports ``max_model_len`` per model on /v1/models, which is the
        authoritative value for whatever ``--max-model-len`` the server booted
        with. Returns None (rather than raising) when the server is not up yet
        so callers can fall back to the configured value.
        """
        try:
            response = self._http.get(
                f"{self.base_url}/v1/models",
                headers=self.headers,
                timeout=self._timeout(5.0),
            )
            response.raise_for_status()
            entries = response.json().get("data") or []
        except Exception:
            return None

        for entry in entries:
            if entry.get("id") == model and entry.get("max_model_len"):
                return int(entry["max_model_len"])
        # Single-model servers are the common case: accept the only window on offer.
        for entry in entries:
            if entry.get("max_model_len"):
                return int(entry["max_model_len"])
        return None

    def is_available(self) -> bool:
        """Check if vLLM server is available."""
        try:
            response = self._http.get(
                f"{self.base_url}/health",
                headers=self.headers,
                timeout=self._timeout(5.0),
            )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            return False

    def get_model_info(self, model: str) -> Optional[Dict]:
        """Get a model from the collection endpoint vLLM actually exposes."""
        try:
            response = self._http.get(
                f"{self.base_url}/v1/models",
                headers=self.headers,
                timeout=self._timeout(5.0),
            )
            response.raise_for_status()
            entries = response.json().get("data") or []
            return next((entry for entry in entries if entry.get("id") == model), None)
        except Exception:
            return None

    def shutdown(self) -> None:
        """Shutdown the client and clean up resources."""
        self._capacity.close()
        self._http.close()
