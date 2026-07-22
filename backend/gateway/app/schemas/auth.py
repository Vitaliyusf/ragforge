"""Public authentication and tenant-user schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class _EmailModel(BaseModel):
    @field_validator("email", check_fields=False)
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        local, separator, domain = normalized.partition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or len(normalized) > 254
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError("invalid email address")
        return normalized


class LoginRequest(_EmailModel):
    tenant: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class SetupRequest(_EmailModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=15, max_length=1024)


class UserCreateRequest(_EmailModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=15, max_length=1024)


class UserStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


class UserPasswordRequest(BaseModel):
    password: str = Field(min_length=15, max_length=1024)


class UserResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: Literal["admin", "user"]
    status: Literal["active", "disabled"]
    admin_id: Optional[str] = None


class AuthResponse(BaseModel):
    user: UserResponse


class SocketTicketResponse(BaseModel):
    ticket: str
    expires_in: int
