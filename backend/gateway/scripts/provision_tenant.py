"""Offline tenant provisioning command.

Run inside the gateway container so database credentials and password peppers
come from its environment.  The administrator password is read from a hidden
prompt or ``PROVISION_ADMIN_PASSWORD``; it is never accepted as a CLI argument.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os

from pymongo import MongoClient

from app.core.config import GatewayConfig
from app.services.auth_service import AuthService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision an isolated tenant and initial administrator")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--display-name", default="Administrator")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = os.getenv("PROVISION_ADMIN_PASSWORD") or getpass.getpass("Initial admin password: ")
    config = GatewayConfig()
    client = MongoClient(config.mongo_connection_string, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        service = AuthService(client[config.mongo_database_name], config)
        service.ensure_indexes()
        result = service.provision_tenant_admin(
            tenant_id=args.tenant_id,
            tenant_name=args.tenant_name,
            admin_email=args.admin_email,
            admin_password=password,
            display_name=args.display_name,
        )
        print(json.dumps(result, indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
