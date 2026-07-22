"""Gateway-owned tenants, users, opaque sessions and security audit events."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from pymongo import ASCENDING, IndexModel
from pymongo.database import Database

from app.core.config import GatewayConfig
from shared.auth import (
    AuthError,
    AuthIdentity,
    ROLE_ADMIN,
    ROLE_USER,
    hash_password,
    new_opaque_token,
    sign_auth_ticket,
    token_digest,
    verify_password,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize PyMongo/legacy datetimes before Python-side comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AuthenticationFailed(Exception):
    pass


class AccountLocked(Exception):
    pass


class UserConflict(Exception):
    pass


class AuthService:
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    def __init__(self, database: Database, config: GatewayConfig) -> None:
        self.db = database
        self.config = config
        self.users = database["auth_users"]
        self.tenants = database["auth_tenants"]
        self.sessions = database["auth_sessions"]
        self.audit_events = database["security_audit_events"]
        self._dummy_hash = hash_password("not-a-real-password-123", pepper=config.password_pepper)

    def ensure_indexes(self) -> None:
        self.tenants.create_indexes([
            IndexModel([("tenant_id", ASCENDING)], unique=True, name="uniq_tenant_id"),
            IndexModel([("slug", ASCENDING)], unique=True, name="uniq_tenant_slug"),
        ])
        self.users.create_indexes([
            IndexModel([("user_id", ASCENDING)], unique=True, name="uniq_user_id"),
            IndexModel([("tenant_id", ASCENDING), ("email", ASCENDING)], unique=True, name="uniq_tenant_email"),
            IndexModel([("tenant_id", ASCENDING), ("admin_id", ASCENDING), ("status", ASCENDING)], name="admin_users"),
        ])
        self.sessions.create_indexes([
            IndexModel([("token_digest", ASCENDING)], unique=True, name="uniq_session_token"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="session_ttl"),
            IndexModel([("tenant_id", ASCENDING), ("user_id", ASCENDING)], name="user_sessions"),
        ])
        self.audit_events.create_index(
            [("tenant_id", ASCENDING), ("created_at", ASCENDING)],
            name="tenant_security_audit",
        )

    def bootstrap_admin(self) -> None:
        """Create the first administrator from environment credentials, if provided.

        When BOOTSTRAP_ADMIN_EMAIL/BOOTSTRAP_ADMIN_PASSWORD are unset the
        database is left empty and the interactive first-run setup endpoint
        (`POST /v1/auth/setup`) remains open until the first admin is claimed.
        """
        if self.users.count_documents({}) > 0:
            return
        if not self.config.bootstrap_admin_email or not self.config.bootstrap_admin_password:
            return
        self._create_initial_admin(
            email=self.config.bootstrap_admin_email,
            password=self.config.bootstrap_admin_password,
            display_name="Administrator",
            audit_action="bootstrap_admin_created",
        )

    def needs_setup(self) -> bool:
        """True while authentication is enforced but no user has been created yet."""
        return self.config.auth_required and self.users.count_documents({}) == 0

    def claim_initial_admin(self, *, email: str, display_name: str, password: str) -> Dict[str, Any]:
        """Create the first administrator from the interactive first-run setup.

        Only valid while no users exist.  The unique tenant index is the
        concurrency boundary: two concurrent claims race to insert the fixed
        bootstrap tenant and the loser receives a conflict.
        """
        if self.users.count_documents({}) > 0:
            raise UserConflict("Setup has already been completed")
        return self._create_initial_admin(
            email=email,
            password=password,
            display_name=display_name,
            audit_action="initial_admin_claimed",
        )

    def _create_initial_admin(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        audit_action: str,
    ) -> Dict[str, Any]:
        tenant_id = self.config.bootstrap_tenant_id.strip()
        slug = self._slugify(tenant_id)
        now = _utcnow()
        try:
            self.tenants.insert_one({
                "tenant_id": tenant_id,
                "slug": slug,
                "name": self.config.bootstrap_tenant_name.strip(),
                "status": "active",
                "created_at": now,
            })
        except Exception:
            # The tenant may survive a crash between tenant and user creation;
            # reuse it only while the user collection is still empty.
            if self.users.count_documents({}) > 0:
                raise UserConflict("Setup has already been completed")
            if not self.tenants.find_one({"tenant_id": tenant_id, "status": "active"}):
                raise
        user_id = str(uuid.uuid4())
        user_document = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "admin_id": user_id,
            "email": self._normalize_email(email),
            "display_name": display_name.strip() or "Administrator",
            "role": ROLE_ADMIN,
            "status": "active",
            "password_hash": hash_password(password, pepper=self.config.password_pepper),
            "failed_login_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.users.insert_one(user_document)
        self._audit(tenant_id, user_id, audit_action, target_user_id=user_id)
        return self.public_user(user_document)

    def provision_tenant_admin(
        self,
        *,
        tenant_id: str,
        tenant_name: str,
        admin_email: str,
        admin_password: str,
        display_name: str = "Administrator",
    ) -> Dict[str, Any]:
        """Provision an isolated tenant and its first administrator.

        This method is intentionally exposed only to the offline provisioning
        command, never as a browser endpoint.  The unique tenant index is the
        concurrency boundary for two operators attempting the same creation.
        """
        normalized_tenant_id = tenant_id.strip()
        if not normalized_tenant_id or len(normalized_tenant_id) > 100:
            raise AuthError("tenant identifier is invalid")
        slug = self._slugify(normalized_tenant_id)
        email = self._normalize_email(admin_email)
        if self.tenants.find_one({"$or": [{"tenant_id": normalized_tenant_id}, {"slug": slug}]}):
            raise UserConflict("Tenant already exists")

        now = _utcnow()
        tenant_document = {
            "tenant_id": normalized_tenant_id,
            "slug": slug,
            "name": tenant_name.strip() or normalized_tenant_id,
            "status": "active",
            "created_at": now,
        }
        self.tenants.insert_one(tenant_document)
        try:
            user_id = str(uuid.uuid4())
            user_document = {
                "user_id": user_id,
                "tenant_id": normalized_tenant_id,
                "admin_id": user_id,
                "email": email,
                "display_name": display_name.strip() or "Administrator",
                "role": ROLE_ADMIN,
                "status": "active",
                "password_hash": hash_password(admin_password, pepper=self.config.password_pepper),
                "failed_login_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            self.users.insert_one(user_document)
        except Exception:
            self.tenants.delete_one({"tenant_id": normalized_tenant_id})
            raise

        self._audit(normalized_tenant_id, user_id, "tenant_admin_provisioned", target_user_id=user_id)
        return {"tenant": {key: tenant_document[key] for key in ("tenant_id", "slug", "name", "status")}, "admin": self.public_user(user_document)}

    def login(
        self,
        *,
        tenant: str,
        email: str,
        password: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
    ) -> Tuple[str, str, AuthIdentity, Dict[str, Any]]:
        tenant_value = tenant.strip()
        tenant_candidates: List[Dict[str, str]] = [{"tenant_id": tenant_value}]
        try:
            tenant_candidates.append({"slug": self._slugify(tenant_value)})
        except AuthError:
            # Invalid public workspace input is deliberately indistinguishable
            # from unknown credentials and must not become a server error.
            pass
        tenant_doc = self.tenants.find_one({
            "$or": tenant_candidates,
            "status": "active",
        })
        user = None
        if tenant_doc:
            user = self.users.find_one({
                "tenant_id": tenant_doc["tenant_id"],
                "email": self._normalize_email(email),
            })

        candidate_hash = user.get("password_hash") if user else self._dummy_hash
        password_valid = verify_password(password, candidate_hash, pepper=self.config.password_pepper)
        now = _utcnow()

        if user and user.get("lock_until") and _as_utc(user["lock_until"]) > now:
            self._audit(user["tenant_id"], user["user_id"], "login_locked", ip_address=ip_address)
            raise AccountLocked("Account is temporarily locked")
        if not user or not password_valid or user.get("status") != "active":
            if user:
                failed_count = int(user.get("failed_login_count", 0)) + 1
                update: Dict[str, Any] = {"failed_login_count": failed_count, "updated_at": now}
                if failed_count >= self.MAX_FAILED_LOGINS:
                    update["lock_until"] = now + timedelta(minutes=self.LOCKOUT_MINUTES)
                    update["failed_login_count"] = 0
                self.users.update_one({"_id": user["_id"]}, {"$set": update})
                self._audit(user["tenant_id"], user["user_id"], "login_failed", ip_address=ip_address)
            raise AuthenticationFailed("Invalid tenant, email or password")

        self.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"failed_login_count": 0, "lock_until": None, "last_login_at": now, "updated_at": now}},
        )
        session_token = new_opaque_token()
        csrf_token = new_opaque_token()
        session_id = str(uuid.uuid4())
        expires_at = now + timedelta(seconds=self.config.session_ttl_seconds)
        self.sessions.insert_one({
            "session_id": session_id,
            "token_digest": token_digest(session_token, pepper=self.config.session_pepper),
            "csrf_digest": token_digest(csrf_token, pepper=self.config.session_pepper),
            "tenant_id": user["tenant_id"],
            "user_id": user["user_id"],
            "created_at": now,
            "last_seen_at": now,
            "expires_at": expires_at,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:512],
        })
        identity = self._identity(user, session_id=session_id)
        self._audit(user["tenant_id"], user["user_id"], "login_succeeded", ip_address=ip_address)
        return session_token, csrf_token, identity, self.public_user(user)

    def authenticate_session(
        self,
        session_token: str,
        *,
        csrf_cookie: Optional[str] = None,
        csrf_header: Optional[str] = None,
        require_csrf: bool = False,
    ) -> Tuple[AuthIdentity, Dict[str, Any]]:
        if not self.config.auth_required:
            identity = AuthIdentity(
                tenant_id=self.config.bootstrap_tenant_id,
                user_id="local-development-admin",
                role=ROLE_ADMIN,
                email="local-admin@localhost",
                admin_id="local-development-admin",
                session_id="local-development-session",
            )
            return identity, {
                "tenant_id": identity.tenant_id,
                "user_id": identity.user_id,
                "role": identity.role,
                "email": identity.email,
                "display_name": "Local Administrator",
                "status": "active",
            }
        if not session_token:
            raise AuthenticationFailed("Authentication required")
        now = _utcnow()
        session = self.sessions.find_one({
            "token_digest": token_digest(session_token, pepper=self.config.session_pepper),
            "expires_at": {"$gt": now},
            "revoked_at": {"$exists": False},
        })
        if not session:
            raise AuthenticationFailed("Authentication required")
        if require_csrf:
            if not csrf_cookie or not csrf_header or not csrf_cookie == csrf_header:
                raise AuthenticationFailed("CSRF validation failed")
            expected = session.get("csrf_digest", "")
            supplied = token_digest(csrf_header, pepper=self.config.session_pepper)
            if not expected or not secrets_compare(expected, supplied):
                raise AuthenticationFailed("CSRF validation failed")

        user = self.users.find_one({
            "tenant_id": session["tenant_id"],
            "user_id": session["user_id"],
            "status": "active",
        })
        if not user:
            raise AuthenticationFailed("Authentication required")
        last_seen_at = _as_utc(session.get("last_seen_at", now))
        if (now - last_seen_at).total_seconds() >= 300:
            self.sessions.update_one({"_id": session["_id"]}, {"$set": {"last_seen_at": now}})
        return self._identity(user, session_id=session["session_id"]), self.public_user(user)

    def logout(self, session_token: str, actor: AuthIdentity) -> None:
        self.sessions.update_one(
            {"token_digest": token_digest(session_token, pepper=self.config.session_pepper)},
            {"$set": {"revoked_at": _utcnow()}},
        )
        self._audit(actor.tenant_id, actor.user_id, "logout")

    def create_user(self, actor: AuthIdentity, *, email: str, display_name: str, password: str) -> Dict[str, Any]:
        self._require_admin(actor)
        now = _utcnow()
        document: Dict[str, Any] = {
            "user_id": str(uuid.uuid4()),
            "tenant_id": actor.tenant_id,
            "admin_id": actor.user_id,
            "email": self._normalize_email(email),
            "display_name": display_name.strip(),
            "role": ROLE_USER,
            "status": "active",
            "password_hash": hash_password(password, pepper=self.config.password_pepper),
            "failed_login_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        if self.users.find_one({"tenant_id": actor.tenant_id, "email": document["email"]}):
            raise UserConflict("A user with this email already exists in the workspace")
        self.users.insert_one(document)
        self._audit(actor.tenant_id, actor.user_id, "user_created", target_user_id=document["user_id"])
        return self.public_user(document)

    def list_users(self, actor: AuthIdentity) -> List[Dict[str, Any]]:
        self._require_admin(actor)
        query = {
            "tenant_id": actor.tenant_id,
            "$or": [{"admin_id": actor.user_id}, {"user_id": actor.user_id}],
        }
        return [self.public_user(user) for user in self.users.find(query).sort("created_at", ASCENDING)]

    def set_user_status(self, actor: AuthIdentity, user_id: str, status: str) -> Dict[str, Any]:
        user = self._managed_user(actor, user_id)
        if user["user_id"] == actor.user_id:
            raise AuthError("An administrator cannot disable their own account")
        self.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"status": status, "updated_at": _utcnow()}},
        )
        if status == "disabled":
            self._revoke_user_sessions(actor.tenant_id, user_id)
        user["status"] = status
        self._audit(actor.tenant_id, actor.user_id, f"user_{status}", target_user_id=user_id)
        return self.public_user(user)

    def set_user_password(self, actor: AuthIdentity, user_id: str, password: str) -> None:
        user = self._managed_user(actor, user_id)
        self.users.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "password_hash": hash_password(password, pepper=self.config.password_pepper),
                "updated_at": _utcnow(),
                "failed_login_count": 0,
                "lock_until": None,
            }},
        )
        self._revoke_user_sessions(actor.tenant_id, user_id)
        self._audit(actor.tenant_id, actor.user_id, "user_password_reset", target_user_id=user_id)

    def socket_ticket(self, identity: AuthIdentity) -> str:
        return sign_auth_ticket(
            identity,
            secret=self.config.internal_auth_secret,
            audience="rag",
            purpose="socket",
            ttl_seconds=min(120, self.config.internal_auth_ticket_ttl_seconds * 2),
        )

    @staticmethod
    def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "admin_id": user.get("admin_id"),
            "email": user["email"],
            "display_name": user.get("display_name") or user["email"],
            "role": user["role"],
            "status": user["status"],
        }

    def _managed_user(self, actor: AuthIdentity, user_id: str) -> Dict[str, Any]:
        self._require_admin(actor)
        user = self.users.find_one({
            "tenant_id": actor.tenant_id,
            "user_id": user_id,
            "$or": [{"admin_id": actor.user_id}, {"user_id": actor.user_id}],
        })
        if not user:
            raise AuthenticationFailed("User not found")
        return cast(Dict[str, Any], user)

    def _revoke_user_sessions(self, tenant_id: str, user_id: str) -> None:
        self.sessions.update_many(
            {"tenant_id": tenant_id, "user_id": user_id, "revoked_at": {"$exists": False}},
            {"$set": {"revoked_at": _utcnow()}},
        )

    @staticmethod
    def _identity(user: Dict[str, Any], *, session_id: str) -> AuthIdentity:
        return AuthIdentity(
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
            role=user["role"],
            email=user.get("email"),
            admin_id=user.get("admin_id"),
            session_id=session_id,
        )

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().casefold()

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
        if not slug:
            raise AuthError("tenant identifier is invalid")
        return slug[:100]

    @staticmethod
    def _require_admin(actor: AuthIdentity) -> None:
        if not actor.is_admin:
            raise AuthError("Administrator role required")

    def _audit(
        self,
        tenant_id: str,
        actor_user_id: str,
        action: str,
        *,
        target_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        self.audit_events.insert_one({
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "target_user_id": target_user_id,
            "action": action,
            "ip_address": ip_address,
            "created_at": _utcnow(),
        })


def secrets_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)
