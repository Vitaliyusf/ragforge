"""Inspect the raw OpenAI-compatible SSE stream exposed by vLLM."""
import json

import httpx


base_url = "http://vllm:8000"
models = httpx.get(f"{base_url}/v1/models", timeout=10).json().get("data", [])
model = models[0]["id"]
chunks = []

with httpx.stream(
    "POST",
    f"{base_url}/v1/completions",
    json={
        "model": model,
        "prompt": "Reply with exactly three words:",
        "max_tokens": 12,
        "temperature": 0,
        "stream": True,
    },
    timeout=60,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            chunks.append(json.loads(line[5:].strip()).get("choices", [{}])[0].get("text", ""))

print(json.dumps({"chunk_count": len(chunks), "chunks": chunks, "text": "".join(chunks)}))
