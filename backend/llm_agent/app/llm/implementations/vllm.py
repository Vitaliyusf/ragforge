"""vLLM client implementation for concurrent inference and streaming."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Dict, List, Optional

import httpx

from app.core.config import Settings
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage


# Qwen3 is a reasoning model: over raw /v1/completions it emits a <think>…</think>
# block before its answer. That breaks JSON-only steps (thinking exhausts the token
# budget before any JSON) and leaks reasoning into chat answers. Prefilling the
# assistant turn with an already-closed, empty think block signals "reasoning done",
# so the model generates the final content directly — no thinking, no leaked tags.
_NO_THINK_SUFFIX = "\n\nAssistant:\n<think>\n\n</think>\n\n"


class VLLMClient(ILLMClient):
    """vLLM client for high-performance concurrent inference."""

    def __init__(self, config: Settings):
        self.config = config
        self.base_url = config.vllm_base_url
        self.headers = {"Authorization": f"Bearer {config.vllm_api_key}"}
        self.max_concurrent_requests = config.max_concurrent_requests
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent_requests)
        self.default_max_tokens = config.vllm_max_tokens
        self.default_temperature = config.vllm_temperature
        self.default_top_p = config.vllm_top_p
        self.default_top_k = config.vllm_top_k

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """Generate text from a prompt using the vLLM OpenAI-compatible API."""
        future = self._executor.submit(self._invoke_vllm, invocation)
        try:
            return future.result(timeout=invocation.timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise RuntimeError(f"Request timed out after {invocation.timeout} seconds") from exc

    def _invoke_vllm(self, invocation: LLMInvocation) -> LLMGenerationResult:
        request_type = invocation.metadata.get("request_type")
        payload = {
            "model": invocation.model,
            "prompt": f"{invocation.to_prompt()}{_NO_THINK_SUFFIX}",
            "max_tokens": self.default_max_tokens,
            "temperature": self.default_temperature,
            "top_p": self.default_top_p,
            "top_k": self.default_top_k,
            "stream": invocation.streaming,
        }
        if invocation.metadata.get("structured_output_hint") == "json_object":
            payload["temperature"] = 0.0
            payload["stop"] = ["```"]
            # Grammar-constrain the output to a JSON object. Reasoning models
            # (e.g. Qwen3) otherwise emit <think>/prose around — or instead of —
            # the JSON the structured-output parsers require, which breaks
            # extraction. guided_json enforces this token-by-token so no
            # thinking/prose can precede the object.
            payload["guided_json"] = {"type": "object"}

        try:
            if invocation.streaming:
                return self._stream_generate(invocation, payload)
            return self._generate_once(invocation, payload)
        except httpx.ConnectError as exc:
            raise RuntimeError("The AI service is not available right now. Please try again in a moment.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError("The AI model is not ready yet. Please wait a moment and try again.") from exc
            raise RuntimeError("Something went wrong while generating the response. Please try again.") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("The request took too long to process. Please try again.") from exc

    def _generate_once(self, invocation: LLMInvocation, payload: Dict[str, object]) -> LLMGenerationResult:
        response = httpx.post(
            f"{self.base_url}/v1/completions",
            json=payload,
            headers=self.headers,
            timeout=invocation.timeout,
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

        with httpx.stream(
            "POST",
            f"{self.base_url}/v1/completions",
            json=payload,
            headers=self.headers,
            timeout=invocation.timeout,
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
                choices = payload_chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                token = choice.get("text", "")
                if token:
                    index = len(chunks)
                    chunks.append(token)
                    if invocation.on_token is not None:
                        invocation.on_token(token, index)
                finish_reason = choice.get("finish_reason") or finish_reason

        return LLMGenerationResult(
            raw_output="".join(chunks),
            usage=LLMUsage(provider="vllm"),
            finish_reason=finish_reason,
        )

    def list_models(self) -> List[str]:
        """List available models from the vLLM server."""
        try:
            response = httpx.get(f"{self.base_url}/v1/models", headers=self.headers, timeout=5.0)
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
            response = httpx.get(f"{self.base_url}/v1/models", headers=self.headers, timeout=5.0)
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
            response = httpx.get(f"{self.base_url}/health", headers=self.headers, timeout=5.0)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            return False

    def get_model_info(self, model: str) -> Optional[Dict]:
        """Get information about a specific model if the API exposes it."""
        try:
            response = httpx.get(f"{self.base_url}/v1/models/{model}", headers=self.headers, timeout=5.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def shutdown(self) -> None:
        """Shutdown the client and clean up resources."""
        self._executor.shutdown(wait=True)
