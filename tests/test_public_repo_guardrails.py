"""Guardrail tests for the public repo — verify hygiene, structure, and safety."""
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── README ──────────────────────────────────────────────────


def test_readme_covers_key_review_sections():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for section in (
        "## Problem",
        "## Architecture",
        "## Tech Stack",
        "## Results / Metrics",
        "## Quick Start",
        "## Project Structure",
        "## Public Repo Scope",
    ):
        assert section in readme, f"README missing section: {section}"


# ── .env.example ────────────────────────────────────────────


def test_env_example_documents_public_stack_variables():
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "HF_TOKEN=",
        "NEXT_PUBLIC_API_BASE_URL=",
        "NEXT_PUBLIC_RAG_WS_URL=",
        "NEXT_PUBLIC_ENABLE_TRAINING_TAB=",
        "VLLM_MODEL=",
        "DEFAULT_MODEL=",
        "KAFKA_PORT",
        "MONGODB_PORT",
    ):
        assert variable in env_example, f".env.example missing: {variable}"


def test_env_example_contains_no_placeholder_passwords():
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").lower()
    assert "changeme" not in env_example
    assert "password123" not in env_example
    assert "mysecret" not in env_example


def test_env_example_optional_secrets_are_empty():
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in env_example.splitlines():
        if line.startswith("HF_TOKEN="):
            assert line.strip() == "HF_TOKEN=", "HF_TOKEN should be empty in .env.example"
        if line.startswith("BOOTSTRAP_ADMIN_PASSWORD="):
            assert line.strip() == "BOOTSTRAP_ADMIN_PASSWORD=", (
                "BOOTSTRAP_ADMIN_PASSWORD should be empty: the first admin is "
                "created interactively in the browser on first run"
            )


def test_env_example_required_secrets_use_placeholders():
    """Mandatory secrets must ship as obvious replace-me placeholders, never real values."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "QDRANT_API_KEY=",
        "INTERNAL_AUTH_SECRET=",
        "PASSWORD_PEPPER=",
        "SESSION_PEPPER=",
        "RABBITMQ_PASSWORD=",
        "MONGO_ROOT_PASSWORD=",
        "VLLM_API_KEY=",
    ):
        line = next(
            (ln for ln in env_example.splitlines() if ln.startswith(variable)), None
        )
        assert line is not None, f".env.example missing: {variable}"
        value = line.split("=", 1)[1].strip()
        assert value.startswith("replace-"), (
            f"{variable} must use a replace-* placeholder, got: {value!r}"
        )


# ── Docker Compose ──────────────────────────────────────────


def test_default_compose_no_local_base_image():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ragapp-base:latest" not in compose_text, (
        "Compose should not depend on a locally prebuilt ragapp-base image"
    )


def test_default_compose_references_expected_dockerfiles():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service_dockerfile in (
        "backend/gateway/Dockerfile",
        "backend/llm_agent/Dockerfile",
        "backend/embedding/Dockerfile",
        "backend/rag/Dockerfile",
        "backend/files/Dockerfile",
        "backend/vector_db/Dockerfile",
        "backend/memory/Dockerfile",
        "frontend/Dockerfile",
    ):
        assert service_dockerfile in compose_text, (
            f"Compose missing Dockerfile reference: {service_dockerfile}"
        )


def test_application_images_use_non_root_runtime_users():
    backend_dockerfiles = (
        "backend/gateway/Dockerfile",
        "backend/llm_agent/Dockerfile",
        "backend/embedding/Dockerfile",
        "backend/rag/Dockerfile",
        "backend/files/Dockerfile",
        "backend/vector_db/Dockerfile",
        "backend/memory/Dockerfile",
    )
    for dockerfile in backend_dockerfiles:
        text = (REPO_ROOT / dockerfile).read_text(encoding="utf-8")
        assert "USER app:app" in text, f"{dockerfile} must run as app:app"
        assert "--uid 10001 --gid app" in text, (
            f"{dockerfile} must use the shared runtime UID/GID"
        )

    frontend = (REPO_ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "USER node" in frontend
    assert "COPY --chown=node:node" in frontend


def test_application_images_use_canonical_runtime_lines():
    for dockerfile in (
        "backend/gateway/Dockerfile",
        "backend/llm_agent/Dockerfile",
        "backend/embedding/Dockerfile",
        "backend/rag/Dockerfile",
        "backend/files/Dockerfile",
        "backend/vector_db/Dockerfile",
        "backend/memory/Dockerfile",
    ):
        text = (REPO_ROOT / dockerfile).read_text(encoding="utf-8")
        assert text.startswith("FROM python:3.12-slim"), (
            f"{dockerfile} must stay on the canonical Python 3.12 runtime line"
        )

    frontend = (REPO_ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert frontend.count("FROM node:24-alpine") == 2


def test_frontend_uses_minimal_standalone_runtime():
    config = (REPO_ROOT / "frontend/next.config.js").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")

    assert "output: 'standalone'" in config
    assert "/app/.next/standalone" in dockerfile
    assert "/app/.next/static" in dockerfile
    assert 'CMD ["node", "server.js"]' in dockerfile
    assert "COPY --chown=node:node --from=deps /app/node_modules" not in dockerfile


def test_docker_build_context_excludes_private_and_generated_artifacts():
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for excluded in (
        ".git",
        ".agent-private/",
        ".uv-cache*/",
        "frontend/node_modules/",
        "frontend/.next/",
        "frontend/coverage/",
        ".env",
        ".env.*",
    ):
        assert excluded in dockerignore, f"root .dockerignore missing: {excluded}"


def test_compose_applies_runtime_privilege_restrictions():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "no-new-privileges:true" in compose_text
    assert re.search(r"(?ms)^x-runtime-security:.*?^  cap_drop:\n    - ALL$", compose_text)

    for service in (
        "qdrant",
        "vllm",
        "llm_agent",
        "memory",
        "files",
        "embedding",
        "vector_db",
        "rag",
        "gateway",
        "frontend",
    ):
        block = _compose_service_block(compose_text, service)
        assert "<<: *runtime-security" in block, (
            f"{service} must inherit the runtime security restrictions"
        )

    vllm = _compose_service_block(compose_text, "vllm")
    assert 'user: "0:0"' in vllm
    assert "Root is retained only for the upstream GPU runtime" in vllm

    volume_permissions = _compose_service_block(compose_text, "volume_permissions")
    assert 'user: "0:0"' in volume_permissions
    assert "no-new-privileges:true" in volume_permissions
    assert re.search(r"(?m)^      - CHOWN$", volume_permissions)
    assert "10001:10001" in volume_permissions
    assert "network_mode: none" in volume_permissions
    assert "Migration-only root exception" in volume_permissions


def test_production_edge_has_a_minimal_documented_root_exception():
    compose_text = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    caddy = _compose_service_block(compose_text, "caddy")
    assert 'user: "0:0"' in caddy
    assert "no-new-privileges:true" in caddy
    assert re.search(r"(?m)^      - ALL$", caddy)
    assert re.search(r"(?m)^      - NET_BIND_SERVICE$", caddy)
    assert "Root is retained for ports 80/443" in caddy


def test_compose_does_not_use_reload():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "--reload" not in compose_text, "Compose should not use --reload in production"


def _compose_service_block(compose_text: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^volumes:\n)",
        compose_text,
    )
    assert match, f"Compose missing service block: {service}"
    return match.group(1)


def test_kafka_is_scoped_to_the_ingestion_pipeline():
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ("files", "embedding", "vector_db"):
        block = _compose_service_block(compose_text, service)
        assert "KAFKA_BOOTSTRAP_SERVERS:" in block, f"{service} missing Kafka pipeline config"
        assert "kafka:" in block, f"{service} missing Kafka dependency"

    rag_block = _compose_service_block(compose_text, "rag")
    assert "KAFKA_BOOTSTRAP_SERVERS:" not in rag_block
    assert "kafka:" not in rag_block


def test_rag_runtime_has_no_kafka_dependency():
    requirements = (REPO_ROOT / "backend" / "rag" / "requirements.txt").read_text(encoding="utf-8")
    assert "kafka-python" not in requirements
    assert (REPO_ROOT / "backend" / "rag" / "app" / "messaging" / "rpc_client.py").exists()


# ── Secrets scan ────────────────────────────────────────────


SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style API key"),
    (r"\bhf_(?=[a-zA-Z0-9]*[A-Z])[a-zA-Z0-9]{10,}", "HuggingFace token"),
    (r"AKIA[A-Z0-9]{16}", "AWS access key"),
    (r"BEGIN (PRIVATE|OPENSSH PRIVATE) KEY", "Private key"),
]


def _tracked_files() -> list[Path]:
    """Every path git actually tracks — the set a public clone would receive.

    NUL separators (-z) keep paths with spaces or non-ASCII names intact.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return [
        REPO_ROOT / name
        for name in result.stdout.decode("utf-8").split("\0")
        if name
    ]


def test_no_secrets_in_tracked_files():
    """Scan all non-binary tracked files for real secret patterns."""
    text_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml",
        ".md", ".txt", ".sh", ".env", ".cfg", ".ini", ".toml",
    }
    for path in _tracked_files():
        if not path.is_file():
            continue
        if path.suffix not in text_extensions:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, label in SECRET_PATTERNS:
            match = re.search(pattern, content)
            if match:
                rel = path.relative_to(REPO_ROOT)
                assert False, f"Possible {label} in {rel}: {match.group()[:20]}..."


# ── No compiled artifacts ───────────────────────────────────


def _committable(paths: list[Path]) -> list[str]:
    """Return the subset of paths that git would commit (i.e., not gitignored).

    Local build caches always exist on a dev machine; the guarantee that
    matters for the public repo is that none of them can reach a commit.
    """
    candidates = [p.relative_to(REPO_ROOT).as_posix() for p in paths if ".git" not in p.parts]
    if not candidates:
        return []
    # NUL separators (-z) keep Windows newline translation out of the pipe.
    result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=REPO_ROOT,
        input="\0".join(candidates).encode("utf-8"),
        capture_output=True,
    )
    ignored = set(result.stdout.decode("utf-8").split("\0"))
    return [c for c in candidates if c not in ignored]


def test_no_committable_pycache_directories():
    leaked = _committable(list(REPO_ROOT.rglob("__pycache__")))
    assert leaked == [], f"__pycache__ directories not covered by .gitignore: {leaked}"


def test_no_committable_pyc_files():
    leaked = _committable(list(REPO_ROOT.rglob("*.pyc")))
    assert leaked == [], f".pyc files not covered by .gitignore: {leaked}"


def test_no_committable_pytest_cache():
    leaked = _committable(list(REPO_ROOT.rglob(".pytest_cache")))
    assert leaked == [], f".pytest_cache directories not covered by .gitignore: {leaked}"


# ── Structural sanity ──────────────────────────────────────


def test_gitignore_blocks_env_files():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "!.env.example" in gitignore


def test_dockerignore_exists():
    assert (REPO_ROOT / ".dockerignore").exists(), "Missing .dockerignore"
