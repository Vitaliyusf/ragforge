# Multi-tenancy, RBAC and security runbook

This document describes the security model implemented in the code, the permission map, the migration path from a single-user system, and the gates that must pass before production. It is not a certification statement; formal compliance also requires penetration testing, infrastructure review, and operational evidence.

## 1. Identity and ownership model

Every authenticated identity carries the following fields:

| Field | Meaning |
| --- | --- |
| `tenant_id` | The organization/workspace boundary. Every query and every write must include it. |
| `user_id` | A random user identifier that cannot be chosen by the client. |
| `role` | One of `admin`, `user`, or `service`. |
| `admin_id` | The administrator who manages the user. For an admin, the value equals `user_id`. |
| `session_id` | A server-side session identifier; it is not a credential. |

Every domain document and every vector payload stores:

```text
tenant_id
owner_user_id
owner_admin_id
```

The authorization rules are invariants, not conventions:

1. A `user` reads and writes only records with their own `tenant_id` and `owner_user_id`.
2. An `admin` sees files only when their `tenant_id` matches and `owner_admin_id` equals their `user_id`.
3. A `service` may operate inside a given tenant only after verifying a signed internal ticket. When writing vectors it must receive explicit ownership.
4. Identity fields sent in an HTTP body, over Socket.IO, or inside a business payload are not a source of authority and are overridden or rejected.
5. When identity is absent and `INTERNAL_AUTH_REQUIRED=true`, the operation fails; there is no fallback to a global query.

## 2. Permission matrix

| Operation | user | admin |
| --- | ---: | ---: |
| Login/logout/socket ticket | yes | yes |
| Chat and personal chat history | yes | yes |
| Personal memory | yes | yes |
| File upload | yes | yes |
| File listing and file metadata | no | yes, for all users they manage |
| File summary/review case/audit/delete/rerun | no | yes, within their management boundary |
| Guardrail approval for a file | no | yes |
| Logs, traces, system prompt and raw model debug | no | yes, and only for their own tenant |
| User management | no | yes, and only users with their `admin_id` |
| Model/config management and detailed health | no | yes |

Hiding features in the frontend is UX only. The same permission is enforced again at the Gateway, in the target service, and in the repository/vector filter layer.

## 3. Authentication and sessions

- The session token is an opaque random token. Only an HMAC digest keyed with `SESSION_PEPPER` is stored in the database.
- Passwords are stored with PBKDF2-HMAC-SHA256, a random salt, 600,000 iterations, and a `PASSWORD_PEPPER` kept outside the database.
- A new password requires at least 15 characters; there is no artificial complexity requirement.
- After five failed attempts the account is locked for 15 minutes.
- The session cookie is `HttpOnly`, `SameSite=Strict`, and in production also `Secure` with the `__Host-` prefix.
- State-changing operations require a CSRF token matching the cookie, and its digest must additionally match the server-side session.
- An origin that is not allowlisted is rejected before authentication.
- A password reset or user disable revokes all of that user's sessions.
- Logout revokes the session in the database and deletes both cookies.
- The frontend does not keep credentials, logs, or files in localStorage/Redux persistence and clears state on session change.

## 4. Service-to-service trust

The Gateway signs a short-lived ticket with HMAC-SHA256. The ticket includes audience, purpose, issuer, `iat`, `exp`, `jti`, all identity fields, and a canonical SHA-256 digest of the entire message envelope. Every consumer verifies both the signature and the digest match before binding to the local context; changing the action, routing metadata, or payload after signing fails closed. Replies and stream events pass the same verification.

```text
Browser session
    -> Gateway authentication + CSRF + RBAC
        -> short-lived signed internal ticket
            -> RabbitMQ/Kafka/HTTP consumer verifies ticket
                -> repository/vector query injects tenant ownership filter
```

Socket.IO does not accept user/tenant from the handshake. The browser requests a short-lived socket ticket with audience `rag` from the Gateway, and the RAG service verifies it before opening the connection.

For a regular user, the RAG service does not emit `trace` events and strips `trace_summary`, `safe_debug_payloads`, and raw debug from `done`. Preventing leakage therefore does not depend on hiding a button in the UI.

## 5. Guardrail and file approval

1. A user uploads a file through the authenticated Gateway.
2. The Gateway validates the name, extension allowlist, MIME allowlist, size, magic bytes, and UTF-8 by file type.
3. The Files service normalizes the name again, prevents path traversal, validates base64 and size, and stores under `uploads/<tenant_id>/<file_id>`.
4. The extraction graph and the guardrail analyze PII, prompt injection, dangerous content, and parser issues.
5. When review is required, the file moves to `awaiting_review`, a review case is stored, and the graph pauses.
6. Only the appropriate admin can read the review case and submit a decision.
7. `reviewer` and `reviewer_role` are derived from the server-side session. An attempt to submit `reviewer` from the client receives 422.
8. `review_case_id`, a hash of the text, and the patch map are validated before resume. The resume token is time-limited and single-use; an atomic claim and a unique decision index prevent two concurrent decisions even on standalone Mongo.
9. Every state transition and decision is recorded in a tenant-scoped audit trail.

## 6. Where the separation is implemented

| Area | Key change |
| --- | --- |
| `backend/shared` | Shared identity, password hashing, signed tickets, ContextVars, HTTP/RabbitMQ verification and context propagation to threads. |
| `backend/gateway` | Tenants/users/sessions, login/CSRF/RBAC, admin users, route guards, upload validation, log filtering, RPC signing. |
| `backend/files` | Scope on every collection, tenant-based paths, upload validation, admin-only review, actor from trusted context, and audit. |
| `backend/memory` | Scope on chats/messages/long-term memories and on Qdrant memory by tenant+user. |
| `backend/vector_db` | Tenant payload indexes, enforced filters, ownership on upsert, admin/service only for deletion and review mutation. |
| `backend/embedding` | Preservation of ownership fields and ticket verification/propagation at every stage. |
| `backend/rag` | Socket authentication, history/checkpoint/feedback isolation, role-based debug filtering, and signed RPC. |
| `backend/llm_agent` | Context propagation, debug sanitization, and a Bearer API key on every vLLM call. |
| `frontend` | AuthProvider, login workspace, CSRF, role navigation, admin users/files/logs, user upload-only, session state cleanup. |
| `docker-compose*.yml` | Separate DB users, required secrets, Qdrant/vLLM auth, minimized host ports, network segmentation, and TLS ingress. |

## 7. Provisioning a new tenant

On a fresh installation the first administrator of the bootstrap tenant is created interactively in the browser: the one-time setup screen claims the first account as admin and closes permanently once any user exists (`POST /v1/auth/setup`). Everything below concerns additional tenants.

There is no public endpoint for tenant creation. This is deliberately an offline operation so that no super-admin attack surface exists.

From the Gateway environment:

```powershell
$env:PROVISION_ADMIN_PASSWORD = '<strong unique password>'
docker compose exec gateway python scripts/provision_tenant.py `
  --tenant-id acme `
  --tenant-name 'Acme Ltd' `
  --admin-email admin@acme.example `
  --display-name 'Acme Administrator'
Remove-Item Env:PROVISION_ADMIN_PASSWORD
```

The command creates the tenant and its first admin atomically at the application level, relies on unique indexes against races, and returns only public data.

## 8. Production deployment

The production overlay provides HTTPS via Caddy, HSTS, CSP, protective headers, secure `__Host-` cookies, and same-origin API/socket routing. Data, messaging, AI, and malware-scanning services are separated into internal Docker networks; only the ingress is exposed.

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Every placeholder in `.env.example` must be replaced with a separately generated random value. Never reuse a secret between Mongo, RabbitMQ, Qdrant, vLLM, internal tickets, the password pepper, and the session pepper.

### Infrastructure gates that application code does not solve

- Do not promote the current frontend to production while `package-lock.json` pins `next@14.2.35`. Next.js 14 is unsupported and appears in 2026 vulnerability disclosures. Upgrade at least to the supported backport `15.5.20` (or a newer Active LTS), run `npm audit --omit=dev`, the full frontend test suite, and a production build — only then remove this gate. Blocking `Next-Action` and unexpected WebSocket upgrades in Caddy is defense-in-depth, not a substitute for the upgrade.
- Disks, snapshots, and backups encrypted with the target environment's KMS.
- A real secret manager instead of `.env` in production.
- MFA or enterprise OIDC/SAML for admin accounts before internet exposure.
- mTLS/service mesh if the threat model requires cryptographic encryption inside the host/cluster as well; Docker internal networks provide isolation, not mTLS.
- Rate limiting/WAF at the ingress layer and per-tenant LLM quotas.
- SIEM/alerts for lockouts, authorization failures, malware, guardrail approvals, and config changes.
- Retention and deletion according to privacy policy and regulation.
- SCA, image scanning, SBOM, patch cadence, and image signature verification.
- An external penetration test and a restore/DR drill before go-live.

## 9. Verification commands

```powershell
# Python syntax/import compilation
.\.venv\Scripts\python.exe -m compileall -q backend scripts

# Backend unit/integration suites (after installing requirements)
.\.venv\Scripts\python.exe -m pytest backend -q

# Frontend unit/component authorization tests
Set-Location frontend
npm.cmd test -- --run

# Frontend production compilation
npm.cmd run build

# Production dependency audit (requires registry/network access)
npm.cmd audit --omit=dev --audit-level=high

# Compose schemas and interpolation
Set-Location ..
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

The security test suite covers password hashing, ticket tampering/audience/expiry, missing-identity fail-closed behavior, file repository scoping, vector scoping, admin review RBAC, CSRF/origin, socket debug filtering, UI debug hiding, and vLLM bearer authentication.

## 10. Standards baseline

The controls were built against:

- [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP LLMSVS 2.0](https://owasp.org/www-project-llm-verification-standard/LLMSVS-v2.0-en.html), especially memory/RAG separation between users, vector store verification, server-side prompts, and guardrails.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

The implementation target is ASVS Level 2 at the application level. Do not claim "ASVS compliant" or "fully secure" without completing the infrastructure gates, full per-requirement traceability, and an independent assessment.
