"""Authoritative execution and checkpoint ordering for conversation turns."""
from __future__ import annotations

from typing import Dict, Literal, Optional, Tuple

from app.services.conversation_types import Mode


NodeName = Literal[
    "input_guardrails",
    "load_short_term_context",
    "load_memory_light",
    "retrieve_chunks_once",
    "generate_answer",
    "evaluate_answer_light",
    "load_memory_deep",
    "rewrite_or_decompose_query",
    "retrieve_pass_one",
    "retrieve_pass_two_if_needed",
    "rerank_and_merge",
    "generate_draft_answer",
    "evaluate_answer_deep",
    "revise_once_if_needed",
    "output_guardrails",
    "persist_turn",
    "stream_done",
]
CheckpointStage = Literal[
    "graph_start",
    "after_context_load",
    "after_retrieval",
    "after_pass_one",
    "after_pass_two",
    "after_final_ranking",
    "after_generation",
    "after_evaluation",
    "after_persistence",
]


EXECUTION_PATHS: Dict[Mode, Tuple[NodeName, ...]] = {
    "regular": (
        "input_guardrails",
        "load_short_term_context",
        "load_memory_light",
        "retrieve_chunks_once",
        "generate_answer",
        "evaluate_answer_light",
        "output_guardrails",
        "persist_turn",
        "stream_done",
    ),
    "extended": (
        "input_guardrails",
        "load_short_term_context",
        "load_memory_deep",
        "rewrite_or_decompose_query",
        "retrieve_pass_one",
        "retrieve_pass_two_if_needed",
        "rerank_and_merge",
        "generate_draft_answer",
        "evaluate_answer_deep",
        "revise_once_if_needed",
        "output_guardrails",
        "persist_turn",
        "stream_done",
    ),
}

_COMPLETED_NODE_BY_STAGE: Dict[Mode, Dict[str, NodeName]] = {
    "regular": {
        "after_context_load": "load_short_term_context",
        "after_retrieval": "retrieve_chunks_once",
        "after_generation": "generate_answer",
        "after_evaluation": "evaluate_answer_light",
        "after_persistence": "persist_turn",
    },
    "extended": {
        "after_context_load": "load_short_term_context",
        # Legacy checkpoints used one ambiguous retrieval stage. Resuming from
        # the Pass1 boundary is conservative: Pass2 may repeat, but cannot be
        # skipped along with the final rank.
        "after_retrieval": "retrieve_pass_one",
        "after_pass_one": "retrieve_pass_one",
        "after_pass_two": "retrieve_pass_two_if_needed",
        "after_final_ranking": "rerank_and_merge",
        "after_generation": "generate_draft_answer",
        "after_evaluation": "evaluate_answer_deep",
        "after_persistence": "persist_turn",
    },
}


def remaining_nodes(mode: Mode, stage: str) -> Optional[Tuple[NodeName, ...]]:
    """Return nodes after the durable milestone, or ``None`` if it is unknown."""
    path = EXECUTION_PATHS[mode]
    if stage == "graph_start":
        return path
    completed_node = _COMPLETED_NODE_BY_STAGE[mode].get(stage)
    if completed_node is None:
        return None
    return path[path.index(completed_node) + 1 :]
