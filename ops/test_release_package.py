"""Release package checks. No Pod, no network, no model weights."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from ops.release.package import (
    ReleaseError,
    git_executable,
    path_is_safe,
    read_checksum_sidecar,
    sha256_file,
    verify_archive,
    write_checksum_sidecar,
)
from ops.release.pre_shutdown import checkpoint_status
from ops.release.source_update import SourceUpdateRefusal, acceptance, plan_fast_forward
from ops.release.volume_transfer import plan_volume_transfer


def _archive(path: Path, names: dict[str, bytes]) -> str:
    with tarfile.open(path, "w:gz") as tar:
        for name, payload in names.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _special_archive(path: Path, *, member_type: bytes, name: str, target: str) -> str:
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.type = member_type
        info.linkname = target
        tar.addfile(info)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleasePackageTests(unittest.TestCase):
    def test_checksum_and_required_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "release.tar.gz"
            digest = _archive(archive, {"web/server.py": b"print(1)\n"})
            self.assertEqual(sha256_file(archive), digest)
            verify_archive(archive, digest, required=("web/server.py",))
            with self.assertRaises(ReleaseError):
                verify_archive(archive, "0" * 64, required=("web/server.py",))
            with self.assertRaises(ReleaseError):
                verify_archive(archive, digest, required=("missing.py",))

    def test_parent_path_is_rejected(self) -> None:
        self.assertFalse(path_is_safe("../secret"))
        self.assertFalse(path_is_safe("/etc/passwd"))
        self.assertTrue(path_is_safe("ops/release/START.sh"))
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.tar.gz"
            digest = _archive(archive, {"../secret": b"no\n"})
            with self.assertRaises(ReleaseError):
                verify_archive(archive, digest, required=())

    def test_windows_path_forms_are_rejected_cross_platform(self) -> None:
        for path in (
            r"C:\\Windows\\system.ini",
            r"C:relative\\secret.txt",
            r"file.txt:alternate-stream",
            r"folder\\..\\secret.txt",
            r"\\\\server\\share\\secret.txt",
        ):
            with self.subTest(path=path):
                self.assertFalse(path_is_safe(path))
        self.assertTrue(path_is_safe(r"ops\\release\\START.sh"))

    def test_archive_links_are_rejected_before_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                archive = Path(tmp) / ("link-" + str(kind[0]) + ".tar.gz")
                digest = _special_archive(
                    archive,
                    member_type=kind,
                    name="release/redirect",
                    target="../../outside",
                )
                with self.subTest(member_type=kind):
                    with self.assertRaises(ReleaseError):
                        verify_archive(archive, digest, required=())

    def test_git_executable_prints_a_version(self) -> None:
        previous = os.environ.get("AI_PLAYBOOK_GIT")
        os.environ["AI_PLAYBOOK_GIT"] = str(Path(tempfile.gettempdir()) / "missing-git.exe")
        try:
            exe = git_executable()
        finally:
            if previous is None:
                os.environ.pop("AI_PLAYBOOK_GIT", None)
            else:
                os.environ["AI_PLAYBOOK_GIT"] = previous
        result = subprocess.run([exe, "--version"], check=False, capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0)
        self.assertIn("git version", result.stdout.lower())

    def test_source_update_never_restarts_a_process(self) -> None:
        self.assertEqual(
            plan_fast_forward(clean=True, is_ancestor=True, same_commit=False),
            "fast-forward-source-only",
        )
        self.assertEqual(
            plan_fast_forward(clean=True, is_ancestor=False, same_commit=True),
            "already-current",
        )
        with self.assertRaises(SourceUpdateRefusal):
            plan_fast_forward(clean=False, is_ancestor=True, same_commit=False)
        with self.assertRaises(SourceUpdateRefusal):
            plan_fast_forward(clean=True, is_ancestor=False, same_commit=False)
        with self.assertRaises(SourceUpdateRefusal):
            plan_fast_forward(
                clean=True,
                is_ancestor=True,
                same_commit=False,
                origin_url="https://example.invalid/other.git",
            )
        self.assertEqual(
            acceptance(before="aaa", after="bbb", published="bbb"),
            "acceptance: aaa -> bbb; health URLs were not called",
        )
        with self.assertRaises(SourceUpdateRefusal):
            acceptance(before="aaa", after="bbb", published="ccc")
        script = Path("ops/release/update-source-only.sh").read_text(encoding="utf-8")
        self.assertIn("https://github.com/henokmeron/AI-PLAYBOOK.md.git", script)
        self.assertNotIn("kill ", script)
        self.assertNotIn("START.sh", script)
        self.assertLess(script.index("remote get-url"), script.index("\ngit fetch origin"))
        self.assertLess(script.index("\ngit fetch origin"), script.index("\ngit merge --ff-only"))
        snapshot = Path("ops/release/snapshot-published-tip.sh").read_text(encoding="utf-8")
        self.assertLess(snapshot.index("VOLUME_COPY_APPROVED"), snapshot.index("mkdir -p"))
        self.assertIn("rollback:", snapshot)
        self.assertNotIn("kill ", snapshot)

    def test_checksum_sidecar_is_outside_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "release.tar.gz"
            digest = _archive(archive, {"ops/release/START.sh": b"echo ok\n"})
            sidecar = write_checksum_sidecar(root, archive.name, digest)
            self.assertEqual(read_checksum_sidecar(sidecar), digest)
            self.assertFalse(sidecar.name.endswith(".tar.gz"))
            with self.assertRaises(ReleaseError):
                write_checksum_sidecar(root, archive.name, "abc")

    def test_volume_transfer_plan_never_copies(self) -> None:
        digest = "a" * 64
        dry = plan_volume_transfer(
            approved=False,
            local_sha256=digest,
            destination_name="AI-PLAYBOOK.md-runpod-first-abc1234.tar.gz",
        )
        self.assertEqual(dry["action"], "dry-run")
        self.assertFalse(dry["copied"])
        approved = plan_volume_transfer(
            approved=True,
            local_sha256=digest,
            destination_name="AI-PLAYBOOK.md-runpod-first-abc1234.tar.gz",
        )
        self.assertEqual(approved["action"], "approved-plan")
        self.assertFalse(approved["copied"])
        self.assertIn("older snapshot", approved["rollback"])
        refused = plan_volume_transfer(
            approved=True,
            local_sha256=digest,
            destination_name="already.tar.gz",
            existing_names=("already.tar.gz",),
        )
        self.assertEqual(refused["action"], "refused")
        self.assertFalse(refused["copied"])

    def test_shutdown_status_requires_a_verified_volume_copy(self) -> None:
        self.assertEqual(checkpoint_status(True, True), "READY_TO_SHUTDOWN")
        self.assertEqual(checkpoint_status(True, False), "BLOCKED")
        self.assertEqual(checkpoint_status(False, False), "NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
