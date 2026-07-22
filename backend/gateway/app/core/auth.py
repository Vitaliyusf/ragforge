"""FastAPI authentication, CSRF and role dependencies."""
from __future__ import annotations

from typing import Tuple

from fastapi import Depends, HTTPException, Request, status

from app.core.config import GatewayConfig
from app.core.deps import get_auth_service, get_config
from app.services.auth_service import AuthService, AuthenticationFailed
from shared.auth import AuthIdentity
from shared.context import update_context


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def validate_browser_origin(request: Request, config: GatewayConfig) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in config.cors_origins_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin is not allowed")


def _authenticate(
    request: Request,
    service: AuthService,
    config: GatewayConfig,
) -> Tuple[AuthIdentity, dict]:
    validate_browser_origin(request, config)
    token = request.cookies.get(config.session_cookie_name, "")
    try:
        return service.authenticate_session(
            token,
            csrf_cookie=request.cookies.get(config.csrf_cookie_name),
            csrf_header=request.headers.get("x-csrf-token"),
            require_csrf=request.method.upper() not in SAFE_METHODS,
        )
    except AuthenticationFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Session"},
        ) from exc


async def get_current_user(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    config: GatewayConfig = Depends(get_config),
) -> AuthIdentity:
    identity, public_user = _authenticate(request, service, config)
    request.state.identity = identity
    request.state.user = public_user
    update_context(**identity.to_dict())
    return identity


async def require_admin(identity: AuthIdentity = Depends(get_current_user)) -> AuthIdentity:
    if not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return identity
