"""Exercise the llm_agent service layer token callback without messaging."""
import json
from uuid import uuid4

from app.main import llm_service
from app.schemas.llm import validate_model_execution_request_message


request_id = str(uuid4())
request = validate_model_execution_request_message(
    {
        "message_id": str(uuid4()),
        "message_type": "command",
        "action": "answer_generation",
        "source_service": "rag",
        "target_service": "llm_agent",
        "request_id": request_id,
        "trace_id": request_id,
        "correlation_id": str(uuid4()),
        "reply_to": "test.reply",
        "stream_to": "test.stream",
        "timestamp": 1,
        "payload": {
            "request_type": "answer_generation",
            "input": {
                "question": "Reply with exactly three words.",
                "retrieved_context": [],
                "instructions": "Use exactly three words.",
            },
            "metadata": {"request_id": request_id},
        },
    }
)

events = []
response = llm_service.execute(request, events.append)
print(
    json.dumps(
        {
            "status": response.status,
            "event_types": [event.event_type for event in events],
            "token_count": len([event for event in events if event.event_type == "llm.token"]),
            "raw_output": response.raw_output,
        }
    )
)
