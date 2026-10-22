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
from pathlib import Path, PurePosixPath, PureWindowsPath
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
    """Reject paths that can escape the destination on POSIX or Windows."""
    if not name or "\\x00" in name:
        return False
    windows_path = PureWindowsPath(name)
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or windows_path.is_absolute() or windows_path.drive:
        return False
    parts = PurePosixPath(normalized).parts
    # A colon can introduce a Windows drive or NTFS alternate data stream.
    return bool(parts) and ".." not in parts and not any(":" in part for part in parts)


def _validated_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Allow only regular files and directories; never extract links or special files."""
    members = tar.getmembers()
    for member in members:
        if not path_is_safe(member.name):
            raise ReleaseError(f"archive path is not safe: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise ReleaseError(f"archive member type is not allowed: {member.name}")
    return members


def archive_names(archive: Path) -> list[str]:
    with tarfile.open(archive, "r:gz") as tar:
        return [member.name for member in _validated_members(tar)]


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
    if destination.is_symlink():
        raise ReleaseError("destination must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ReleaseError("destination is not empty")
    with tarfile.open(archive, "r:gz") as tar:
        members = _validated_members(tar)
        # Links and special files are rejected above so extraction cannot redirect
        # a later member outside the destination through a symlink or hard link.
        tar.extractall(destination, members=members)


def git_executable() -> str:
    """Return a git binary that prints a version.

    ``git`` on Windows PATH can be a launcher that does not run. ``AI_PLAYBOOK_GIT``
    is checked first. Git config is not changed.
    """
    candidates: list[str] = []
    override = os.environ.get("AI_PLAYBOOK_GIT", "").strip()
    if override:
        candidates.append(override)
    candidates.append("git")
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        root = Path(local) / "GitHubDesktop"
        if root.is_dir():
            candidates.extend(
                str(path)
                for path in sorted(
                    root.glob("app-*/resources/app/git/mingw64/bin/git.exe"),
                    reverse=True,
                )
            )
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            result = subprocess.run(
                [candidate, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "git version" in (result.stdout or "").lower():
            return candidate
    raise ReleaseError("a working git executable was not found")


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [git_executable(), "-C", str(repo), *args],
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
        "checksum_file": f"{archive_name}.sha256",
        "persistent_volume_copy": "not verified by this manifest",
        "startup_order": ["Qwen :8002", "gateway :8010", "console :8080"],
        "health_checks": [
            "http://127.0.0.1:8002/health",
            "http://127.0.0.1:8010/health",
            "http://127.0.0.1:8080/api/status",
        ],
    }


def checksum_sidecar_name(archive_name: str) -> str:
    return f"{archive_name}.sha256"


def write_checksum_sidecar(directory: Path, archive_name: str, checksum: str) -> Path:
    """Write the digest beside the archive, never inside it."""
    digest = checksum.strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ReleaseError("checksum file requires a lowercase sha256 digest")
    path = directory / checksum_sidecar_name(archive_name)
    line = f"{digest}  {archive_name}\n"
    path.write_text(line, encoding="utf-8", newline="\n")
    if path.read_text(encoding="utf-8") != line:
        raise ReleaseError("checksum file read-back did not match")
    return path


def read_checksum_sidecar(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").split()
    if len(parts) < 2 or len(parts[0]) != 64:
        raise ReleaseError("checksum file is not a sha256 record")
    return parts[0]


def write_manifest(path: Path, manifest: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    read_back = json.loads(path.read_text(encoding="utf-8"))
    if read_back.get("sha256") != manifest.get("sha256"):
        raise ReleaseError("manifest read-back did not match the archive checksum")
    return sha256_file(path)
