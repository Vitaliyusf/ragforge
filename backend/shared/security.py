"""Security headers middleware and HMAC request signing.

Provides:
1. SecurityHeadersMiddleware — adds OWASP-recommended headers to all responses
2. RequestSigner — HMAC-SHA256 signing for inter-service Kafka messages

Usage:
    from shared.security import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
"""
import hmac
import hashlib
import json
import logging
import os
from typing import Dict, Any, Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds OWASP-recommended security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security (HSTS)
    - Referrer-Policy
    - Content-Security-Policy
    - Permissions-Policy
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )

        return response


class RequestSigner:
    """
    HMAC-SHA256 signing for inter-service Kafka messages.

    Prevents message tampering if the Kafka broker is compromised.
    Uses a shared secret (from environment variable) to sign and verify.

    Usage:
        signer = RequestSigner()  # reads KAFKA_SIGNING_SECRET from env

        # Producer side:
        signature = signer.sign(message_payload)
        message_payload["_signature"] = signature

        # Consumer side:
        if not signer.verify(message_payload):
            raise SecurityError("Message signature invalid")
    """

    def __init__(self, secret: Optional[str] = None) -> None:
        resolved = secret if secret is not None else os.environ.get("KAFKA_SIGNING_SECRET", "")
        self._secret = resolved.encode("utf-8")
        self._enabled = bool(self._secret)

        if not self._enabled:
            logger.info("Request signing disabled (no KAFKA_SIGNING_SECRET set)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def sign(self, payload: Dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for a message payload.

        Args:
            payload: The Kafka message dict (excluding _signature field)

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        if not self._enabled:
            return ""

        # Create deterministic representation (sort keys, exclude _signature)
        signable = {k: v for k, v in payload.items() if k != "_signature"}
        message = json.dumps(signable, sort_keys=True, default=str).encode("utf-8")

        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def verify(self, payload: Dict[str, Any]) -> bool:
        """
        Verify the HMAC-SHA256 signature on a message.

        Args:
            payload: The Kafka message dict (including _signature field)

        Returns:
            True if signature is valid, False otherwise
        """
        if not self._enabled:
            return True  # Signing disabled — allow all

        signature = payload.get("_signature")
        if not signature:
            logger.warning("Message missing signature")
            return False

        expected = self.sign(payload)
        return hmac.compare_digest(signature, expected)
