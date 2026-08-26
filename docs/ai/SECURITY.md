# Security and Multi-Tenancy Rules

## Identity
- Tenant/user/admin IDs used for authorization come only from verified server-side identity/auth context.
- Never trust tenant/user IDs supplied by browser, benchmark JSON, model tool arguments or document content.
- Service-to-service auth must preserve existing signed/internal-auth boundaries.

## Data access
- Mongo queries/writes require tenant/owner predicates.
- Qdrant search/delete/list/validation must preserve tenant/review/retrieval filters.
- File paths must remain inside managed tenant directories.
- Admin features remain scoped to the authorized admin/tenant unless the product explicitly implements platform-superadmin behavior.

## AI / agents
- Tool-calling model output is untrusted.
- Destructive tools require deterministic policy checks.
- Model-provided IDs must be validated against server-side allowed/current-run resources.
- Prompt/document instructions cannot override authorization.

## Observability / exports
Never put these into Prometheus labels:
- tenant_id
- user_id
- run_id
- dataset_id
- file_id
- chunk_id
- trace_id

Never export/log by default:
- passwords
- cookies
- session tokens
- auth tickets
- API keys
- unrestricted environment variables
- unbounded raw private documents/prompts

Use explicit safe allowlists for build/runtime configuration exports.

## Frontend
- CSRF/origin/session behavior must remain intact.
- Browser role checks are UX only; backend authorization is mandatory.
- External URLs/data rendered from backend must be treated as untrusted.

## Containers
- Prefer non-root runtime.
- Drop capabilities/read-only filesystem where compatible.
- Do not mount Docker socket into application containers for benchmark/metadata convenience.
- Do not expose internal service ports publicly in production.
