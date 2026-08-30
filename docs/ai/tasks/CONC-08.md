# CONC-08 — Remove large base64 file payloads from RabbitMQ and bound upload memory

**Phase:** Ingestion performance  
**Priority:** P1  
**Branch:** `perf/file-upload-io`  
**Depends on:** `CONC-01`, `CONC-02`

## Goal

Make file upload/ingestion memory- and broker-efficient while preserving validation, ownership, audit and extraction behavior.

## Audit evidence

Gateway upload currently:

```text
read entire UploadFile into list of 1 MiB chunks
→ join into one bytes object
→ base64 encode entire file
→ JSON/RabbitMQ RPC
```

Files service then:

```text
base64 decode entire payload
→ write to uploads volume
→ publish path to embedding
```

A 25 MiB file therefore creates multiple full-size copies and ~33% base64 expansion in the broker message.

Files and Embedding already share `uploads_data:/app/uploads` in Compose.

## Required target

RabbitMQ carries metadata/control messages, not large binary payloads.

Implement the smallest production-appropriate binary ingress path.

Preferred options, in order:

1. stream once to a managed shared upload location and send a validated opaque reference/path to Files;
2. internal streaming upload endpoint owned by Files, with Gateway streaming/proxying and then sending only the file reference;
3. another existing repository-owned object-storage primitive if one already exists.

Do not add MinIO/S3 emulation merely for architecture optics.

## Security and ownership

- validate filename/type/signature/size;
- prevent path traversal/symlink escape;
- generate server-owned file IDs/paths;
- never trust a caller-provided arbitrary filesystem path;
- atomic/temporary write then finalize;
- clean partial uploads on cancellation/failure;
- tenant/user ownership stays authoritative;
- audit does not expose unsafe host paths.

## Backpressure

- stream in bounded chunks;
- do not buffer the entire file in Gateway or Files;
- define max concurrent uploads;
- define max bytes in-flight if useful;
- client disconnect cancels the transfer cleanly.

## Compatibility

If a legacy base64 RPC shape must remain temporarily, keep it bounded and explicitly deprecated. Do not let new production flow use it.

## Benchmark

At e.g. 1 MiB / 10 MiB / max allowed size:

- peak Gateway RSS;
- peak Files RSS;
- upload wall time;
- broker message bytes;
- broker publish latency;
- 1/4/8 concurrent uploads;
- failure cleanup.

## Acceptance

- normal production upload does not place the full file bytes in RabbitMQ;
- memory overhead is bounded by streaming buffers rather than file size;
- existing extraction pipeline still receives the canonical managed path;
- upload smoke and ingestion smoke remain green.
## Validation — MINIMAL

Follow `CONC-VALIDATION-POLICY.md`.

For this task run only:

- the smallest focused regression test(s) that prove the changed behavior;
- Ruff on changed Python files;
- `git diff --check`.

Do **not** run a full service suite, repository suite, broad mypy, Docker rebuild, or load benchmark unless this task explicitly owns that measurement.

If the task includes a benchmark section, run only the smallest benchmark needed to prove this task's own performance claim. The full load campaign belongs to `CONC-99`.

## Execution rules

- Current source wins.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not repair `.venv`.
- Use isolated Python 3.12 fallback only if needed.
- Once the focused regression is green, STOP.
