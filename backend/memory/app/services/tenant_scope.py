"""Mandatory per-user Mongo scoping for the memory service."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from shared.auth import AuthIdentity, identity_from_context


def current_identity() -> Optional[AuthIdentity]:
    required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
    return identity_from_context(required=required)


def ownership_fields() -> Dict[str, str]:
    identity = current_identity()
    if identity is None:
        return {}
    return {
        "tenant_id": identity.tenant_id,
        "owner_user_id": identity.user_id,
        "owner_admin_id": identity.admin_id or identity.user_id,
    }


def scope_filter(query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    identity = current_identity()
    source = dict(query or {})
    if identity is None:
        return source
    boundary = {"tenant_id": identity.tenant_id, "owner_user_id": identity.user_id}
    return boundary if not source else {"$and": [boundary, source]}
