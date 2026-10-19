"""Build and check a source release from one Git commit.

The package is a git archive plus a manifest. It does not contain model
weights, virtual environments, secrets, or the Pod runtime.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Iterable

REQUIRED_PATHS = (
    "web/server.py",
    "ops/release/START.sh",
    "ops/release/deploy-console-only.sh",
    "ops/release/snapshot-published-tip.sh",
    "ops/release/package.py",
    "ops/release/make_release.py",
    "ops/release/recover.py",
    "ops/release/pre_shutdown.py",
    "integrations/endpoint_worker.py",
    "docs/first-release-recovery.md",
    "docs/windows-repair/endpoint-agent.md",
    "docs/release/RECOVERY.md",
)

MODEL_NOTE = {
    "name": "Qwen3.5-27B",
    "revision": "fc05daec18b0a78c049392ed2e771dde82bdf654",
    "volume_path": "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654",
    "included_in_package": False,
    "reason": "Weights stay on the RunPod volume. This package does not download them.",
}


class ReleaseError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_is_safe(name: str) -> bool:
    if not name or name.startswith(("/", "\\")):
        return False
    parts = Path(name).parts
    return ".." not in parts and not any(part.endswith(":") for part in parts)


def archive_names(archive: Path) -> list[str]:
    with tarfile.open(archive, "r:gz") as tar:
        names = []
        for member in tar.getmembers():
            if not path_is_safe(member.name):
                raise ReleaseError(f"archive path is not safe: {member.name}")
            names.append(member.name)
    return names


def verify_archive(archive: Path, expected_sha256: str, required: Iterable[str] = REQUIRED_PATHS) -> None:
    actual = sha256_file(archive)
    if not hmac.compare_digest(actual, expected_sha256):
        raise ReleaseError("archive checksum does not match")
    names = set(archive_names(archive))
    missing = [item for item in required if item not in names]
    if missing:
        raise ReleaseError("archive is missing required files: " + ", ".join(missing))


def extract_archive(archive: Path, destination: Path, expected_sha256: str) -> None:
    verify_archive(archive, expected_sha256)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ReleaseError("destination is not empty")
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not path_is_safe(member.name):
                raise ReleaseError(f"archive path is not safe: {member.name}")
        tar.extractall(destination)


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleaseError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def dirty_entries(repo: Path) -> list[str]:
    lines = [line for line in git_output(repo, "status", "--porcelain").splitlines() if line]
    dirty = []
    for line in lines:
        path = line[3:].replace("\\", "/")
        if path.rstrip("/").endswith("__pycache__") or path.endswith(".pyc"):
            continue
        dirty.append(line)
    return dirty


def default_release_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "AI-PLAYBOOK" / "releases"


def build_manifest(commit: str, archive_name: str, checksum: str, tests: list[str]) -> dict:
    return {
        "release_id": commit,
        "commit": commit,
        "branch": "main",
        "archive": archive_name,
        "sha256": checksum,
        "required_paths": list(REQUIRED_PATHS),
        "tests_recorded": tests,
        "model": MODEL_NOTE,
        "dependencies": {
            "python": "The Pod runtime archive /workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst. No pip lock file is in this repository.",
            "pinned_in_git": False,
        },
        "secrets_included": False,
        "persistent_volume_copy": "not verified by this manifest",
        "startup_order": ["Qwen :8002", "gateway :8010", "console :8080"],
        "health_checks": [
            "http://127.0.0.1:8002/health",
            "http://127.0.0.1:8010/health",
            "http://127.0.0.1:8080/api/status",
        ],
    }


def write_manifest(path: Path, manifest: dict) -> str:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)
