from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import tomllib
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a checked-out private ARGUS source tag without executing it."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return tomllib.load(file)


def nested_version(data: dict[str, object], section: str | None = None) -> str:
    selected = data if section is None else data[section]
    if not isinstance(selected, dict) or not isinstance(selected.get("version"), str):
        raise RuntimeError("Manifest is missing a string version.")
    return selected["version"]


def read_python_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise RuntimeError(f"{path} is missing a literal __version__ assignment.")


def tauri_override_versions(source: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    config_root = source / "app" / "src-tauri"
    base_config = config_root / "tauri.conf.json"
    for path in sorted(config_root.glob("tauri*.conf.*")):
        if path == base_config:
            continue
        if path.suffix == ".json":
            data = read_json(path)
        elif path.suffix == ".toml":
            data = read_toml(path)
        else:
            raise RuntimeError(
                f"Unsupported Tauri overlay {path.name}; use JSON or TOML so releases "
                "can validate version overrides."
            )
        if not isinstance(data, dict):
            raise RuntimeError(f"Tauri overlay {path.name} is not an object.")
        if "version" not in data:
            continue
        version = data["version"]
        if not isinstance(version, str):
            raise RuntimeError(f"Tauri overlay {path.name} has a non-string version.")
        versions[str(path.relative_to(source))] = version
    return versions


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    versions = {
        "pyproject.toml": nested_version(read_toml(source / "pyproject.toml"), "project"),
        "app/package.json": nested_version(read_json(source / "app" / "package.json")),
        "app/package-lock.json": nested_version(
            read_json(source / "app" / "package-lock.json")
        ),
        "app/src-tauri/Cargo.toml": nested_version(
            read_toml(source / "app" / "src-tauri" / "Cargo.toml"), "package"
        ),
        "app/src-tauri/tauri.conf.json": nested_version(
            read_json(source / "app" / "src-tauri" / "tauri.conf.json")
        ),
        "src/argus/__init__.py": read_python_version(
            source / "src" / "argus" / "__init__.py"
        ),
    }
    versions.update(tauri_override_versions(source))
    distinct = set(versions.values())
    if len(distinct) != 1:
        details = ", ".join(f"{path}={version}" for path, version in versions.items())
        raise RuntimeError(f"Release versions do not match: {details}")

    version = distinct.pop()
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
        version,
    ):
        raise RuntimeError(f"Application version {version!r} is not strict SemVer.")
    if args.tag != f"v{version}":
        raise RuntimeError(f"Tag {args.tag} does not match application version {version}.")
    source_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise RuntimeError("Private source checkout did not resolve to a full commit SHA.")

    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")
        output.write(f"tag={args.tag}\n")
        output.write(f"source_sha={source_sha}\n")
    print(f"Validated ARGUS {args.tag} at source commit {source_sha[:12]}.")


if __name__ == "__main__":
    main()
