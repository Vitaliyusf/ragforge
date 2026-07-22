"""Session authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.auth import get_current_user, validate_browser_origin
from app.core.config import GatewayConfig
from app.core.deps import get_auth_service, get_config
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    SetupRequest,
    SetupStatusResponse,
    SocketTicketResponse,
)
from app.services.auth_service import (
    AccountLocked,
    AuthenticationFailed,
    AuthService,
    UserConflict,
)
from shared.auth import AuthIdentity


router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_options(config: GatewayConfig) -> dict:
    options = {
        "secure": config.session_cookie_secure,
        "samesite": config.session_cookie_samesite,
        "path": "/",
    }
    if config.session_cookie_domain:
        options["domain"] = config.session_cookie_domain
    return options


@router.get("/setup", response_model=SetupStatusResponse)
def setup_status(service: AuthService = Depends(get_auth_service)):
    """Report whether the interactive first-run setup is still open.

    Exposes a single boolean and nothing else, so it is safe to serve
    unauthenticated: once any user exists it permanently reports false.
    """
    return {"needs_setup": service.needs_setup()}


@router.post("/setup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def claim_initial_admin(
    body: SetupRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    config: GatewayConfig = Depends(get_config),
):
    """Create the first administrator account, then sign them in.

    Only available while no users exist; afterwards it always returns 409.
    """
    validate_browser_origin(request, config)
    try:
        service.claim_initial_admin(
            email=str(body.email),
            display_name=body.display_name,
            password=body.password,
        )
        session_token, csrf_token, _identity, public_user = service.login(
            tenant=config.bootstrap_tenant_id,
            email=str(body.email),
            password=body.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AccountLocked, AuthenticationFailed) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant, email or password",
        ) from exc
    options = _cookie_options(config)
    response.set_cookie(
        config.session_cookie_name,
        session_token,
        httponly=True,
        max_age=config.session_ttl_seconds,
        **options,
    )
    response.set_cookie(
        config.csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=config.session_ttl_seconds,
        **options,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": public_user}


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    config: GatewayConfig = Depends(get_config),
):
    validate_browser_origin(request, config)
    try:
        session_token, csrf_token, _identity, public_user = service.login(
            tenant=body.tenant,
            email=str(body.email),
            password=body.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AccountLocked as exc:
        # Keep locked, unknown and invalid accounts indistinguishable to callers.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant, email or password",
        ) from exc
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    options = _cookie_options(config)
    response.set_cookie(
        config.session_cookie_name,
        session_token,
        httponly=True,
        max_age=config.session_ttl_seconds,
        **options,
    )
    response.set_cookie(
        config.csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=config.session_ttl_seconds,
        **options,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": public_user}


@router.get("/me", response_model=AuthResponse)
def me(request: Request, _identity: AuthIdentity = Depends(get_current_user)):
    return {"user": request.state.user}


@router.post("/me", response_model=AuthResponse)
def me_legacy(request: Request, _identity: AuthIdentity = Depends(get_current_user)):
    return {"user": request.state.user}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    identity: AuthIdentity = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    config: GatewayConfig = Depends(get_config),
):
    service.logout(request.cookies.get(config.session_cookie_name, ""), identity)
    options = _cookie_options(config)
    response.delete_cookie(config.session_cookie_name, httponly=True, **options)
    response.delete_cookie(config.csrf_cookie_name, httponly=False, **options)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/socket-ticket", response_model=SocketTicketResponse)
def socket_ticket(
    identity: AuthIdentity = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    config: GatewayConfig = Depends(get_config),
):
    ttl = min(120, config.internal_auth_ticket_ttl_seconds * 2)
    return {"ticket": service.socket_ticket(identity), "expires_in": ttl}
