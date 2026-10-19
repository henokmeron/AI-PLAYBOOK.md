"""Release package checks. No Pod, no network, no model weights."""
from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from ops.release.package import ReleaseError, path_is_safe, sha256_file, verify_archive
from ops.release.pre_shutdown import checkpoint_status


def _archive(path: Path, names: dict[str, bytes]) -> str:
    with tarfile.open(path, "w:gz") as tar:
        for name, payload in names.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


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

    def test_shutdown_status_requires_a_verified_volume_copy(self) -> None:
        self.assertEqual(checkpoint_status(True, True), "READY_TO_SHUTDOWN")
        self.assertEqual(checkpoint_status(True, False), "BLOCKED")
        self.assertEqual(checkpoint_status(False, False), "NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
