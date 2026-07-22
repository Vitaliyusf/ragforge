"""Reference MongoDB index catalog for shared/backend collections.

This module centralizes a generic set of collection index definitions and
provides one idempotent helper to create them against a `pymongo` database.
The helper is safe to call repeatedly, but active service startup wiring for
this shared helper is not currently universal across the repository.
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger("db_indexes")

# Index definitions: collection -> list of index specs
INDEX_DEFINITIONS: Dict[str, List[Dict[str, Any]]] = {
    "chats": [
        {"keys": [("chat_id", 1)], "unique": True, "name": "idx_chat_id"},
        {"keys": [("updated_at", -1)], "name": "idx_updated_at"},
    ],
    "messages": [
        {"keys": [("chat_id", 1), ("timestamp", 1)], "name": "idx_chat_timestamp"},
        {"keys": [("message_id", 1)], "unique": True, "name": "idx_message_id"},
    ],
    "files": [
        {"keys": [("status", 1)], "name": "idx_status"},
        {"keys": [("filename", 1)], "name": "idx_filename"},
        {"keys": [("file_id", 1)], "unique": True, "name": "idx_file_id"},
    ],
    "memories": [
        {"keys": [("category", 1), ("updated_at", -1)], "name": "idx_category_updated"},
        {"keys": [("memory_id", 1)], "unique": True, "name": "idx_memory_id"},
    ],
    "dlq_messages": [
        {"keys": [("service", 1), ("created_at", -1)], "name": "idx_service_created"},
        {"keys": [("status", 1)], "name": "idx_dlq_status"},
        {
            "keys": [("timestamp", 1)],
            "name": "idx_dlq_ttl",
            "expireAfterSeconds": 7776000,  # 90 days TTL
        },
    ],
    "audit_log": [
        {"keys": [("event_type", 1), ("timestamp", -1)], "name": "idx_event_timestamp"},
        {"keys": [("source_ip", 1)], "name": "idx_source_ip"},
        {
            "keys": [("timestamp", 1)],
            "name": "idx_audit_ttl",
            "expireAfterSeconds": 7776000,  # 90 days TTL
        },
    ],
    "api_keys": [
        {"keys": [("key_hash", 1)], "unique": True, "name": "idx_key_hash"},
        {"keys": [("expires_at", 1)], "name": "idx_expires_at"},
    ],
    "training_jobs": [
        {"keys": [("job_id", 1)], "unique": True, "name": "idx_job_id"},
        {"keys": [("status", 1), ("created_at", -1)], "name": "idx_status_created"},
    ],
    "training_datasets": [
        {"keys": [("dataset_id", 1)], "unique": True, "name": "idx_dataset_id"},
    ],
    "model_adapters": [
        {"keys": [("adapter_id", 1)], "unique": True, "name": "idx_adapter_id"},
        {"keys": [("base_model", 1), ("created_at", -1)], "name": "idx_model_created"},
    ],
}


def ensure_indexes(db: Any) -> Dict[str, int]:
    """
    Attempt to create every index declared in `INDEX_DEFINITIONS`.

    Args:
        db: `pymongo` database handle used to access collections by name.

    Returns:
        Dict mapping each collection name to the number of `create_index`
        calls that completed without raising.

    Side effects:
        Calls `create_index` on each configured collection, logs warnings for
        individual failures, and continues processing the remaining indexes.
    """
    results = {}

    for collection_name, indexes in INDEX_DEFINITIONS.items():
        collection = db[collection_name]
        created = 0

        for index_spec in indexes:
            keys = index_spec["keys"]
            kwargs = {k: v for k, v in index_spec.items() if k != "keys"}

            try:
                collection.create_index(keys, **kwargs)
                created += 1
            except Exception as e:
                logger.warning(
                    f"Failed to create index {index_spec.get('name', 'unnamed')} "
                    f"on {collection_name}: {e}"
                )

        results[collection_name] = created
        if created > 0:
            logger.info(f"Ensured {created} indexes on '{collection_name}'")

    total = sum(results.values())
    logger.info(f"Index initialization complete: {total} indexes across {len(results)} collections")
    return results
