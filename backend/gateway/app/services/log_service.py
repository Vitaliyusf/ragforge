"""Log service for reading service logs."""
import os
import subprocess
import json
from typing import Dict, Any, List, Optional


class LogService:
    """Service for reading logs from services."""

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir is None:
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
            log_dir = os.getenv("LOG_DIR", os.path.join(project_root, "logs"))
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_logs(self, service: str, lines: int = 100, *, tenant_id: str) -> Dict[str, Any]:
        """Get logs for a specific service (Docker → file → empty fallback)."""
        if result := self._get_docker_logs(service, lines, tenant_id):
            return result
        if result := self._get_file_logs(service, lines, tenant_id):
            return result
        return {
            "service": service,
            "logs": [],
            "source": "empty",
        }

    def get_all_logs(self, services: List[str], lines: int = 50, *, tenant_id: str) -> Dict[str, Any]:
        """Get logs from all services."""
        all_logs = {}
        for service in services:
            try:
                all_logs[service] = self.get_logs(service, lines, tenant_id=tenant_id)
            except Exception as e:
                all_logs[service] = {
                    "service": service,
                    "logs": [f"Error: {str(e)}"],
                    "source": "error",
                }
        return all_logs

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_docker_logs(self, service: str, lines: int, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Attempt to fetch logs via `docker logs`. Returns None if unavailable."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                log_lines = self._tenant_lines(result.stdout.split("\n"), tenant_id)
                if log_lines:
                    return {
                        "service": service,
                        "logs": log_lines[-lines:] if len(log_lines) > lines else log_lines,
                        "source": "docker",
                    }
        except Exception:
            pass
        return None

    def _get_file_logs(self, service: str, lines: int, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Attempt to fetch logs from the filesystem. Returns None if no readable file found."""
        candidates = [
            os.path.join(self.log_dir, f"{service}_service.log"),
            os.path.join("/app/logs", f"{service}_service.log"),
            os.path.join(os.path.expanduser("~"), "logs", f"{service}_service.log"),
            os.path.join(os.getcwd(), "logs", f"{service}_service.log"),
        ]
        if os.path.exists("/app"):
            candidates.insert(1, os.path.join("/app/logs", f"{service}_service.log"))

        for path in candidates:
            try:
                normalized = os.path.normpath(
                    os.path.abspath(path) if not os.path.isabs(path) else path
                )
                if os.path.isfile(normalized):
                    with open(normalized, "r", encoding="utf-8", errors="ignore") as f:
                        log_lines = self._tenant_lines(f.readlines(), tenant_id)
                        if log_lines:
                            return {
                                "service": service,
                                "logs": log_lines[-lines:] if len(log_lines) > lines else log_lines,
                                "source": "file",
                            }
            except Exception:
                continue
        return None

    @staticmethod
    def _tenant_lines(lines: List[str], tenant_id: str) -> List[str]:
        """Fail closed: malformed and cross-tenant log lines are never returned."""
        scoped: List[str] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            event_tenant = event.get("tenant_id")
            if event_tenant is None and isinstance(event.get("data"), dict):
                event_tenant = event["data"].get("tenant_id")
            if event_tenant == tenant_id:
                scoped.append(json.dumps(event, ensure_ascii=True, separators=(",", ":")))
        return scoped
