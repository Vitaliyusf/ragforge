"""Security audit logging.

Records all security-relevant events to MongoDB for compliance,
forensics, and the security dashboard.

Usage:
    from shared.audit import AuditLogger

    audit = AuditLogger(db_collection=db["audit_log"])
    audit.log("auth_failure", source_ip="192.168.1.1", details={"reason": "invalid_key"})
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("audit")


class AuditEventType:
    """Standard audit event types."""
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    PROMPT_BLOCKED = "prompt_blocked"
    PROMPT_FLAGGED = "prompt_flagged"
    OUTPUT_FLAGGED = "output_flagged"
    RATE_LIMITED = "rate_limited"
    DLQ_MESSAGE = "dlq_message"
    CONFIG_CHANGE = "config_change"
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    TRAINING_STARTED = "training_started"
    TRAINING_COMPLETED = "training_completed"


class AuditLogger:
    """
    Writes security audit events to MongoDB.

    Each event includes:
    - timestamp (UTC)
    - event_type (from AuditEventType)
    - source_ip
    - user_agent
    - api_key_id (if authenticated)
    - details (event-specific data)

    The audit_log collection has a 90-day TTL index.
    """

    def __init__(self, db_collection: Any = None) -> None:
        """
        Args:
            db_collection: pymongo Collection for audit_log
                          (None = log-only mode, no persistence)
        """
        self._collection = db_collection
        self._total_events = 0
        self._events_by_type: Dict[str, int] = {}

    def log(
        self,
        event_type: str,
        source_ip: str = "unknown",
        user_agent: str = "",
        api_key_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record an audit event.

        Args:
            event_type: Type of event (use AuditEventType constants)
            source_ip: Client IP address
            user_agent: Client user-agent string
            api_key_id: Authenticated API key ID (if available)
            details: Event-specific details

        Returns:
            The audit event dict
        """
        event = {
            "timestamp": datetime.now(timezone.utc),
            "event_type": event_type,
            "source_ip": source_ip,
            "user_agent": user_agent[:500] if user_agent else "",
            "api_key_id": api_key_id,
            "details": details or {},
        }

        # Persist to MongoDB
        if self._collection is not None:
            try:
                self._collection.insert_one(event.copy())
            except Exception as e:
                logger.error(f"Failed to persist audit event: {e}")

        # Always log to application log
        logger.info(
            f"AUDIT [{event_type}] ip={source_ip} "
            f"key={api_key_id or 'none'} details={details}"
        )

        # Update metrics
        self._total_events += 1
        self._events_by_type[event_type] = self._events_by_type.get(event_type, 0) + 1

        return event

    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """
        Query recent audit events.

        Args:
            event_type: Filter by event type (None = all types)
            limit: Maximum events to return

        Returns:
            List of audit event dicts
        """
        if self._collection is None:
            return []

        query = {}
        if event_type:
            query["event_type"] = event_type

        try:
            cursor = self._collection.find(
                query,
                {"_id": 0},
            ).sort("timestamp", -1).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []

    @property
    def metrics(self) -> Dict[str, Any]:
        """Audit metrics for monitoring."""
        return {
            "total_events": self._total_events,
            "by_type": dict(self._events_by_type),
        }
