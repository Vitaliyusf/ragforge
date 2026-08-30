# Demo workspace bootstrap

`bootstrap_demo_workspace.py` fills an empty **local** RAGForge workspace with a
small synthetic dataset so the product can be shown without repeating the same
manual setup. It is a demo convenience, not a fixture framework.

## What it does not do

- It does not write to MongoDB, Qdrant, RabbitMQ or Kafka. Every object is
  created through the public, authenticated gateway API — the same contracts the
  browser calls.
- It does not bypass, weaken or stub authentication. It logs in as a real
  operator using credentials the caller supplies at run time.
- It ships no secret. The password is read from `RAGFORGE_DEMO_PASSWORD` and is
  never written to disk or into any created object.
- It contains no real personal, customer or credential data. The corpus is a
  fictional freight company.
- It creates no frontend-only data. Nothing appears in the UI that the backend
  did not actually produce.

## Production isolation

Three independent guards, all in `main()`/`assert_local_target()`:

1. **Loopback only.** The gateway host must be `localhost`, `127.0.0.1` or
   `::1`. Any other host is a hard refusal before authentication is attempted.
2. **Explicit opt-in.** `--confirm` is required; without it the script exits 2.
   `--dry-run` prints the plan and writes nothing.
3. **Never automatic.** Nothing invokes it — no Compose service, no Dockerfile,
   no hook, no CI job, no application import. It runs only when a human runs it.

Everything it creates is prefixed `[demo]`, so demo objects are identifiable at
a glance and removable through the ordinary product UI.

## Usage

From the repository root, with the local Compose stack healthy:

```powershell
# See the plan without writing anything
py -3.12 scripts/demo/bootstrap_demo_workspace.py --dry-run

# Populate the workspace
$env:RAGFORGE_DEMO_PASSWORD = "<operator password>"
py -3.12 scripts/demo/bootstrap_demo_workspace.py --confirm --email operator@example.com
```

Options: `--base-url` (default `http://localhost:8000`), `--tenant` (default
`default`), `--email` / `RAGFORGE_DEMO_EMAIL`.

Re-running is safe: a document, conversation, dataset or run that already
carries its demo name is reused rather than duplicated.

## What it seeds

| Target | How |
| ------ | --- |
| Example documents | Three markdown files uploaded via `POST /v1/files/upload` and ingested by the real pipeline. |
| One conversation | `POST /v1/chats`, then a real grounded answer from `POST /v1/chat` (`use_rag: true`), persisted via `POST /v1/chats/{id}/messages`. |
| One evaluation run | A six-query golden set (`POST /v1/metrics/eval/datasets`) plus one `retrieval`-mode run (`POST /v1/metrics/eval/runs`). Retrieval mode calls no model, so the run is free and reproducible. |
| One operational issue | A fourth document whose text trips the ingestion issue detector's prompt-injection heuristic. The pipeline quarantines it into a real review case with a real recovery path — it is not a fabricated status. |

## Intentionally unavailable: a stored trace

The script cannot seed an inspectable conversation trace, and does not pretend
to.

A trace exists only as a live event stream: `backend/rag/app/services/conversation_events.py`
emits `trace` envelopes over the Socket.IO conversation channel, and only to a
viewer whose role is `admin`. `GET /v1/rag/traces/{id}` has no matching handler
in the RAG service — `get_trace` is absent from the action dispatch in
`backend/rag/app/main.py`, so the request falls through to the conversation
graph rather than returning a stored trace. No public contract persists or
replays a trace after the turn ends.

To inspect one, send a chat message as an admin and open the **Trace** tab in
the developer inspector while the turn runs.
