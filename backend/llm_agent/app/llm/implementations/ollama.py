"""Ollama LLM client implementation."""
from __future__ import annotations

import json
from typing import List

import httpx

from app.core.config import Settings
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage


class OllamaClient(ILLMClient):
    """Ollama LLM client implementation."""

    def __init__(self, config: Settings):
        self.config = config
        self.base_url = config.ollama_url

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """Generate text from a prompt using Ollama."""
        prompt = invocation.to_prompt()
        prompt_length = len(prompt)
        max_length = 100000

        if "TL;DR" in prompt or "summary" in prompt.lower() or prompt_length > 5000:
            max_length = 8000

        if prompt_length > max_length:
            prompt = prompt[:max_length]

        try:
            if invocation.streaming:
                return self._stream_generate(invocation, prompt)
            return self._generate_once(invocation, prompt)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 500:
                raise RuntimeError(
                    "Ollama server error (500). This may be caused by prompt size, model limits, or insufficient resources."
                ) from exc
            raise RuntimeError(f"Error generating text: {str(exc)}") from exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Ollama request timed out at {self.base_url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Error generating text: {str(exc)}") from exc

    def _generate_once(self, invocation: LLMInvocation, prompt: str) -> LLMGenerationResult:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": invocation.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=invocation.timeout,
        )
        response.raise_for_status()
        result = response.json()
        usage = LLMUsage(
            provider="ollama",
            input_tokens=result.get("prompt_eval_count"),
            output_tokens=result.get("eval_count"),
            total_tokens=_sum_optional(result.get("prompt_eval_count"), result.get("eval_count")),
        )
        return LLMGenerationResult(
            raw_output=result.get("response", ""),
            usage=usage,
            finish_reason="completed",
        )

    def _stream_generate(self, invocation: LLMInvocation, prompt: str) -> LLMGenerationResult:
        chunks = []
        input_tokens = None
        output_tokens = None

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json={
                "model": invocation.model,
                "prompt": prompt,
                "stream": True,
            },
            timeout=invocation.timeout,
        ) as response:
            response.raise_for_status()
            for index, line in enumerate(response.iter_lines()):
                if not line:
                    continue
                payload = json.loads(line)
                token = payload.get("response", "")
                if token:
                    chunks.append(token)
                    if invocation.on_token is not None:
                        invocation.on_token(token, index)
                if payload.get("done"):
                    input_tokens = payload.get("prompt_eval_count")
                    output_tokens = payload.get("eval_count")

        return LLMGenerationResult(
            raw_output="".join(chunks),
            usage=LLMUsage(
                provider="ollama",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=_sum_optional(input_tokens, output_tokens),
            ),
            finish_reason="completed",
        )

    def list_models(self) -> List[str]:
        """List available models from Ollama."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()

            models = []
            if "models" in data:
                for model in data["models"]:
                    model_name = model.get("name", "")
                    if ":" in model_name:
                        model_name = model_name.split(":")[0]
                    if model_name and model_name not in models:
                        models.append(model_name)

            return models
        except httpx.ConnectError:
            # Ollama not running — return empty list rather than crashing callers
            return []
        except httpx.TimeoutException:
            return []
        except Exception as exc:
            raise RuntimeError(f"Error listing models: {str(exc)}") from exc

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            return False


def _sum_optional(left: int | None, right: int | None) -> int | None:
    """Add token counts when both are available."""
    if left is None or right is None:
        return None
    return left + right
