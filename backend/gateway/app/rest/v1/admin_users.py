"""Admin-only management of users assigned to that administrator."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.auth import require_admin
from app.core.deps import get_auth_service
from app.schemas.auth import UserCreateRequest, UserPasswordRequest, UserResponse, UserStatusRequest
from app.services.auth_service import AuthService, AuthenticationFailed, UserConflict
from shared.auth import AuthError, AuthIdentity


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=List[UserResponse])
def list_users(
    actor: AuthIdentity = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
):
    return service.list_users(actor)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    actor: AuthIdentity = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return service.create_user(
            actor,
            email=str(body.email),
            display_name=body.display_name,
            password=body.password,
        )
    except UserConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_status(
    user_id: str,
    body: UserStatusRequest,
    actor: AuthIdentity = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return service.set_user_status(actor, user_id, body.status)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: str,
    body: UserPasswordRequest,
    actor: AuthIdentity = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
):
    try:
        service.set_user_password(actor, user_id, body.password)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
