# DOCKER-BASE-01 — Docker runtime baseline and image optimization

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Phase:** Career-first production foundation  
**Priority:** P0  
**Branch:** `chore/docker-runtime-baseline`  
**Depends on:** `SEC-03 COMPLETE` / runtime hardening green

## Goal

Establish a clean, reproducible Docker/Compose runtime baseline for RagForge after the Python/Node dependency modernization and non-root container hardening.

This task should improve:

```text
image structure
+ image size where practical
+ build/cache efficiency
+ dev/prod parity
+ runtime dependency boundaries
+ Compose clarity
+ measurable container evidence
```

without changing application behavior.

The objective is **not** to redesign the deployment platform or introduce Kubernetes.

---

# 1. Non-negotiable execution rules

- Work only on `DOCKER-BASE-01`.
- Preserve unrelated dirty files.
- If an unrelated file becomes modified during the task, preserve it and continue unless it overlaps the files required by this task.
- Do not reset/stash/revert/clean.
- Do not commit or push unless explicitly asked.
- Do not run doctor.
- Do not repair `.venv`.
- Canonical Python runtime is **3.12**.
- Canonical Node runtime is **24 LTS**.
- Keep the accepted vLLM image/runtime exactly as currently configured.
- Preserve all `SEC-03` non-root users, writable-path ownership, capability dropping, `no-new-privileges`, and documented root exceptions.
- Do not weaken container security to reduce image size.
- Do not create a local shared `ragapp-base` image. The repository explicitly rejects that topology today.
- Do not upgrade application dependencies in this task.
- Do not upgrade stateful infrastructure majors.
- Do not introduce Kubernetes.
- Do not change RAG/retrieval/embedding/model semantics.
- Do not remove the Hugging Face provider silently.
- Do not unbake the canonical embedding model merely to make the embedding image look smaller.
- No broad application refactor.

Testing rule:

> TEST WHAT CHANGED. LET CI TEST THE REPOSITORY.

---

# 2. Inventory and evidence first

Before editing, capture a private baseline under `.agent-private/`.

Audit:

```text
backend/*/Dockerfile
frontend/Dockerfile
frontend/next.config.*
frontend/package.json
frontend/package-lock.json
docker-compose.yml
docker-compose.prod.yml
.dockerignore
frontend/.dockerignore
backend/*/.dockerignore if present
docker/requirements-base.txt
backend/*/requirements.txt
SEC-03 runtime user / writable path rules
```

Capture:

```text
service
image tag
image size
configured runtime user
base image
number of build stages
runtime entrypoint/cmd
healthcheck
host-exposed ports
named volumes
runtime-writable paths
security_opt
cap_drop
build context
```

Also capture current image sizes for:

```text
gateway
rag
files
vector_db
memory
embedding
llm_agent
frontend
```

Do not rely on old numbers from another task; measure the current branch state.

Record build duration only when before/after conditions are reasonably comparable. If cache conditions differ, report that limitation rather than claiming an improvement.

---

# 3. Preserve the SEC-03 security baseline

The final runtime must preserve:

## Backend custom images

```text
non-root runtime user
fixed intended UID/GID
explicit writable directories
no silent chmod/chown failures
```

## Frontend

```text
non-root `node` runtime
```

## Compose application services

```text
security_opt:
  - no-new-privileges:true

cap_drop:
  - ALL
```

Keep documented narrow exceptions only where already justified:

- vLLM/GPU runtime
- production Caddy privileged port binding
- one-shot volume ownership migration

The one-shot volume migration must remain:
- bounded;
- network-isolated;
- capability-minimal;
- non-persistent;
- clearly documented.

Do not convert normal application containers back to root.

---

# 4. Frontend production image — highest priority optimization

The current frontend image is known to be materially larger after the Next 16 / React 19 migration.

Audit the actual built image and then implement a proper Next.js production runtime.

## Preferred target

Evaluate and, if compatible, use:

```js
output: "standalone"
```

in `frontend/next.config.js`.

The final runtime stage should contain only what the standalone server needs, typically:

```text
.next/standalone
.next/static
public                 # only if present/needed
minimal package/runtime metadata only if required
```

Do **not** copy the entire source tree and full development `node_modules` into the production runner if standalone output makes them unnecessary.

Preferred runtime command should use the generated standalone server when applicable, e.g. conceptually:

```text
node server.js
```

rather than requiring the full development dependency tree.

## Acceptance

Verify:

- production build succeeds under Node 24;
- all existing routes work;
- `/api/health` still works if part of the current app;
- environment/build-arg behavior remains correct;
- runtime still binds to the intended host/port;
- non-root `node` user remains;
- frontend container starts correctly in Compose;
- authenticated application flow is not broken.

Measure frontend image size before/after.

Do not claim a percentage improvement unless measured from comparable image builds.

---

# 5. Backend Dockerfile convergence

Audit the seven custom Python application Dockerfiles.

They should follow a consistent structure where practical:

```text
Python 3.12 slim base
→ uv binary
→ runtime environment
→ workdir
→ dependency manifests
→ dependency install
→ application/shared copy
→ writable directory ownership
→ non-root USER
→ command/entrypoint
```

Converge accidental differences, but do **not** create a custom shared base image.

## Dependency layers

Preserve authoritative dependency ownership:

```text
docker/requirements-base.txt
+
backend/<service>/requirements.txt
```

Do not duplicate shared pins back into service manifests.

Order copies so dependency layers remain cacheable when only application source changes.

Do not change package versions.

## Build cache

Use BuildKit cache mounts only if they:
- materially improve build reuse;
- do not change the final image contents;
- remain understandable and supported by the current Docker workflow.

Do not introduce complex build tooling for marginal gains.

---

# 6. Heavy ML image audit

## `llm_agent`

The local Hugging Face provider remains a real selectable capability.

Audit why the image is large:

```text
torch
CUDA runtime dependencies
transformers
accelerate
sentencepiece
model/runtime artifacts
```

Do not silently delete provider support.

Evaluate these options in order:

1. Can the current image be reduced by normal layer/runtime cleanup without behavioral change?
2. Can CPU/GPU dependency ownership be made more deliberate without changing supported runtime behavior?
3. Would separating the optional local-HF provider into a different image/profile materially simplify the canonical vLLM client path?

Option 3 is **not automatically required**.

If separation would require broad product/config/runtime changes, record it as a deferred optimization rather than expanding this task.

## `embedding`

The canonical embedding model is intentionally baked into the image to avoid runtime download/startup dependency.

Do not remove that behavior just for image-size optics.

Optimize only:
- duplicate layers;
- unnecessary caches/build artifacts;
- dependency ownership;
- build context.

Measure current size and report why the model image remains large.

---

# 7. `.dockerignore` and build context audit

Ensure the root/frontend build contexts do not unnecessarily include:

```text
.git
node_modules
.next
coverage
test output
local caches
.agent-private
.uv-cache*
virtual environments
logs
temporary benchmark artifacts
local secrets / .env
editor files
```

Do not ignore files required by Docker builds.

Prefer the smallest clear ignore rules that materially reduce build context.

Do not introduce secret values into images or build logs.

---

# 8. Runtime artifacts and package-manager cleanup

Audit whether image stages leave behind avoidable artifacts:

```text
package-manager caches
temporary requirements files
build-only files
source files not needed at runtime
test/dev dependencies in production frontend
temporary model/download metadata not needed at runtime
```

Remove only artifacts that are demonstrably unnecessary.

Do not run destructive cleanup commands that make builds fragile.

---

# 9. Compose runtime baseline

Audit both:

```text
docker-compose.yml
docker-compose.prod.yml
```

The goal is clarity and correct runtime behavior, not YAML cleverness.

## Verify

- build/image ownership is clear;
- host-exposed ports are intentional;
- internal services do not gain unnecessary host exposure;
- networks are intentional;
- named volumes have clear owners;
- healthchecks match actual readiness;
- dependency ordering uses health/completion semantics where required;
- restart policies are appropriate;
- `SEC-03` privilege restrictions survive both base and prod overlays;
- env/build args are not accidentally duplicated or contradictory;
- development-only behavior does not leak into production;
- production-only edge behavior is isolated to the production overlay.

Do not add YAML anchors/frameworks merely to reduce line count if readability gets worse.

---

# 10. Health and startup semantics

Do not redesign HEALTH-01.

Verify the existing contract survives image/runtime optimization:

```text
/live
/ready
dependency-aware readiness
Compose health dependencies
frontend health
Qdrant
vLLM
Kafka/RabbitMQ dependent startup
```

If an optimization changes startup ordering, fix only the Docker/Compose issue.

Do not change application health semantics unless a genuine Docker integration regression requires a minimal fix.

---

# 11. Dev vs production separation

The production overlay should describe production-specific concerns, not duplicate the entire base Compose file.

Audit for:
- public edge;
- host port exposure;
- restart policy;
- production environment overrides;
- production-only volumes/secrets;
- debug/dev-only behavior.

Do not create a second unrelated Compose architecture.

---

# 12. Image evidence

Capture exact before/after:

```text
gateway
rag
files
vector_db
memory
embedding
llm_agent
frontend
```

For each:

```text
before bytes/human size
after bytes/human size
absolute delta
percentage delta
reason
```

If an image grows, explain why.

Important expected focus:

```text
frontend runtime image
llm_agent heavy ML runtime
```

But do not force reductions at the expense of supported behavior.

---

# 13. Optional build evidence

If cheap and repeatable, capture:

```text
frontend build duration
selected backend build duration
Docker build context size
cold container readiness
```

Only compare runs with equivalent cache conditions.

A warm-cache build may be useful operational evidence, but do not compare warm-after against cold-before as if it were a valid optimization metric.

---

# 14. Validation

Because this task should primarily change Docker/Compose/runtime packaging, do not run the full backend test matrix unless production Python code is changed.

Required validation at final candidate state:

1. `docker compose config --quiet`
2. production overlay config with required placeholder env:
   ```text
   docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
   ```
3. frontend focused tests if frontend config/Docker behavior changed
4. full frontend suite once if `next.config.*`, package/runtime behavior, or frontend build structure changed
5. Next production build once
6. build all changed custom application images once
7. inspect final image runtime users
8. inspect final image sizes
9. recreate/start the Compose stack
10. verify application/backend health
11. verify `SEC-03` runtime restrictions:
    - non-root users
    - `no-new-privileges`
    - capability drops
    - writable paths
12. minimal authenticated chat smoke
13. one ingestion/upload smoke if an authenticated path is available
14. `git diff --check`
15. repository guardrail tests affected by Docker/Compose changes

If ingestion requires a user/browser session unavailable to the agent, report it as a manual validation item rather than inventing credentials or weakening auth.

GitHub Actions remains final clean-environment authority.

---

# 15. Testing discipline

During implementation:

```text
Dockerfile/Compose edit
→ docker compose config
→ smallest affected image build
→ focused runtime check
```

Near completion:

```text
all changed image builds once
→ Compose runtime once
→ affected guardrails
→ frontend suite/build once if relevant
→ final diff
```

Do not repeatedly rebuild all large ML images after unrelated edits.

If a later edit cannot invalidate an already-built heavy image, do not rebuild it.

Use one environment retry after diagnosis; otherwise mark host-local validation blocked and use an authoritative container/CI path where appropriate.

---

# 16. Expected production changes

Likely allowed files:

```text
backend/*/Dockerfile
frontend/Dockerfile
frontend/next.config.js
docker-compose.yml
docker-compose.prod.yml
.dockerignore
frontend/.dockerignore
tests/test_public_repo_guardrails.py
docs directly required to document the Docker runtime contract
```

Do not edit application business logic unless required to fix a Docker-induced integration regression.

---

# 17. Guardrails to add/update

Repository contract tests should protect important final decisions, for example:

- Python services stay on Python 3.12 runtime line.
- Frontend stays on Node 24 runtime line.
- custom app images have explicit non-root runtime users.
- Compose keeps `no-new-privileges` / capability dropping.
- Qdrant stays on unprivileged image.
- accepted vLLM image stays unchanged.
- frontend standalone runtime contract, if adopted.
- default Compose does not depend on a custom local shared base image.
- required production Caddy exception remains minimal/documented.

Avoid brittle tests that assert every Dockerfile line number or formatting detail.

---

# 18. Completion report

Report:

```text
runtime structure:
  Python base:
  Node base:
  frontend runtime strategy:
  backend dependency strategy:
  shared local base image:
  vLLM:
  embedding model bake:

images:
  gateway before/after:
  rag before/after:
  files before/after:
  vector_db before/after:
  memory before/after:
  embedding before/after:
  llm_agent before/after:
  frontend before/after:

build:
  context changes:
  cache/layer improvements:
  comparable build timing evidence:

security:
  backend runtime UID:
  frontend runtime UID:
  no-new-privileges:
  capability dropping:
  root exceptions:
  volume permission migration:

compose:
  dev/prod structure:
  health/dependency ordering:
  ports:
  volumes:
  networks:

heavy ML:
  llm_agent decision:
  embedding decision:
  deferred optimization:

validation:
  compose config:
  production overlay:
  frontend tests:
  frontend build:
  image builds:
  live health:
  chat smoke:
  ingestion smoke:
  guardrails:
  diff check:

limitations:
```

Also report:
- files changed;
- production files added/deleted;
- obsolete Docker paths removed;
- dependencies added/removed;
- unresolved blockers.

---

# 19. Evidence / career value

Produce measurable evidence only.

Useful examples, if actually measured:

> Reduced the Next.js production container from X GB to Y MB by moving to standalone output and excluding development dependencies/source artifacts.

> Standardized seven Python service images around one reproducible dependency-layer pattern while preserving non-root runtime security and dependency-aware readiness.

> Reduced Docker build context by X% and improved comparable warm build time from A to B.

Never invent numbers.

---

# 20. Stop condition

When the final Docker/runtime baseline is green:

```text
implementation
→ focused validation
→ final image builds
→ Compose runtime
→ runtime/security inspection
→ final diff audit
→ NO MORE SOURCE EDITS
→ record handoff once
→ rebuild brain once
→ validate brain once
```

Then STOP.

Do not start:
- RAG-RESUME-01
- frontend redesign
- Kubernetes
- dependency upgrades
- unrelated cleanup
