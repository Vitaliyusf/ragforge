"""Typed schemas for llm_agent model execution and shared message envelopes."""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


RequestType = Literal[
    "answer_generation",
    "answer_evaluation",
    "content_risk_scan",
    "query_rewrite",
    "memory_extraction",
]
ReplyStatus = Literal["success", "error"]
MessageType = Literal["command", "query", "reply", "event", "stream_event"]
StreamEventType = Literal["llm.token", "llm.done", "llm.error"]


class StrictSchema(BaseModel):
    """Base schema with strict field handling."""

    model_config = ConfigDict(extra="forbid")


class ConversationMessage(StrictSchema):
    """Conversation history item."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class DebugOptions(StrictSchema):
    """Execution debug flags accepted from upstream callers."""

    include_visible_reasoning_steps: bool = True


class ContextPassage(StrictSchema):
    """One retrieved passage with a stable id the model can cite.

    Plain strings carry no identity, so a ``[1]`` marker in an answer cannot be
    resolved back to the chunk that supported it. Callers that want citation
    metrics send passages instead of strings; ``source_id`` is the retrieving
    service's chunk id and is what ``Citation.source_id`` reports back.
    """

    source_id: str
    text: str
    locator: Optional[str] = None


class ClaimAssessment(StrictSchema):
    """One atomic claim the judge extracted, and whether context supports it."""

    claim: str
    supported: bool
    supporting_passage_ids: List[str] = Field(default_factory=list)


class AnswerGenerationInput(StrictSchema):
    """Input fields for generating a final answer from retrieved context."""

    question: str
    retrieved_context: Union[str, List[str], List[ContextPassage]]
    conversation_history: Optional[List[ConversationMessage]] = None
    instructions: Optional[str] = None


class AnswerEvaluationInput(StrictSchema):
    """Input fields for scoring an answer against reference context."""

    question: str
    answer: str
    reference_context: Union[str, List[str], List[ContextPassage]]
    rubric: Optional[List[str]] = None


class ContentRiskScanInput(StrictSchema):
    """Input fields for classifying content risk and policy issues."""

    content: str
    policy_hints: Optional[List[str]] = None
    content_type: Optional[str] = None


class QueryRewriteInput(StrictSchema):
    """Input fields for rewriting a user query for retrieval or search."""

    query: str
    conversation_history: Optional[List[ConversationMessage]] = None
    rewrite_goal: Optional[str] = None


class MemoryExtractionInput(StrictSchema):
    """Input fields for extracting durable memory candidates from chat history."""

    conversation_history: List[ConversationMessage]
    existing_memory: Optional[List[Dict[str, Any]]] = None
    extraction_scope: Optional[str] = None


class ModelExecutionRequestBase(StrictSchema):
    """Typed inner request payload carried inside the shared envelope."""

    request_type: RequestType
    model: Optional[str] = None
    timeout: Optional[float] = None
    prompt_version: Optional[str] = None
    metadata: Dict[str, Any]
    debug: DebugOptions = Field(default_factory=DebugOptions)


class AnswerGenerationRequest(ModelExecutionRequestBase):
    """Typed request payload for `answer_generation` execution."""

    request_type: Literal["answer_generation"]
    input: AnswerGenerationInput


class AnswerEvaluationRequest(ModelExecutionRequestBase):
    """Typed request payload for `answer_evaluation` execution."""

    request_type: Literal["answer_evaluation"]
    input: AnswerEvaluationInput


class ContentRiskScanRequest(ModelExecutionRequestBase):
    """Typed request payload for `content_risk_scan` execution."""

    request_type: Literal["content_risk_scan"]
    input: ContentRiskScanInput


class QueryRewriteRequest(ModelExecutionRequestBase):
    """Typed request payload for `query_rewrite` execution."""

    request_type: Literal["query_rewrite"]
    input: QueryRewriteInput


class MemoryExtractionRequest(ModelExecutionRequestBase):
    """Typed request payload for `memory_extraction` execution."""

    request_type: Literal["memory_extraction"]
    input: MemoryExtractionInput


ModelExecutionRequest = Annotated[
    Union[
        AnswerGenerationRequest,
        AnswerEvaluationRequest,
        ContentRiskScanRequest,
        QueryRewriteRequest,
        MemoryExtractionRequest,
    ],
    Field(discriminator="request_type"),
]


class SharedMessageError(StrictSchema):
    """Shared error object used in reply and stream envelopes."""

    code: str
    message: str


class SharedEnvelopeBase(StrictSchema):
    """Global shared message envelope contract."""

    message_id: str
    message_type: MessageType
    action: str
    source_service: str
    target_service: str
    request_id: str
    trace_id: str
    correlation_id: str
    reply_to: Optional[str] = None
    stream_to: Optional[str] = None
    timestamp: int
    auth_context: Optional[str] = None
    traffic_class: Literal["live", "eval"] = "live"


class ModelExecutionRequestMessage(SharedEnvelopeBase):
    """Shared-envelope request for the typed llm_agent execution lane."""

    message_type: Literal["command", "query"]
    target_service: Literal["llm_agent"]
    payload: ModelExecutionRequest

    @model_validator(mode="after")
    def validate_action_matches_payload(self) -> "ModelExecutionRequestMessage":
        if self.action != self.payload.request_type:
            raise ValueError("action must match payload.request_type")
        return self


_REQUEST_MESSAGE_ADAPTER = TypeAdapter(ModelExecutionRequestMessage)


def validate_model_execution_request_message(payload: Dict[str, Any]) -> ModelExecutionRequestMessage:
    """Validate a raw inbound message into the shared typed request envelope."""
    return _REQUEST_MESSAGE_ADAPTER.validate_python(payload)


# Backward-compatible local alias for callers using the older request name.
validate_model_execution_request = validate_model_execution_request_message


class Citation(StrictSchema):
    """Optional citation metadata attached to generated answers."""

    source_id: Optional[str] = None
    locator: Optional[str] = None
    snippet: Optional[str] = None


class AnswerReviewParsedOutput(StrictSchema):
    """Shared answer-review contract returned by answer evaluation.

    Score fields are Optional so that partial evaluations (where the model omits
    one or more scores) do not hard-fail validation.  Callers must treat None
    scores as unavailable rather than zero.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    review_id: str
    verdict: str
    groundedness_score: Optional[float] = None
    completeness_score: Optional[float] = None
    safety_score: Optional[float] = None
    issues: List[str]
    claims: List[ClaimAssessment] = Field(default_factory=list)
    unsupported_claim_count: Optional[int] = None
    hallucination_verdict: Optional[str] = None
    revision_applied: bool
    model_name: str
    created_at: int


class RiskFlag(StrictSchema):
    """One structured policy or safety flag returned by a risk scan."""

    code: str
    span: Optional[str] = None
    rationale: str


class MemoryItem(StrictSchema):
    """One extracted memory candidate returned by memory extraction."""

    type: str
    content: str
    confidence: Union[float, str]
    action: str


class AnswerGenerationParsedOutput(StrictSchema):
    """Parsed answer-generation output returned inside typed replies.

    ``citations`` is an empty list when citation extraction ran and the
    model cited nothing, and None when it did not run at all (feature off,
    or no passage list available to resolve markers against).

    ``invalid_citation_count`` counts markers the model emitted that point
    outside the supplied passage range. They are discarded, never clamped
    onto a real passage, so this is the only place a bad citation is
    visible.
    """

    answer: str
    citations: Optional[List[Citation]] = None
    invalid_citation_count: Optional[int] = None
    confidence: Optional[str] = None


class ContentRiskScanParsedOutput(StrictSchema):
    """Parsed content-risk-scan output returned inside typed replies."""

    risk_level: str
    categories: List[str]
    flags: List[RiskFlag]
    summary: str


class QueryRewriteParsedOutput(StrictSchema):
    """Parsed query-rewrite output returned inside typed replies."""

    rewritten_query: str
    search_intent: Optional[str] = None


class MemoryExtractionParsedOutput(StrictSchema):
    """Parsed memory-extraction output returned inside typed replies."""

    memories: List[MemoryItem]


ParsedOutput = Union[
    AnswerGenerationParsedOutput,
    AnswerReviewParsedOutput,
    ContentRiskScanParsedOutput,
    QueryRewriteParsedOutput,
    MemoryExtractionParsedOutput,
]


class UsageInfo(StrictSchema):
    """Normalized provider token-usage metadata for one execution."""

    provider: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class TraceInfo(StrictSchema):
    """Trace identifiers attached to typed execution replies."""

    trace_id: str
    langsmith_run_id: Optional[str] = None
    langsmith_trace_url: Optional[str] = None


class ErrorEntry(StrictSchema):
    """One normalized error attached to a typed execution reply."""

    code: str
    message: str


class ModelExecutionResponsePayload(StrictSchema):
    """Normalized inner reply payload for llm_agent execution."""

    request_type: str
    status: ReplyStatus
    raw_prompt: str
    system_prompt: str
    visible_reasoning_steps: List[str]
    raw_output: str
    parsed_output: Optional[ParsedOutput] = None
    usage: UsageInfo
    latency_ms: int
    model: str
    prompt_version: str
    trace: TraceInfo
    errors: List[ErrorEntry] = Field(default_factory=list)


class ModelExecutionReplyMessage(SharedEnvelopeBase):
    """Shared-envelope reply for typed execution responses."""

    message_type: Literal["reply"] = "reply"
    success: bool
    payload: ModelExecutionResponsePayload
    error: Optional[SharedMessageError] = None


class ModelExecutionStreamPayload(StrictSchema):
    """Inner payload for shared stream-event messages."""

    event_type: StreamEventType
    data: Dict[str, Any]


class ModelExecutionStreamEventMessage(SharedEnvelopeBase):
    """Shared-envelope stream event for answer generation."""

    message_type: Literal["stream_event"] = "stream_event"
    action: Literal["answer_generation"] = "answer_generation"
    stream_to: str
    payload: ModelExecutionStreamPayload
