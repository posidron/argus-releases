from __future__ import annotations

import os
from pathlib import Path

from run_quiet import run_quiet


TARGETS = {
    "aarch64-apple-darwin": "dmg",
    "x86_64-apple-darwin": "dmg",
    "x86_64-pc-windows-msvc": "nsis,msi",
}


def main() -> None:
    target = os.environ.get("ARGUS_TARGET", "")
    bundles = os.environ.get("ARGUS_BUNDLES", "")
    if target not in TARGETS or bundles != TARGETS[target]:
        raise RuntimeError("Release target or bundle selection is invalid.")

    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    source = workspace / "source"
    logs = Path(os.environ["RUNNER_TEMP"]) / "argus-private-logs"
    commands = [
        (
            "Python dependency installation",
            ["uv", "sync", "--frozen", "--group", "build"],
        ),
        (
            "Frontend dependency installation",
            ["npm", "ci", "--prefix", "app"],
        ),
        (
            "Native backend sidecar build",
            [
                "uv",
                "run",
                "--frozen",
                "--group",
                "build",
                "python",
                "scripts/build_sidecar.py",
                "--target",
                target,
            ],
        ),
        (
            "Native backend sidecar smoke test",
            [
                "uv",
                "run",
                "--frozen",
                "--group",
                "build",
                "python",
                "scripts/smoke_sidecar.py",
                "--target",
                target,
            ],
        ),
        (
            "Native Tauri installer build",
            [
                "npm",
                "--prefix",
                "app",
                "run",
                "tauri",
                "--",
                "build",
                "--target",
                target,
                "--bundles",
                bundles,
                "--config",
                "src-tauri/tauri.release.conf.json",
            ],
        ),
    ]
    for index, (label, command) in enumerate(commands, start=1):
        run_quiet(label, source, logs / f"{index:02d}.log", command)


if __name__ == "__main__":
    main()
