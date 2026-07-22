"""Base repository: MongoDB transaction support and shared helpers.

All domain repository mixins inherit from ``BaseRepository``. It owns
the transaction context manager, the collection requirement guard, and
the two static Mongo update helpers used across all mixins.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from pymongo.collection import Collection

from app.core.errors import DatabaseException
from shared.auth import AuthIdentity, ROLE_ADMIN, ROLE_SERVICE, ROLE_USER, identity_from_context


# ---------------------------------------------------------------------------
# Module-level serializer (used by all mixins)
# ---------------------------------------------------------------------------

def serialize(value: Any) -> Any:
    """Recursively convert datetime objects to ISO-format strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseRepository:
    """Shared infrastructure for all file-domain repository mixins.

    Responsibilities:
    - Holds the primary ``collection`` and the Mongo ``client`` reference.
    - Provides the ``transaction()`` context manager with standalone fallback.
    - Exposes ``_mongo_kwargs``, ``_update_document``, and
      ``_require_collection`` helpers used by every mixin.
    """

    def __init__(
        self,
        collection: Collection,
        *,
        client=None,
        logger=None,
    ) -> None:
        self.collection = collection
        self.client = client or collection.database.client
        self.logger = logger
        self._transactions_supported: Optional[bool] = None
        self._transaction_warning_logged: bool = False

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mongo_kwargs(session=None) -> Dict[str, Any]:
        """Return ``{"session": session}`` when a session is active."""
        return {"session": session} if session is not None else {}

    @staticmethod
    def _update_document(
        base: Optional[Dict[str, Any]] = None,
        updates: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Merge ``updates`` into the ``$set`` of ``base``."""
        update_doc = dict(base or {})
        if updates:
            update_doc.setdefault("$set", {}).update(updates)
        return update_doc

    def _require_collection(
        self, collection: Optional[Collection], name: str
    ) -> Collection:
        """Return ``collection`` or raise if it was not configured."""
        if collection is None:
            raise DatabaseException(f"{name} collection is not configured")
        return collection

    def _identity(self) -> AuthIdentity:
        required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
        identity = identity_from_context(required=required)
        if identity is not None:
            return identity
        return AuthIdentity(
            tenant_id="legacy",
            user_id="legacy-user",
            role=ROLE_SERVICE,
            admin_id="legacy-user",
        )

    def _scope_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Stamp immutable tenant ownership on every domain document."""
        identity = self._identity()
        scoped = dict(document)
        supplied_tenant = scoped.get("tenant_id")
        if supplied_tenant not in (None, identity.tenant_id):
            raise DatabaseException("Cross-tenant document write denied")
        scoped["tenant_id"] = identity.tenant_id
        if identity.role == ROLE_USER:
            scoped["owner_user_id"] = identity.user_id
            scoped["owner_admin_id"] = identity.admin_id or identity.user_id
        elif identity.role == ROLE_ADMIN:
            if scoped.get("owner_admin_id") not in (None, identity.user_id):
                raise DatabaseException("Document is outside the administrator scope")
            scoped["owner_admin_id"] = identity.user_id
            scoped.setdefault("owner_user_id", identity.user_id)
        else:
            if not scoped.get("owner_user_id") or not scoped.get("owner_admin_id"):
                raise DatabaseException("Service document writes require explicit ownership")
        return scoped

    def _scope_filter(
        self,
        query: Optional[Dict[str, Any]] = None,
        *,
        owner_scope: bool = True,
    ) -> Dict[str, Any]:
        """Add mandatory tenant and ownership predicates to a Mongo query."""
        identity = self._identity()
        boundary: Dict[str, Any] = {"tenant_id": identity.tenant_id}
        if owner_scope and identity.role == ROLE_USER:
            boundary["owner_user_id"] = identity.user_id
        elif owner_scope and identity.role == ROLE_ADMIN:
            boundary["owner_admin_id"] = identity.user_id
        source = dict(query or {})
        if not source:
            return boundary
        return {"$and": [boundary, source]}

    # ------------------------------------------------------------------
    # Transaction support
    # ------------------------------------------------------------------

    def _probe_transaction_support(self) -> bool:
        """Return True when the connected Mongo topology supports transactions."""
        admin_db = getattr(self.client, "admin", None)
        if admin_db is None:
            return True
        topology_doc: Optional[Dict[str, Any]] = None
        for command_name in ("hello", "isMaster"):
            try:
                topology_doc = admin_db.command(command_name)
                break
            except Exception:
                continue
        if not isinstance(topology_doc, dict):
            return True
        return bool(
            topology_doc.get("setName") or topology_doc.get("msg") == "isdbgrid"
        )

    @staticmethod
    def _is_transaction_unsupported_error(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        return (
            code == 20
            or "transaction numbers are only allowed on a replica set member or mongos"
            in str(exc).lower()
        )

    def _log_transaction_fallback(self, reason: str) -> None:
        if self._transaction_warning_logged:
            return
        self._transaction_warning_logged = True
        message = "MongoDB transactions unsupported; falling back to non-transactional writes"
        data = {"reason": reason}
        if self.logger is not None and hasattr(self.logger, "log"):
            self.logger.log("db:transaction", message, data, hypothesis_id="W")
            return
        if self.logger is not None and hasattr(self.logger, "warning"):
            self.logger.warning(message, extra=data)
            return
        logging.getLogger(__name__).warning("%s %s", message, data)

    @contextmanager
    def transaction(self):
        """Yield a Mongo session inside a transaction, or ``None`` on standalone."""
        if self.client is None or self._transactions_supported is False:
            yield None
            return

        if self._transactions_supported is None:
            self._transactions_supported = self._probe_transaction_support()
            if not self._transactions_supported:
                self._log_transaction_fallback("standalone_mongo_topology")
                yield None
                return

        try:
            with self.client.start_session() as session:
                try:
                    with session.start_transaction():
                        self._transactions_supported = True
                        yield session
                except Exception as exc:
                    if self._is_transaction_unsupported_error(exc):
                        self._transactions_supported = False
                        self._log_transaction_fallback(str(exc))
                        yield None
                        return
                    raise
        except Exception as exc:
            if self._is_transaction_unsupported_error(exc):
                self._transactions_supported = False
                self._log_transaction_fallback(str(exc))
                yield None
                return
            raise DatabaseException(
                f"Failed to open MongoDB transaction: {exc}"
            ) from exc
