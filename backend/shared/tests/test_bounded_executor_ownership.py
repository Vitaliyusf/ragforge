from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("service", "owner_paths"),
    [
        ("files", ("backend/files/app/main.py",)),
        ("vector_db", ("backend/vector_db/app/main.py",)),
        ("embedding", ("backend/embedding/app/main.py",)),
        (
            "memory",
            (
                "backend/memory/app/bootstrap/runtime.py",
                "backend/memory/app/services/memory_handler_service.py",
            ),
        ),
        ("llm_agent", ("backend/llm_agent/app/main.py",)),
    ],
)
def test_service_owns_and_closes_one_bounded_executor(
    service: str,
    owner_paths: tuple[str, ...],
) -> None:
    sources = [
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in owner_paths
    ]
    combined = "\n".join(sources)

    assert combined.count("BoundedExecutor(") == 1, service
    assert "await executor.run(" in combined, service
    assert (
        "await executor.shutdown()" in combined
        or "await self.executor.shutdown()" in combined
    ), service
    assert "run_in_executor(None" not in combined, service
    assert "asyncio.to_thread(" not in combined, service
