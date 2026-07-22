"""Compatibility checks for rag-originated typed llm-agent requests."""
from app.schemas.llm import validate_model_execution_request_message


def _base_envelope(action, payload):
    return {
        "message_id": "msg-1",
        "message_type": "query" if action != "answer_generation" else "command",
        "action": action,
        "source_service": "rag",
        "target_service": "llm_agent",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "rag.replies",
        "timestamp": 1730000000000,
        "payload": payload,
    }


def test_rag_content_risk_scan_envelope_validates_against_typed_schema():
    request = validate_model_execution_request_message(
        _base_envelope(
            "content_risk_scan",
            {
                "request_type": "content_risk_scan",
                "model": "test-model",
                "metadata": {
                    "conversation_id": "conv-1",
                    "turn_id": "turn-1",
                    "request_id": "req-1",
                    "trace_id": "trace-1",
                    "graph_run_id": "graph-1",
                    "stage": "input",
                    "mode": "regular",
                },
                "debug": {"include_visible_reasoning_steps": True},
                "input": {
                    "content": "What can you help me with?",
                    "policy_hints": ["prompt_injection"],
                    "content_type": "user_input",
                },
            },
        )
    )

    assert request.payload.request_type == "content_risk_scan"
    assert request.payload.input.content == "What can you help me with?"
    assert request.payload.metadata["graph_run_id"] == "graph-1"


def test_rag_answer_generation_envelope_validates_against_typed_schema():
    request = validate_model_execution_request_message(
        _base_envelope(
            "answer_generation",
            {
                "request_type": "answer_generation",
                "model": "test-model",
                "metadata": {
                    "conversation_id": "conv-1",
                    "turn_id": "turn-1",
                    "request_id": "req-1",
                    "trace_id": "trace-1",
                    "graph_run_id": "graph-1",
                    "mode": "extended",
                },
                "debug": {"include_visible_reasoning_steps": True},
                "input": {
                    "question": "What is RAG?",
                    "retrieved_context": ["Chunk one", "Chunk two"],
                    "conversation_history": [
                        {"role": "user", "content": "Earlier question"},
                        {"role": "assistant", "content": "Earlier answer"},
                    ],
                    "instructions": "Mode: extended\n\nConversation summary:\nEarlier summary",
                },
            },
        )
    )

    assert request.payload.request_type == "answer_generation"
    assert request.payload.input.question == "What is RAG?"
    assert request.payload.input.retrieved_context == ["Chunk one", "Chunk two"]
