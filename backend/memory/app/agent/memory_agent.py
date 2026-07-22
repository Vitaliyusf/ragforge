"""LangChain tool-calling agent for intelligent memory management.

The agent reviews a conversation and existing memories, then decides which
memories to add, update, or delete to keep the set concise and non-redundant.
It calls vLLM directly via the OpenAI-compatible API (no Kafka hop needed).
"""
from __future__ import annotations

from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool

from app.core.config import settings
from app.services.memory_service import LongTermMemoryService
from app.core.logging_config import ServiceLogger


_SYSTEM_PROMPT = """\
You are a memory curator for an AI assistant. Your job is to keep the \
long-term memory concise, accurate, and non-redundant.

Given:
- The most recent conversation
- The existing memory entries (with their IDs)

Your tasks:
1. Identify duplicate or near-duplicate memories and merge them (use update_memory).
2. Remove entries that are no longer relevant or are superseded (use delete_memory).
3. Add genuinely new insights from the conversation (use add_memory).
4. Keep every memory entry as a single concise sentence (max ~120 chars).
5. Do not create more than 3 new memories per conversation.

Finish by calling the 'done' tool with a one-line summary of what you changed.\
"""


class MemoryAgent:
    """LangChain tool-calling agent that manages long-term memories."""

    def __init__(
        self,
        memory_service: LongTermMemoryService,
        logger: ServiceLogger,
        vllm_base_url: str = "http://vllm:8000/v1",
        model: str = "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
    ) -> None:
        self.memory_service = memory_service
        self.logger = logger
        self._vllm_base_url = vllm_base_url
        self._model = model

    def _build_agent(self, chat_id: str):
        """Build a fresh agent (LLM client is stateless).

        Args:
            chat_id: ID of the chat being processed, stored in memory metadata.
        """
        llm = ChatOpenAI(
            base_url=self._vllm_base_url,
            api_key=settings.vllm_api_key,
            model=self._model,
            temperature=0.2,
            max_tokens=512,
        )

        memory_svc = self.memory_service  # captured in closure for tools
        _chat_id = chat_id  # captured in closure for metadata

        @tool
        def list_memories() -> List[Dict[str, Any]]:
            """Return all current long-term memory entries (excluding user_insight)."""
            all_mems = memory_svc.get_all_memories()
            return [
                {"id": m["id"], "content": m["content"], "category": m.get("category", "")}
                for m in all_mems
                if m.get("category") != "user_insight"
            ]

        @tool
        def add_memory(content: str, category: str = "chat_insight") -> str:
            """Add a new concise memory entry.

            Args:
                content: A single sentence describing the insight (max 120 chars).
                category: Category label, e.g. 'chat_insight' or 'user_preference'.
            """
            mem = memory_svc.create_memory(content, category, {"source": "agent", "chat_id": _chat_id})
            return f"Created memory {mem['id']}"

        @tool
        def update_memory(memory_id: str, content: str) -> str:
            """Overwrite the content of an existing memory entry.

            Args:
                memory_id: The ID of the memory to update.
                content: New concise content (max 120 chars).
            """
            try:
                memory_svc.update_memory(memory_id, content=content)
                return f"Updated memory {memory_id}"
            except Exception as exc:
                return f"Failed to update {memory_id}: {exc}"

        @tool
        def delete_memory(memory_id: str) -> str:
            """Permanently delete a redundant or outdated memory entry.

            Args:
                memory_id: The ID of the memory to delete.
            """
            try:
                memory_svc.delete_memory(memory_id)
                return f"Deleted memory {memory_id}"
            except Exception as exc:
                return f"Failed to delete {memory_id}: {exc}"

        @tool
        def done(summary: str) -> str:
            """Signal that memory curation is complete.

            Args:
                summary: One-line description of the changes made.
            """
            return f"Memory curation complete: {summary}"

        tools = [list_memories, add_memory, update_memory, delete_memory, done]

        return create_agent(
            model=llm,
            tools=tools,
            system_prompt=_SYSTEM_PROMPT,
        )

    @staticmethod
    def _extract_summary(result: Dict[str, Any]) -> str:
        """Normalize the final agent message across LangChain result shapes."""
        messages = result.get("messages") or []
        if not messages:
            return ""

        last_message = messages[-1]
        content = getattr(last_message, "content", last_message)
        if content is None:
            return ""

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif item is not None:
                    parts.append(str(item))
            return "".join(parts).strip()

        return str(content).strip()

    def run(self, conversation: str, chat_id: str) -> Dict[str, Any]:
        """Run the memory curation agent.

        Args:
            conversation: Formatted string of the current chat (e.g. "User: ...\nAssistant: ...").
            chat_id: ID of the chat being processed (for logging).

        Returns:
            Dict with 'status' and 'summary' keys.
        """
        try:
            agent = self._build_agent(chat_id)
            user_input = (
                f"Conversation to analyse:\n{conversation}\n\n"
                "Please curate the long-term memories now."
            )
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config={"recursion_limit": 20},
            )
            summary = self._extract_summary(result)
            self.logger.log(
                "memory_agent:run",
                "Memory curation completed",
                {"chat_id": chat_id, "summary": summary[:120]},
            )
            return {"status": "success", "summary": summary}
        except Exception as exc:
            self.logger.log(
                "memory_agent:run",
                "Memory agent error",
                {
                    "chat_id": chat_id,
                    "error": str(exc),
                    "vllm_url": self._vllm_base_url,
                    "model": self._model,
                },
                "E",
            )
            return {"status": "error", "summary": str(exc)}
