#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_TMP = ROOT / ".agent-private" / "test-tmp"
MAX_FAILURE_LINES = 80
PROBE_TIMEOUT_SECONDS = 12

SERVICE_DIRS = {
    "rag": ROOT / "backend" / "rag",
    "gateway": ROOT / "backend" / "gateway",
    "files": ROOT / "backend" / "files",
    "embedding": ROOT / "backend" / "embedding",
    "vector_db": ROOT / "backend" / "vector_db",
    "memory": ROOT / "backend" / "memory",
    "llm_agent": ROOT / "backend" / "llm_agent",
}

def _candidate_pythons() -> list[Path]:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result

def _probe_python(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "not found"
    try:
        proc = subprocess.run(
            [str(path), "-c", "import sys; print(sys.version.split()[0])"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stdout or "").strip()[:300]
    return True, (proc.stdout or "").strip()

def resolve_python() -> tuple[str, str]:
    reasons: list[str] = []
    for candidate in _candidate_pythons():
        ok, detail = _probe_python(candidate)
        if ok:
            return str(candidate), detail
        reasons.append(f"{candidate}: {detail}")
    raise RuntimeError("No accessible Python interpreter. " + " | ".join(reasons))

def python_cmd() -> str:
    return resolve_python()[0]

def _tail(text: str, limit: int = MAX_FAILURE_LINES) -> list[str]:
    return (text or "").splitlines()[-limit:]

def run_check(
    name: str,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    blocked_markers: tuple[str, ...] = (),
) -> tuple[bool, bool]:
    """Return (passed, blocked)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        print(f"{name}: BLOCKED")
        print(str(exc)[:500])
        return False, True

    output = proc.stdout or ""
    if proc.returncode == 0:
        print(f"{name}: PASS")
        return True, False

    low = output.lower()
    blocked = any(marker.lower() in low for marker in blocked_markers)
    print(f"{name}: {'BLOCKED' if blocked else 'FAIL'}")
    for line in _tail(output):
        print(line)
    return False, blocked

def python_module(module: str, *args: str) -> list[str]:
    return [python_cmd(), "-m", module, *args]

def service_env(service_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    backend = ROOT / "backend"
    current = env.get("PYTHONPATH", "")
    entries = [str(service_dir), str(backend)]
    if current:
        entries.append(current)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env

def _service_basetemp(service: str) -> Path:
    path = PRIVATE_TMP / service
    PRIVATE_TMP.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def doctor() -> int:
    try:
        py, version = resolve_python()
        print(f"Python: PASS ({version}; {py})")
    except RuntimeError as exc:
        print("Python: BLOCKED")
        print(str(exc))
        print("Overall: BLOCKED")
        return 2

    overall = True
    probes = [
        ("Ruff", [py, "-m", "ruff", "--version"]),
        ("Pytest", [py, "-m", "pytest", "--version"]),
        ("Mypy", [py, "-m", "mypy", "--version"]),
    ]
    for name, cmd in probes:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=PROBE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"{name}: BLOCKED")
            print(str(exc)[:500])
            overall = False
            continue

        if proc.returncode == 0:
            first = (proc.stdout or "").strip().splitlines()
            detail = first[0] if first else "available"
            print(f"{name}: PASS ({detail})")
        else:
            print(f"{name}: BLOCKED")
            for line in _tail(proc.stdout or "", 20):
                print(line)
            overall = False

    print("Overall:", "PASS" if overall else "BLOCKED")
    return 0 if overall else 2

def run_ruff(files: list[str]) -> tuple[bool, bool]:
    if not files:
        print("Ruff: SKIP (no files supplied)")
        return True, False
    return run_check(
        "Ruff",
        python_module("ruff", "check", *files, "--quiet"),
        blocked_markers=("No module named ruff",),
    )

def run_mypy(files: list[str]) -> tuple[bool, bool]:
    if not files:
        print("Mypy: SKIP (no Python files supplied)")
        return True, False
    return run_check(
        "Mypy",
        python_module(
            "mypy",
            *files,
            "--config-file",
            str(ROOT / "mypy.ini"),
            "--follow-imports=skip",
        ),
        blocked_markers=("No module named mypy",),
    )

def run_pytest(service: str, tests: list[str], label: str) -> tuple[bool, bool]:
    service_dir = SERVICE_DIRS[service]
    basetemp = _service_basetemp(service)
    return run_check(
        label,
        python_module(
            "pytest",
            *tests,
            "-q",
            "--maxfail=1",
            "--basetemp",
            str(basetemp),
        ),
        cwd=service_dir,
        env=service_env(service_dir),
        blocked_markers=(
            "pytest_asyncio",
            "pytest-asyncio",
            "error importing plugin",
            "pluginmanager",
            "no module named pytest",
            "importerror while loading conftest",
        ),
    )

def run_frontend_tests(test_args: list[str]) -> tuple[bool, bool]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        print("Frontend tests: BLOCKED")
        print("npm was not found on PATH")
        return False, True

    cmd = [npm, "test"]
    if test_args:
        cmd.extend(["--", *test_args])
    return run_check("Frontend tests", cmd, cwd=ROOT / "frontend")

def run_frontend_build() -> tuple[bool, bool]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        print("Frontend build: BLOCKED")
        print("npm was not found on PATH")
        return False, True
    return run_check("Frontend build", [npm, "run", "build"], cwd=ROOT / "frontend")

def summary(results: list[tuple[bool, bool]]) -> int:
    if all(passed for passed, _ in results):
        print("Overall: PASS")
        return 0
    if any(blocked for _, blocked in results):
        print("Overall: BLOCKED/FAIL")
        return 2
    print("Overall: FAIL")
    return 1

def focused(args: argparse.Namespace) -> int:
    if args.service == "frontend":
        return summary([run_frontend_tests(args.tests or [])])

    results: list[tuple[bool, bool]] = []

    py_files = [f for f in (args.files or []) if f.endswith(".py")]
    if py_files:
        results.append(run_ruff(py_files))

    if args.mypy:
        results.append(run_mypy(py_files))

    if not args.tests:
        print("Pytest focused: SKIP (no tests supplied)")
    else:
        results.append(run_pytest(args.service, args.tests, "Pytest focused"))

    return summary(results or [(True, False)])

def affected(args: argparse.Namespace) -> int:
    if args.service == "frontend":
        results = [run_frontend_tests([])]
        if args.build:
            results.append(run_frontend_build())
        return summary(results)

    service_rel = str(SERVICE_DIRS[args.service].relative_to(ROOT))
    results = [
        run_ruff([service_rel]),
        run_pytest(args.service, ["app/tests"], f"Pytest {args.service}"),
    ]
    if args.mypy and args.files:
        py_files = [f for f in args.files if f.endswith(".py")]
        results.append(run_mypy(py_files))
    return summary(results)

def full(args: argparse.Namespace) -> int:
    results: list[tuple[bool, bool]] = []

    # Explicitly rare/manual mode: broad Ruff + all backend services + frontend.
    ruff_result = run_ruff(["backend/"])
    results.append(ruff_result)
    if args.fail_fast and not ruff_result[0]:
        return summary(results)

    for service in SERVICE_DIRS:
        result = run_pytest(service, ["app/tests"], f"Pytest {service}")
        results.append(result)
        if args.fail_fast and not result[0]:
            return summary(results)

    results.append(run_frontend_tests([]))
    if args.build:
        results.append(run_frontend_build())

    return summary(results)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Low-noise, CI-delegated validation for RAGForge agents."
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("doctor")

    p_focused = sub.add_parser("focused", aliases=["fast"])
    p_focused.add_argument("service", choices=[*SERVICE_DIRS, "frontend"])
    p_focused.add_argument("--files", nargs="*", default=[])
    p_focused.add_argument("--tests", nargs="*", default=[])
    p_focused.add_argument("--mypy", action="store_true")

    p_affected = sub.add_parser("affected", aliases=["service"])
    p_affected.add_argument("service", choices=[*SERVICE_DIRS, "frontend"])
    p_affected.add_argument("--files", nargs="*", default=[])
    p_affected.add_argument("--mypy", action="store_true")
    p_affected.add_argument("--build", action="store_true")

    p_full = sub.add_parser("full")
    p_full.add_argument("--fail-fast", action="store_true")
    p_full.add_argument("--build", action="store_true")

    args = parser.parse_args()

    if args.mode == "doctor":
        return doctor()
    if args.mode in {"focused", "fast"}:
        return focused(args)
    if args.mode in {"affected", "service"}:
        return affected(args)
    return full(args)

if __name__ == "__main__":
    raise SystemExit(main())
