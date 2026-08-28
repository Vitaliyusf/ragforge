# AUTH-02 — Internal RPC expiry handling and embedding service readiness

**Branch:** `fix/internal-rpc-auth-readiness`

## Goal

Prevent internal RabbitMQ RPC requests from degrading into long caller-side timeouts when:

1. a downstream service is not yet truly ready to serve RPC traffic; or
2. a queued internal-auth ticket expires before the consumer processes it.

This task must make internal RPC authentication failures explicit and fast, while preserving short-lived signed internal tickets and existing tenant/security boundaries.

Do **not** solve this by merely increasing auth-ticket TTL or RAG timeouts.

---

## Incident / evidence

A Smoke30 benchmark produced:

```text
RabbitMQ RPC timeout waiting for 'embedding' after 75.0s
```

The embedding container itself was running and later reported:

```json
{
  "status": "ok",
  "model_loaded": true,
  "kafka": "disconnected"
}
```

RabbitMQ later showed:

```text
queue: embedding
messages_ready: 0
messages_unacknowledged: 0
consumers: 1
```

However, embedding startup logs showed repeated Hugging Face model-download read timeouts/resume attempts before application startup completed.

After the consumer began processing the already-queued RPC requests, message authentication failed repeatedly with:

```text
shared.auth.AuthError:
authentication ticket has expired
```

The current shared RabbitMQ consumer verifies the internal ticket before the normal service handler/reply path. When verification raises, no normal RPC error reply is returned to the caller. The caller therefore waits until its own RPC timeout expires and reports a misleading downstream timeout.

The current design also lets `rag` depend on `embedding` using service-start semantics rather than application-readiness semantics.

---

# Required outcomes

After this task:

```text
container running
        ≠
RPC ready
```

must be represented correctly.

A downstream auth failure must become:

```text
immediate explicit RPC error
```

rather than:

```text
silent consumer exception
→ caller waits
→ 75-second timeout
```

And RAG startup must not consider embedding ready solely because the container process exists.

---

# PART 1 — Embedding readiness semantics

## Required readiness model

Add or extend an embedding readiness endpoint so the service can distinguish:

```text
process alive
model loaded
RabbitMQ RPC consumer connected
Kafka state
ready_for_rpc
```

Preferred split:

```text
/health
```

for basic process health, and:

```text
/ready
```

for serving readiness.

If the repository strongly prefers one endpoint, extend the current health contract instead, but preserve the semantic distinction.

### Minimum `ready_for_rpc`

For RAG retrieval RPCs:

```text
model_loaded == true
AND
RabbitMQ RPC consumer connected == true
```

Kafka may be reported separately.

Do **not** require Kafka to be connected for `ready_for_rpc=true` unless the current embedding RPC path actually depends on Kafka.

Example conceptual response:

```json
{
  "status": "ready",
  "model_loaded": true,
  "rabbitmq": "connected",
  "kafka": "disconnected",
  "ready_for_rpc": true
}
```

or, while still loading:

```json
{
  "status": "starting",
  "model_loaded": false,
  "rabbitmq": "disconnected",
  "ready_for_rpc": false
}
```

Use repository naming conventions if different.

---

# PART 2 — Docker/Compose dependency readiness

Update Compose so RAG does not start merely because the embedding container process was created.

Preferred direction:

```yaml
embedding:
  healthcheck:
    # readiness-aware check

rag:
  depends_on:
    embedding:
      condition: service_healthy
```

The healthcheck must reflect application readiness, not just TCP port-open state.

Do not introduce a brittle shell dependency if the image can perform a normal HTTP readiness probe.

Do not make startup depend on Internet access after the model is already cached.

---

# PART 3 — Explicit internal-auth RPC failure replies

## Current problem

The shared RabbitMQ consumer verifies the ticket before the normal handler path.

If this raises:

```text
AuthError("authentication ticket has expired")
```

the message fails without a structured reply.

The caller then reports a timeout instead of the actual failure.

## Required behavior

For RPC messages that include:

```text
reply_to
correlation_id
```

an internal-auth verification failure must return a safe structured error reply whenever the consumer can safely do so.

Conceptual reply:

```json
{
  "success": false,
  "error": {
    "code": "internal_auth_expired",
    "message": "Internal authentication context expired"
  }
}
```

Use the existing shared reply-envelope/error contract if one exists.

Do not invent a competing envelope schema.

### Error categories

At minimum distinguish safely:

```text
internal_auth_expired
internal_auth_invalid
internal_auth_required
```

if the current AuthError surface allows that distinction without brittle string parsing.

If not, introduce a small typed/internal error mapping in the shared auth boundary.

Do not leak:

```text
ticket
signature
secret
claims payload
full auth_context
```

---

# PART 4 — Reply authentication

Any error reply sent by the consumer must still satisfy the same internal reply authentication expectations as successful replies.

The RAG RPC client currently verifies the signed reply envelope.

Therefore the auth-failure reply path must:

```text
build safe reply
attach fresh internal auth context
publish to reply_to
preserve correlation_id
```

Do not bypass reply verification merely because the request auth failed.

If a trusted service identity is required to sign the reply and the current consumer context does not have one, use the existing internal service identity pattern already present in the repository.

Do not weaken `verify_internal_ticket_from_envelope(... required=True)` on the caller.

---

# PART 5 — Caller-side error semantics

RAG should receive and surface the explicit downstream error instead of waiting for timeout.

Example desired behavior:

```text
embedding request
↓
embedding consumer detects expired auth
↓
safe RPC error reply
↓
RAG receives error promptly
↓
item classified as dependency/auth failure
```

Not:

```text
↓
75-second RabbitMQ timeout
```

Reuse the current `extract_reply_payload` / shared error handling path where possible.

Do not add embedding-specific hacks to RAG if a generic shared RPC error contract can handle this correctly.

---

# PART 6 — Preserve short-lived internal tickets

Do **not** solve the issue by broadly changing:

```text
ttl_seconds = 300
→ 3600
```

The current short-lived signed ticket model is intentional.

A small TTL adjustment is allowed only if clearly justified by current documented service semantics, but it must **not** be the primary fix.

The system must remain correct even when a queued message legitimately expires.

---

# PART 7 — Startup/model-loading behavior

Inspect the embedding model initialization path.

The task does not need to redesign model caching or Hugging Face downloads.

However:

- readiness must remain false while model initialization/download is incomplete;
- RAG must not begin dependent work during that period;
- startup logs should clearly identify readiness transition;
- model-download retries must not make the service appear RPC-ready prematurely.

If the current model cache can avoid repeated startup downloads, do not change caching behavior unless a small correctness fix is clearly necessary.

---

# PART 8 — Logging / observability

Add concise structured logs for:

```text
embedding readiness false -> true
RabbitMQ RPC consumer connected
internal RPC auth expired
internal RPC auth invalid
auth failure reply sent
auth failure reply could not be sent
```

Do not log raw tickets or secrets.

Use existing logging conventions.

Expected operational distinction:

```text
dependency not ready
auth expired
auth invalid
RPC timeout
```

must be visible as different failure categories.

---

# PART 9 — Security requirements

Preserve:

- `INTERNAL_AUTH_REQUIRED=true`;
- HMAC signature verification;
- audience validation;
- purpose validation;
- payload digest binding;
- short-lived tickets;
- tenant/user identity context;
- reply-envelope verification.

Do not:

- disable verification for eval traffic;
- special-case benchmark traffic;
- accept expired tickets;
- trust caller-supplied tenant/user fields;
- log secrets.

---

# PART 10 — Backward compatibility

Existing healthy RPC requests must behave exactly as before.

Existing non-RPC/fire-and-forget message semantics must not be broken merely to add an RPC error reply path.

If a message has no `reply_to`, an auth failure may remain a nack/error event, but it must be logged safely and explicitly.

Do not fabricate a reply destination.

---

# PART 11 — Tests

Follow:

```text
TEST WHAT CHANGED.
LET GITHUB CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests during implementation.

Because this changes a shared RabbitMQ/auth boundary plus embedding readiness, run the relevant affected suites once near completion.

## Required focused tests

### Shared RabbitMQ/auth boundary

1. Valid internal ticket still reaches handler.
2. Expired internal ticket does not reach handler.
3. Expired RPC ticket with `reply_to` returns structured auth-expired reply.
4. Invalid-signature RPC ticket returns safe structured auth-invalid reply.
5. Missing required auth returns safe structured auth-required reply where applicable.
6. Error reply preserves correlation id.
7. Error reply is freshly signed/authenticated.
8. Raw ticket/secret is not included in reply.
9. Fire-and-forget auth failure does not invent a reply.
10. Unexpected non-auth handler exceptions still follow the existing nack/error behavior.

### RAG RPC client

11. Structured internal-auth error reply is received promptly.
12. It becomes an explicit downstream error, not a timeout.
13. Successful reply verification remains unchanged.
14. Unsigned/invalid reply is still rejected.

### Embedding readiness

15. Model not loaded -> not ready.
16. Model loaded but RPC consumer disconnected -> not ready.
17. Model loaded + RPC consumer connected -> ready for RPC.
18. Kafka disconnected does not incorrectly fail RPC readiness if retrieval RPC does not depend on Kafka.
19. Readiness endpoint reflects transition safely.
20. Health/readiness response contains no secrets.

### Compose/config

21. Embedding healthcheck uses readiness semantics.
22. RAG depends on embedding health, not merely service_started.
23. `docker compose config` succeeds.

---

# PART 12 — Validation

Run:

```powershell
python scripts/ai/check.py focused embedding --files <changed> --tests <focused>
```

and focused shared/RAG tests as appropriate.

Run Ruff on changed Python files.

Run mypy only if changed typed contracts/config fall in normal CI mypy scope.

Near completion run affected backend suites for:

```text
shared consumers / relevant shared tests
embedding
rag
```

according to the repository helper.

Then:

```powershell
docker compose config
```

Do not run the entire local repository solely for completeness.

GitHub CI remains authoritative.

---

# PART 13 — Manual acceptance after merge

After CI passes and the PR is merged:

```powershell
git switch main
git pull
```

Rebuild/recreate affected services:

```text
embedding
rag
```

and any other service required by shared-base changes.

## Test A — readiness during startup

Start embedding from a cold/recreated state.

While model loading is incomplete:

```text
ready_for_rpc = false
```

Once model and RabbitMQ consumer are ready:

```text
ready_for_rpc = true
```

RAG must not begin dependent startup until embedding health is ready.

## Test B — healthy retrieval

Run:

```text
Smoke30
Quick Retrieval / retrieval-only
```

Expected:

```text
30 items accounted
0 embedding timeouts
retrieval completes normally
```

Save:

```text
auth02_quick_retrieval_smoke30.zip
```

## Test C — explicit expired-auth behavior

Use a focused development/integration mechanism to create an already-expired or deterministically expiring internal RPC ticket.

Do **not** wait several minutes just to make a ticket expire if a test hook can safely construct one.

Expected:

```text
caller receives internal_auth_expired promptly
```

and specifically **not**:

```text
RabbitMQ RPC timeout waiting for 'embedding' after 75.0s
```

Capture only the relevant safe log/result evidence.

## Test D — BMARK-15B rerun

After Test A/B/C pass:

```text
Smoke30
Full Diagnostic
```

Download:

```text
bmark15b_smoke30_rerun.zip
```

This rerun must be used for BMARK-15B telemetry analysis.

---

# PART 14 — Out of scope

Do not implement in this task:

- benchmark systemic dependency fail-fast across many items;
- LLM RabbitMQ prefetch tuning;
- vLLM concurrency tuning;
- generation token budgets;
- Pass2 changes;
- hybrid retrieval;
- CrossEncoder;
- embedding model replacement;
- cache architecture redesign;
- SAFE-01 streaming fix.

A separate follow-up may handle benchmark systemic dependency fail-fast.

---

# Acceptance criteria

The task is complete only if:

```text
[ ] Embedding exposes truthful RPC readiness.
[ ] RAG waits for embedding readiness at startup.
[ ] Expired internal RPC auth produces an immediate explicit error reply.
[ ] Invalid internal RPC auth produces an immediate explicit error reply.
[ ] Caller no longer converts auth expiry into a 75s timeout.
[ ] Error replies remain signed and verified.
[ ] Short-lived ticket security remains intact.
[ ] Valid RPC behavior is unchanged.
[ ] No secrets/tickets are logged or returned.
[ ] Focused + affected tests pass.
[ ] docker compose config passes.
[ ] Quick Retrieval Smoke30 passes after merge.
[ ] BMARK-15B Full Diagnostic can be rerun afterward.
```

---

# Final report

Return exactly:

1. Root cause addressed.
2. Changed files grouped by:
   - shared auth/RabbitMQ
   - embedding readiness
   - RAG/client
   - Compose
   - tests/docs
3. New readiness semantics.
4. New auth-failure RPC semantics.
5. Security properties preserved.
6. Focused tests and counts.
7. Affected suites and counts.
8. Ruff/mypy/Compose validation.
9. Manual acceptance still required.
10. Known risks / deferred follow-up:
    - benchmark systemic dependency fail-fast.

Do not commit or push.
