"""Origin and fast-forward parity. These tests do not push or contact the pod."""
from __future__ import annotations

import unittest
from pathlib import Path

from ops.git_parity import (
    EXPECTED_ORIGIN,
    ParityError,
    check_repo,
    parse_ls_remote,
    parse_remote_v,
    refuse_force,
    require_matching_refs,
    require_origin,
)

GOOD_REMOTE = (
    "origin\thttps://github.com/henokmeron/AI-PLAYBOOK.md.git (fetch)\n"
    "origin\thttps://github.com/henokmeron/AI-PLAYBOOK.md.git (push)\n"
)
SHA = "4ee02bd843a8e40d59f8121e09c0b81bdabe7648"
OTHER = "a05e17715a045c538c92bfce72181bdb1a9fae6c"


class GitParityTests(unittest.TestCase):
    def test_origin_must_be_exact(self) -> None:
        require_origin(GOOD_REMOTE)
        rows = parse_remote_v(GOOD_REMOTE)
        self.assertEqual(rows[0][1], EXPECTED_ORIGIN)
        with self.assertRaises(ParityError):
            require_origin(
                "origin\thttps://github.com/other/AI-PLAYBOOK.md.git (fetch)\n"
                "origin\thttps://github.com/other/AI-PLAYBOOK.md.git (push)\n"
            )
        with self.assertRaises(ParityError):
            require_origin("origin https://github.com/henokmeron/AI-PLAYBOOK.md.git (fetch)\n")

    def test_published_refs_must_share_one_sha(self) -> None:
        text = (
            f"{SHA}\tHEAD\n"
            f"{SHA}\trefs/heads/main\n"
            f"{SHA}\trefs/heads/feature/qwen-a100-start-hardening\n"
            f"{SHA}\trefs/heads/feature/qwen3.5-27b-integration\n"
        )
        self.assertEqual(require_matching_refs(parse_ls_remote(text)), SHA)
        drifted = text.replace(
            f"{SHA}\trefs/heads/feature/qwen3.5-27b-integration",
            f"{OTHER}\trefs/heads/feature/qwen3.5-27b-integration",
        )
        with self.assertRaises(ParityError):
            require_matching_refs(parse_ls_remote(drifted))
        with self.assertRaises(ParityError):
            parse_ls_remote("not-a-sha\trefs/heads/main\n")

    def test_force_push_is_refused(self) -> None:
        refuse_force(["push", "origin", "main"])
        for flag in ("--force", "-f", "--force-with-lease", "+main"):
            with self.assertRaises(ParityError):
                refuse_force(["push", flag])

    def test_this_checkout_origin_matches_without_network(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual(check_repo(repo, ls_remote=False), "origin-ok")


if __name__ == "__main__":
    unittest.main()
