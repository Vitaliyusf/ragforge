#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_FAILURE_LINES = 120

SERVICE_DIRS = {
    "rag": ROOT / "backend" / "rag",
    "gateway": ROOT / "backend" / "gateway",
    "files": ROOT / "backend" / "files",
    "embedding": ROOT / "backend" / "embedding",
    "vector_db": ROOT / "backend" / "vector_db",
    "memory": ROOT / "backend" / "memory",
    "llm_agent": ROOT / "backend" / "llm_agent",
}

def venv_python() -> Path | None:
    for candidate in (
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return None

def python_cmd() -> str:
    return str(venv_python() or Path(sys.executable))

def run_check(name: str, cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> bool:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if proc.returncode == 0:
        print(f"{name}: PASS")
        return True

    print(f"{name}: FAIL")
    lines = (proc.stdout or "").splitlines()
    for line in lines[-MAX_FAILURE_LINES:]:
        print(line)
    return False

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

def run_ruff(targets: list[str]) -> bool:
    return run_check(
        "Ruff",
        python_module("ruff", "check", *targets, "--quiet"),
        ROOT,
    )

def run_mypy(files: list[str]) -> bool:
    return run_check(
        "Mypy",
        python_module(
            "mypy",
            *files,
            "--config-file",
            str(ROOT / "mypy.ini"),
            "--follow-imports=skip",
        ),
        ROOT,
    )

def run_pytest(service: str, tests: list[str] | None, label: str) -> bool:
    service_dir = SERVICE_DIRS[service]
    targets = tests or ["app/tests"]
    return run_check(
        label,
        python_module(
            "pytest",
            *targets,
            "-q",
            "--disable-warnings",
            "--maxfail=1",
        ),
        service_dir,
        service_env(service_dir),
    )

def run_frontend(build: bool) -> bool:
    npm = shutil.which("npm")
    if not npm:
        print("Frontend tests: FAIL")
        print("npm was not found on PATH")
        return False

    ok = run_check("Frontend tests", [npm, "test"], ROOT / "frontend")
    if ok and build:
        ok = run_check("Frontend build", [npm, "run", "build"], ROOT / "frontend")
    return ok

def run_fast(args: argparse.Namespace) -> int:
    ok = True

    if args.service == "frontend":
        ok &= run_frontend(build=False)
        print("Overall:", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    files = args.files or []
    py_files = [f for f in files if f.endswith(".py")]

    if files:
        ok &= run_ruff(files)
    else:
        print("Ruff: SKIP (no changed files supplied)")

    if args.mypy:
        if py_files:
            ok &= run_mypy(py_files)
        else:
            print("Mypy: SKIP (no Python files supplied)")

    ok &= run_pytest(args.service, args.tests, "Pytest focused")

    print("Overall:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def run_service(args: argparse.Namespace) -> int:
    if args.service == "frontend":
        ok = run_frontend(build=args.build)
        print("Overall:", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    ok = True
    service_rel = str(SERVICE_DIRS[args.service].relative_to(ROOT))
    ok &= run_ruff([service_rel])
    ok &= run_pytest(args.service, None, f"Pytest {args.service}")

    if args.mypy:
        py_files = [f for f in (args.files or []) if f.endswith(".py")]
        if py_files:
            ok &= run_mypy(py_files)
        else:
            print("Mypy: SKIP (no Python files supplied)")

    print("Overall:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def run_full(args: argparse.Namespace) -> int:
    ok = run_ruff(["backend/"])
    if not ok and args.fail_fast:
        print("Overall: FAIL")
        return 1

    for service in SERVICE_DIRS:
        service_ok = run_pytest(service, None, f"Pytest {service}")
        ok &= service_ok
        if not service_ok and args.fail_fast:
            print("Overall: FAIL")
            return 1

    frontend_ok = run_frontend(build=True)
    ok &= frontend_ok

    print("Overall:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Low-noise progressive validation for RAGForge agents."
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    fast = sub.add_parser("fast")
    fast.add_argument("service", choices=[*SERVICE_DIRS, "frontend"])
    fast.add_argument("--files", nargs="*", default=[])
    fast.add_argument("--tests", nargs="*", default=None)
    fast.add_argument("--mypy", action="store_true")

    service = sub.add_parser("service")
    service.add_argument("service", choices=[*SERVICE_DIRS, "frontend"])
    service.add_argument("--files", nargs="*", default=[])
    service.add_argument("--mypy", action="store_true")
    service.add_argument("--build", action="store_true")

    full = sub.add_parser("full")
    full.add_argument("--fail-fast", action="store_true")

    args = parser.parse_args()

    if args.mode == "fast":
        return run_fast(args)
    if args.mode == "service":
        return run_service(args)
    return run_full(args)

if __name__ == "__main__":
    raise SystemExit(main())
