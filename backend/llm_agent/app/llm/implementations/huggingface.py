"""Hugging Face Transformers LLM client implementation."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, List, Optional

import torch
from transformers import pipeline

from app.core.config import Settings
from app.core.errors import StreamingNotSupportedException
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage


class HuggingFaceClient(ILLMClient):
    """Hugging Face Transformers client with model caching."""

    def __init__(self, config: Settings):
        self.config = config
        self.device = self._get_device()
        self.max_concurrent_requests = config.max_concurrent_requests
        self.default_max_length = config.hf_max_length
        self.default_temperature = config.hf_temperature
        self.default_top_p = config.hf_top_p
        self.default_do_sample = config.hf_do_sample
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent_requests)
        self._cache_lock = threading.Lock()
        self._model_cache: Dict[str, Dict[str, Any]] = {}

    def _get_device(self) -> str:
        if self.config.device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        return self.config.device

    def _task_for_model(self, model_name: str) -> str:
        lowered = model_name.lower()
        if "bart" in lowered and "mbart" not in lowered:
            return "summarization"
        if "t5" in lowered and "mt5" not in lowered:
            return "summarization"
        return "text-generation"

    def _pipeline_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if self.device == "cuda":
            kwargs["device"] = 0
            kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
        elif self.device == "mps":
            kwargs["device"] = "mps"
        else:
            kwargs["device"] = -1
        return kwargs

    def _get_or_load_model(self, model_name: str) -> Dict[str, Any]:
        with self._cache_lock:
            if model_name in self._model_cache:
                return self._model_cache[model_name]

        task = self._task_for_model(model_name)
        pipe = pipeline(task, model=model_name, **self._pipeline_kwargs())
        model_info = {"pipeline": pipe, "task": task, "loaded_at": time.time()}
        with self._cache_lock:
            self._model_cache[model_name] = model_info
        return model_info

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """Generate text using a cached transformers pipeline."""
        if invocation.streaming:
            raise StreamingNotSupportedException(
                "Streaming is not supported by the Hugging Face provider in llm_agent."
            )

        future = self._executor.submit(self._generate_once, invocation)
        try:
            return future.result(timeout=invocation.timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise RuntimeError(f"Request timed out after {invocation.timeout} seconds") from exc

    def _generate_once(self, invocation: LLMInvocation) -> LLMGenerationResult:
        model_data = self._get_or_load_model(invocation.model)
        pipe = model_data["pipeline"]
        task = model_data["task"]
        prompt = invocation.to_prompt()

        if task == "summarization":
            result = pipe(
                prompt,
                max_length=min(self.default_max_length, 512),
                min_length=30,
                do_sample=False,
            )
            if isinstance(result, list) and result:
                generated = result[0].get("summary_text", "") or result[0].get("generated_text", "")
            else:
                generated = str(result)
        else:
            result = pipe(
                prompt,
                max_length=self.default_max_length,
                temperature=self.default_temperature,
                top_p=self.default_top_p,
                do_sample=self.default_do_sample,
                num_return_sequences=1,
            )
            if isinstance(result, list) and result:
                generated = result[0].get("generated_text", "")
            else:
                generated = str(result)
            if generated.startswith(prompt):
                generated = generated[len(prompt) :].strip()

        return LLMGenerationResult(
            raw_output=generated,
            usage=LLMUsage(provider="huggingface"),
            finish_reason="completed",
        )

    def list_models(self) -> List[str]:
        """List cached model names."""
        with self._cache_lock:
            return list(self._model_cache.keys())

    def is_available(self) -> bool:
        """Check whether transformers is importable."""
        try:
            import transformers  # noqa: F401

            return True
        except ImportError:
            return False

    def preload_models(self, model_configs: Dict[str, str]) -> None:
        """Preload models in the background to improve response times."""

        def preload_task(model_name: str) -> None:
            try:
                self._get_or_load_model(model_name)
            except Exception:
                return None

        for model_name in model_configs.values():
            if model_name:
                self._executor.submit(preload_task, model_name)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return current cache metadata."""
        with self._cache_lock:
            return {
                "cache_size": len(self._model_cache),
                "cached_models": list(self._model_cache.keys()),
                "device": self.device,
                "max_concurrent_requests": self.max_concurrent_requests,
            }

    def get_model_info(self, model: str) -> Optional[Dict[str, Any]]:
        """Return cached model information if available."""
        with self._cache_lock:
            cached = self._model_cache.get(model)
            if not cached:
                return None
            return {
                "name": model,
                "task": cached.get("task"),
                "loaded_at": cached.get("loaded_at"),
            }

    def shutdown(self) -> None:
        """Shutdown background workers and clear caches."""
        self._executor.shutdown(wait=True)
        with self._cache_lock:
            self._model_cache.clear()
