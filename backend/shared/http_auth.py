"""FastAPI dependencies for service-local, non-browser HTTP endpoints."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, status

from .auth import AuthError, AuthIdentity, verify_auth_ticket
from .context import update_context


async def require_internal_identity(request: Request) -> AuthIdentity:
    raw = request.headers.get("x-internal-auth", "")
    authorization = request.headers.get("authorization", "")
    if not raw and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    try:
        identity = verify_auth_ticket(
            raw,
            secret=os.getenv("INTERNAL_AUTH_SECRET", ""),
            audience="internal",
            purpose="request",
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid internal authentication is required",
        ) from exc
    update_context(**identity.to_dict())
    return identity


async def require_internal_admin(
    identity: AuthIdentity = Depends(require_internal_identity),
) -> AuthIdentity:
    if not (identity.is_admin or identity.is_service):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return identity
