from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


TAG_REF = re.compile(
    r"refs/tags/v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
COMMIT_REF = re.compile(r"[0-9a-f]{40}")
REPOSITORY = "posidron/argus-command-center"


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required checkout setting {name}.")
    return value


def run_git(
    arguments: list[str],
    *,
    environment: dict[str, str],
    log,
) -> None:
    result = subprocess.run(
        ["git", *arguments],
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Private source checkout failed.")


def main() -> None:
    reference = required("ARGUS_PRIVATE_REF")
    if not (TAG_REF.fullmatch(reference) or COMMIT_REF.fullmatch(reference)):
        raise RuntimeError("Private source ref must be a qualified release tag or commit SHA.")

    workspace = Path(required("GITHUB_WORKSPACE")).resolve()
    destination = Path(required("ARGUS_PRIVATE_DESTINATION")).resolve()
    if destination.parent != workspace:
        raise RuntimeError("Private source destination must be a direct workspace child.")

    runner_temp = Path(required("RUNNER_TEMP")).resolve()
    known_hosts = Path(required("ARGUS_KNOWN_HOSTS")).resolve()
    if not known_hosts.is_file():
        raise RuntimeError("Pinned GitHub SSH host keys are unavailable.")

    key_path = runner_temp / f"argus-deploy-{os.getpid()}.key"
    hooks_path = runner_temp / f"argus-empty-hooks-{os.getpid()}"
    log_path = runner_temp / f"argus-checkout-{os.getpid()}.log"
    hooks_path.mkdir(parents=True, exist_ok=True)
    key_path.write_text(required("ARGUS_DEPLOY_KEY").rstrip() + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    shutil.rmtree(destination, ignore_errors=True)

    environment = os.environ.copy()
    for name in (
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "ARGUS_ARTIFACT_PRIVATE_KEY",
        "ARGUS_DEPLOY_KEY",
        "GH_TOKEN",
        "GITHUB_ENV",
        "GITHUB_OUTPUT",
        "GITHUB_PATH",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_TOKEN",
        "SSH_AUTH_SOCK",
    ):
        environment.pop(name, None)
    key = key_path.as_posix()
    hosts = known_hosts.as_posix()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": (
                f'ssh -i "{key}" -o UserKnownHostsFile="{hosts}" '
                "-o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o LogLevel=ERROR "
                "-o ControlMaster=no -o ControlPath=none -o ControlPersist=no"
            ),
        }
    )

    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            run_git(["init", "--quiet", str(destination)], environment=environment, log=log)
            run_git(
                ["-C", str(destination), "config", "core.hooksPath", str(hooks_path)],
                environment=environment,
                log=log,
            )
            run_git(
                [
                    "-C",
                    str(destination),
                    "remote",
                    "add",
                    "origin",
                    f"git@github.com:{REPOSITORY}.git",
                ],
                environment=environment,
                log=log,
            )
            run_git(
                [
                    "-C",
                    str(destination),
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "--no-tags",
                    "origin",
                    reference,
                ],
                environment=environment,
                log=log,
            )
            if os.environ.get("ARGUS_METADATA_ONLY") == "true":
                run_git(
                    [
                        "-C",
                        str(destination),
                        "sparse-checkout",
                        "init",
                        "--no-cone",
                    ],
                    environment=environment,
                    log=log,
                )
                run_git(
                    [
                        "-C",
                        str(destination),
                        "sparse-checkout",
                        "set",
                        "pyproject.toml",
                    ],
                    environment=environment,
                    log=log,
                )
            run_git(
                [
                    "-C",
                    str(destination),
                    "-c",
                    "advice.detachedHead=false",
                    "checkout",
                    "--quiet",
                    "--detach",
                    "FETCH_HEAD",
                ],
                environment=environment,
                log=log,
            )
            source_sha = subprocess.run(
                ["git", "-C", str(destination), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout.strip()
        if COMMIT_REF.fullmatch(reference) and source_sha != reference:
            raise RuntimeError("Private source checkout resolved to the wrong commit.")
        print(f"Checked out private source at {source_sha[:12]}.")
    finally:
        key_path.unlink(missing_ok=True)
        shutil.rmtree(hooks_path, ignore_errors=True)
        log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
