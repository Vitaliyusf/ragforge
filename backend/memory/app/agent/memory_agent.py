"""Bounded policy layer for long-term memory lifecycle decisions.

The model proposes a plan; this module validates the whole plan before any
mutation and delegates persistence to :class:`LongTermMemoryService`.  It does
not query MongoDB/Qdrant directly and it never accepts authorization scope from
model output.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from uuid import uuid4

from shared.metrics import METRICS


ALLOWED_ACTIONS = frozenset(
    {"ignore", "create", "update", "supersede", "merge_suggestion", "delete"}
)
DESTRUCTIVE_ACTIONS = frozenset({"supersede", "delete"})
SCHEMA_VERSION = "memory_curation.action.v2"
SCHEMA_SHA256 = hashlib.sha256(
    b"ignore|create|update|supersede|merge_suggestion|delete;bounded-candidate-ids;server-scope"
).hexdigest()


class MemoryAgentError(RuntimeError):
    """Base error for bounded policy failures."""


class MemoryAgentLLMError(MemoryAgentError):
    """Typed model-control failure used to select a bounded retry budget."""

    def __init__(self, message: str, *, kind: str = "provider") -> None:
        super().__init__(message)
        self.kind = kind


class MemoryAgentValidationError(MemoryAgentError):
    """A parsed plan failed deterministic business validation."""

    def __init__(self, errors: Sequence[str], *, destructive: bool = False) -> None:
        self.errors = list(errors)
        self.destructive = destructive
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class RetryBudgets:
    """Independent correction budgets. Counts are retries, not attempts."""

    structured_output: int = 1
    business_validation: int = 1
    tool_validation: int = 0
    provider: int = 1


@dataclass(frozen=True)
class AgentScope:
    """Authorization scope supplied by trusted server context only."""

    tenant_id: str
    user_id: str
    role: str
    request_id: str
    trace_id: str
    chat_id: Optional[str] = None
    delete_authorized: bool = False

    def validate(self) -> None:
        if not self.tenant_id or not self.user_id:
            raise MemoryAgentError("tenant_id and user_id are required")
        if self.role not in {"user", "admin", "service"}:
            raise MemoryAgentError("role is invalid")


@dataclass
class AgentRunResult:
    """Replayable result of one policy run."""

    status: str
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    mutations: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class MemoryAgent:
    """Validate and apply one bounded, typed memory curation plan."""

    def __init__(
        self,
        memory_service: Any,
        llm_call: Callable[[str, Dict[str, Any], float], Dict[str, Any]],
        logger: Any,
        *,
        candidate_limit: int = 10,
        history_limit: int = 24,
        message_char_limit: int = 4000,
        content_char_limit: int = 500,
        retry_budgets: RetryBudgets = RetryBudgets(),
    ) -> None:
        self.memory_service = memory_service
        self.llm_call = llm_call
        self.logger = logger
        self.candidate_limit = max(1, candidate_limit)
        self.history_limit = max(1, history_limit)
        self.message_char_limit = max(32, message_char_limit)
        self.content_char_limit = max(32, content_char_limit)
        self.retry_budgets = retry_budgets

    @staticmethod
    def _memory_text(memory: Mapping[str, Any]) -> str:
        content = memory.get("content")
        if isinstance(content, Mapping):
            return str(content.get("text") or content.get("summary") or "")
        return str(content or "")

    def _bounded_history(self, history: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
        bounded: List[Dict[str, str]] = []
        for message in list(history)[-self.history_limit :]:
            role = str(message.get("role") or "user").lower()
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            bounded.append(
                {
                    "role": role,
                    "content": str(message.get("content") or "")[: self.message_char_limit],
                }
            )
        return bounded

    def _bounded_candidates(
        self,
        memories: Sequence[Mapping[str, Any]],
        scope: AgentScope,
    ) -> List[Dict[str, Any]]:
        bounded: List[Dict[str, Any]] = []
        for memory in list(memories)[: self.candidate_limit]:
            memory_id = str(memory.get("id") or memory.get("memory_id") or "").strip()
            if not memory_id:
                continue
            owner_id = str(memory.get("owner_id") or memory.get("owner_user_id") or "")
            tenant_id = str(memory.get("tenant_id") or "")
            if owner_id and owner_id != scope.user_id:
                raise MemoryAgentError("bounded candidate owner does not match trusted scope")
            if tenant_id and tenant_id != scope.tenant_id:
                raise MemoryAgentError("bounded candidate tenant does not match trusted scope")
            bounded.append(
                {
                    "id": memory_id,
                    "content": self._memory_text(memory)[: self.content_char_limit],
                    "category": str(memory.get("category") or memory.get("memory_class") or "")[:80],
                    "fact_key": str(memory.get("fact_key") or "")[:120] or None,
                    "scope": memory.get("scope") if isinstance(memory.get("scope"), dict) else {},
                }
            )
        return bounded

    def _validate_plan(
        self,
        raw: Mapping[str, Any],
        allowed_ids: frozenset[str],
        existing_texts: frozenset[str],
        has_user_evidence: bool,
        scope: AgentScope,
    ) -> List[Dict[str, Any]]:
        actions = raw.get("actions")
        if not isinstance(actions, list):
            raise MemoryAgentValidationError(["actions must be an array"])
        if len(actions) > 10:
            raise MemoryAgentValidationError(["actions exceeds the bound of 10"])

        errors: List[str] = []
        normalized: List[Dict[str, Any]] = []
        destructive = False
        seen_targets: set[str] = set()
        forbidden_scope_fields = {"tenant_id", "user_id", "owner_id", "owner_user_id", "role"}
        for index, value in enumerate(actions):
            prefix = f"actions[{index}]"
            if not isinstance(value, Mapping):
                errors.append(f"{prefix} must be an object")
                continue
            injected = forbidden_scope_fields.intersection(value)
            if injected:
                errors.append(f"{prefix} contains server-owned scope fields")
            action = str(value.get("action") or "").strip().lower()
            memory_id = str(value.get("memory_id") or "").strip()
            content = str(value.get("content") or "").strip()
            if action not in ALLOWED_ACTIONS:
                errors.append(f"{prefix}.action is not allowed")
                continue
            if action in DESTRUCTIVE_ACTIONS:
                destructive = True
            if action == "create":
                if memory_id:
                    errors.append(f"{prefix}.memory_id is forbidden for create")
                if not content:
                    errors.append(f"{prefix}.content is required for create")
                if content.casefold() in existing_texts:
                    errors.append(f"{prefix}.content duplicates a supplied active memory")
            elif action in {"update", "supersede"}:
                if not memory_id or not content:
                    errors.append(f"{prefix} requires memory_id and content")
            elif action == "merge_suggestion":
                if not memory_id:
                    errors.append(f"{prefix}.memory_id is required for merge_suggestion")
            elif action == "delete":
                if not memory_id:
                    errors.append(f"{prefix}.memory_id is required for delete")
                if content:
                    errors.append(f"{prefix}.content is forbidden for delete")
                if not scope.delete_authorized:
                    errors.append(f"{prefix} delete lacks explicit product authorization")
            elif action == "ignore" and (memory_id or content):
                errors.append(f"{prefix} ignore forbids memory_id and content")

            if memory_id:
                if memory_id not in allowed_ids:
                    errors.append(f"{prefix}.memory_id is outside the bounded candidate set")
                if action in {"update", "supersede", "delete"} and memory_id in seen_targets:
                    errors.append(f"{prefix}.memory_id repeats a mutation target")
                seen_targets.add(memory_id)
            if content and (len(content) < 3 or len(content) > self.content_char_limit):
                errors.append(f"{prefix}.content length is invalid")
            if action in {"create", "update", "supersede", "delete"} and not (
                has_user_evidence or scope.role == "service"
            ):
                errors.append(f"{prefix} lacks user or approved product evidence")
            confidence = value.get("confidence")
            if confidence is not None and (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0 <= float(confidence) <= 1
            ):
                errors.append(f"{prefix}.confidence must be between 0 and 1")
            elif action in {"create", "update", "supersede"} and confidence is not None and confidence < 0.5:
                errors.append(f"{prefix}.confidence is below the memory-worthiness threshold")
            action_scope = value.get("scope")
            if action_scope is not None and (
                not isinstance(action_scope, Mapping) or len(action_scope) > 8
            ):
                errors.append(f"{prefix}.scope is invalid")
            normalized.append(
                {
                    "action": action,
                    "memory_id": memory_id or None,
                    "content": content or None,
                    "category": str(value.get("category") or "chat_insight")[:80],
                    "confidence": None if confidence is None else float(confidence),
                    "reason": str(value.get("reason") or "")[:240],
                    "fact_key": str(value.get("fact_key") or "")[:120] or None,
                    "scope": dict(action_scope) if isinstance(action_scope, Mapping) else {},
                }
            )
        if errors:
            raise MemoryAgentValidationError(errors, destructive=destructive)
        return normalized

    @staticmethod
    def _failure_kind(exc: Exception) -> str:
        kind = str(getattr(exc, "kind", "provider"))
        if kind in {"structured_output", "business_validation", "tool_validation", "provider"}:
            return kind
        if "structured" in kind or "validation" in kind:
            return "structured_output"
        return "provider"

    def _apply(
        self,
        decisions: Sequence[Mapping[str, Any]],
        scope: AgentScope,
        provenance: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        mutations: List[Dict[str, Any]] = []
        for decision in decisions:
            action = str(decision["action"])
            if action in {"ignore", "merge_suggestion"}:
                continue
            memory_id = decision.get("memory_id")
            if action == "delete":
                result = self.memory_service.delete_memory(str(memory_id))
            else:
                candidate = {
                    "content": {"text": decision["content"]},
                    "category": decision.get("category"),
                    "confidence": decision.get("confidence") if decision.get("confidence") is not None else 0.7,
                    "fact_key": decision.get("fact_key"),
                    "scope": decision.get("scope") or {},
                    "source": "memory_agent",
                    "provenance": {
                        "memory_agent": dict(provenance),
                        "chat_id": scope.chat_id,
                        "explicit_user_signal": True,
                    },
                }
                if action in {"update", "supersede"}:
                    candidate["supersedes"] = memory_id
                result = self.memory_service.write_memory(
                    candidate,
                    {
                        "tenant_id": scope.tenant_id,
                        "owner_id": scope.user_id,
                        "owner_type": "user",
                        "request_id": f"{scope.request_id}:memory-agent:{uuid4().hex}",
                        "trace_id": scope.trace_id,
                        "source": "memory_agent",
                    },
                )
            mutations.append({"action": action, "memory_id": memory_id, "result": result})
        return mutations

    def curate(
        self,
        conversation_history: Sequence[Mapping[str, Any]],
        existing_memory: Sequence[Mapping[str, Any]],
        scope: AgentScope,
        *,
        timeout: float,
    ) -> AgentRunResult:
        """Return a safe result; model failure never causes a mutation."""
        started = time.perf_counter()
        scope.validate()
        history = self._bounded_history(conversation_history)
        candidates = self._bounded_candidates(existing_memory, scope)
        allowed_ids = frozenset(str(item["id"]) for item in candidates)
        existing_texts = frozenset(str(item.get("content") or "").strip().casefold() for item in candidates)
        has_user_evidence = any(
            item["role"] == "user" and item["content"].strip() for item in history
        )
        feedback: Optional[str] = None
        retries = {"structured_output": 0, "business_validation": 0, "tool_validation": 0, "provider": 0}
        llm_provenance: Dict[str, Any] = {}
        decisions: List[Dict[str, Any]] = []
        outcome = "fallback"
        errors: List[str] = []

        while True:
            payload = {
                "conversation_history": history,
                "existing_memory": candidates,
                "deletion_authorized": scope.delete_authorized,
                "validation_feedback": feedback,
            }
            try:
                raw = self.llm_call("memory_curation", payload, timeout)
                llm_provenance = dict(raw.pop("__llm_provenance__", {}) or {})
                decisions = self._validate_plan(
                    raw,
                    allowed_ids,
                    existing_texts,
                    has_user_evidence,
                    scope,
                )
                outcome = "validated"
                break
            except MemoryAgentValidationError as exc:
                kind = "business_validation"
                errors = exc.errors
                if exc.destructive or retries[kind] >= self.retry_budgets.business_validation:
                    break
                retries[kind] += 1
                feedback = "; ".join(exc.errors)[:1000]
            except Exception as exc:
                kind = self._failure_kind(exc)
                errors = [str(exc)]
                budget = getattr(self.retry_budgets, kind)
                if retries[kind] >= budget:
                    break
                retries[kind] += 1
                feedback = f"Previous {kind} failure; return one complete valid object."[:1000]

        latency_ms = int((time.perf_counter() - started) * 1000)
        provenance = {
            "operation": "memory_curation",
            "policy_version": "memory-agent.v1",
            "schema_version": SCHEMA_VERSION,
            "schema_sha256": llm_provenance.get("schema_sha256") or SCHEMA_SHA256,
            "structured_output_transport": llm_provenance.get("structured_output_transport", "json_schema"),
            "model": llm_provenance.get("model"),
            "prompt_version": llm_provenance.get("prompt_version", "memory_curation.v2"),
            "usage": llm_provenance.get("usage", {}),
            "llm_latency_ms": llm_provenance.get("latency_ms"),
            "agent_latency_ms": latency_ms,
            "outcome": outcome,
            "retries": retries,
            "fallback": outcome != "validated",
            "candidate_count": len(candidates),
            "history_message_count": len(history),
        }
        METRICS.memory_agent_runs_total.labels(
            service="memory", operation="memory_curation", outcome=outcome
        ).inc()
        METRICS.memory_agent_duration.labels(service="memory", operation="memory_curation").observe(
            latency_ms / 1000
        )
        for kind, count in retries.items():
            if count:
                METRICS.memory_agent_retries_total.labels(service="memory", retry_class=kind).inc(count)

        if outcome != "validated":
            self.logger.log(
                "memory_agent:curate",
                "Memory policy degraded to a no-mutation fallback",
                {"outcome": outcome, "retry_counts": retries, "error_count": len(errors)},
                "E",
            )
            return AgentRunResult(status="fallback", provenance=provenance, errors=errors)

        try:
            mutations = self._apply(decisions, scope, provenance)
        except Exception as exc:
            errors = [str(exc)]
            provenance["outcome"] = "tool_validation_failed"
            provenance["fallback"] = True
            self.logger.log(
                "memory_agent:curate",
                "Validated memory action could not be applied",
                {"action_count": len(decisions), "error_type": type(exc).__name__},
                "E",
            )
            return AgentRunResult(
                status="fallback",
                decisions=decisions,
                provenance=provenance,
                errors=errors,
            )
        return AgentRunResult(
            status="success",
            decisions=decisions,
            mutations=mutations,
            provenance=provenance,
        )
