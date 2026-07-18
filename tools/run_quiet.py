from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a private-source command without publishing its output."
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def run_quiet(label: str, cwd: Path, log_path: Path, command: list[str]) -> None:
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(f"{label} executable is unavailable.")
    resolved_command = [executable, *command[1:]]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    for name in (
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "GH_TOKEN",
        "GITHUB_ENV",
        "GITHUB_OUTPUT",
        "GITHUB_PATH",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_TOKEN",
        "SSH_AUTH_SOCK",
    ):
        environment.pop(name, None)

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(
            resolved_command,
            cwd=cwd,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if result.returncode != 0:
        print(f"::error::{label} failed with exit code {result.returncode}.")
        raise SystemExit(result.returncode)
    print(f"{label} completed.")


def main() -> None:
    args = parse_args()
    run_quiet(args.label, args.cwd, args.log, args.command)


if __name__ == "__main__":
    main()
