"""Plan a Global Volume source copy.

This module never writes `/workspace`, never copies an archive, and never
signals Qwen, the gateway, or the console. The Pod script
`ops/release/snapshot-published-tip.sh` is dry-run unless
`VOLUME_COPY_APPROVED=yes`.
"""
from __future__ import annotations

from ops.release.package import ReleaseError


def plan_volume_transfer(
    *,
    approved: bool,
    local_sha256: str,
    destination_name: str,
    existing_names: tuple[str, ...] = (),
) -> dict:
    digest = local_sha256.strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ReleaseError("local checksum is not sha256")
    plan = {
        "copied": False,
        "sha256": digest,
        "destination_name": destination_name,
        "preflight": (
            "require fuse.geesefs on /workspace and refuse when the destination "
            "archive or checksum file already exists"
        ),
        "verify": "read the new checksum file back and require the same sha256",
        "rollback": (
            "delete only the new incomplete archive and its checksum file; "
            "keep every older snapshot, the weights, and the runtime archive"
        ),
        "acceptance": (
            "the read-back digest matches; Qwen, the gateway, and the console "
            "are not signalled"
        ),
    }
    if destination_name in existing_names:
        plan["action"] = "refused"
        plan["reason"] = "destination already exists"
        return plan
    if not approved:
        plan["action"] = "dry-run"
        plan["reason"] = "VOLUME_COPY_APPROVED is not yes"
        return plan
    plan["action"] = "approved-plan"
    plan["reason"] = "the planner does not copy; the Pod script must be run only with approval"
    return plan
