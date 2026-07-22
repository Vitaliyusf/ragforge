"""Backfill one legacy single-user installation into one tenant.

The command is dry-run by default.  It intentionally requires one explicit
tenant/admin/user mapping because automatically guessing ownership would risk
cross-tenant disclosure.  Run once per legacy deployment before enabling
``INTERNAL_AUTH_REQUIRED=true``.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from pymongo import MongoClient


MONGO_COLLECTIONS = {
    "files": ["files", "file_tasks", "file_chunks", "file_review_cases", "file_review_decisions"],
    "audit_trail": ["file_audit_events"],
    "memory": [
        "chats",
        "messages",
        "episodic_memories",
        "semantic_preferences",
        "memory_write_log",
        "long_term_memory",
    ],
    "rag": [
        "conversation_threads",
        "conversation_turns",
        "conversation_summaries",
        "graph_checkpoints",
        "answer_reviews",
        "user_feedback",
        "flow_feedback",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill legacy records with immutable tenant ownership")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--admin-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--upload-dir", type=Path)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--qdrant-collection", action="append", default=[])
    parser.add_argument("--apply", action="store_true", help="Apply changes; omit for a read-only report")
    return parser.parse_args()


def ownership(args: argparse.Namespace) -> dict[str, str]:
    return {
        "tenant_id": args.tenant_id,
        "owner_user_id": args.user_id,
        "owner_admin_id": args.admin_id,
    }


def backfill_mongo(args: argparse.Namespace, report: list[dict]) -> None:
    url = os.getenv("MIGRATION_MONGODB_URL")
    if not url:
        raise RuntimeError("MIGRATION_MONGODB_URL is required")
    client = MongoClient(url, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        fields = ownership(args)
        for database_name, collection_names in MONGO_COLLECTIONS.items():
            existing = set(client[database_name].list_collection_names())
            for collection_name in collection_names:
                if collection_name not in existing:
                    continue
                collection = client[database_name][collection_name]
                legacy_query = {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]}
                legacy_count = collection.count_documents(legacy_query)
                owner_query = {
                    "tenant_id": args.tenant_id,
                    "$or": [
                        {"owner_user_id": {"$exists": False}},
                        {"owner_admin_id": {"$exists": False}},
                    ],
                }
                owner_count = collection.count_documents(owner_query)
                report.append({
                    "kind": "mongo",
                    "database": database_name,
                    "collection": collection_name,
                    "legacy_records": legacy_count,
                    "target_tenant_missing_owner": owner_count,
                })
                if args.apply and legacy_count:
                    collection.update_many(legacy_query, {"$set": fields})
                if args.apply and owner_count:
                    collection.update_many(
                        owner_query,
                        {"$set": {"owner_user_id": args.user_id, "owner_admin_id": args.admin_id}},
                    )
    finally:
        client.close()


def migrate_uploads(args: argparse.Namespace, report: list[dict]) -> None:
    if not args.upload_dir or not args.upload_dir.exists():
        return
    target_root = args.upload_dir / args.tenant_id
    candidates = [path for path in args.upload_dir.iterdir() if path.name != args.tenant_id]
    for source in candidates:
        target = target_root / source.name
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite existing tenant upload path: {target}")
        report.append({"kind": "upload", "from": str(source), "to": str(target)})
        if args.apply:
            target_root.mkdir(parents=True, exist_ok=True)
            source.rename(target)


def qdrant_request(base_url: str, path: str, body: dict, api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # nosec B310 - operator-supplied administrative endpoint
        return json.loads(response.read().decode("utf-8"))


def backfill_qdrant(args: argparse.Namespace, report: list[dict]) -> None:
    if not args.qdrant_url:
        return
    api_key = os.getenv("QDRANT_API_KEY", "")
    fields = ownership(args)
    for collection in args.qdrant_collection:
        offset = None
        while True:
            body = {"limit": 256, "with_payload": True, "with_vector": False}
            if offset is not None:
                body["offset"] = offset
            response = qdrant_request(args.qdrant_url, f"/collections/{collection}/points/scroll", body, api_key)
            result = response.get("result") or {}
            points = result.get("points") or []
            legacy_ids = []
            for point in points:
                payload = point.get("payload") or {}
                tenant = payload.get("tenant_id")
                if not tenant or (
                    tenant == args.tenant_id
                    and (not payload.get("owner_user_id") or not payload.get("owner_admin_id"))
                ):
                    legacy_ids.append(point["id"])
            report.append({"kind": "qdrant", "collection": collection, "points": len(legacy_ids)})
            if args.apply and legacy_ids:
                qdrant_request(
                    args.qdrant_url,
                    f"/collections/{collection}/points/payload?wait=true",
                    {"payload": fields, "points": legacy_ids},
                    api_key,
                )
            offset = result.get("next_page_offset")
            if offset is None:
                break


def main() -> int:
    args = parse_args()
    if any(not value.strip() for value in (args.tenant_id, args.admin_id, args.user_id)):
        raise RuntimeError("tenant, admin and user identifiers must be non-empty")
    report: list[dict] = []
    backfill_mongo(args, report)
    migrate_uploads(args, report)
    backfill_qdrant(args, report)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "changes": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
