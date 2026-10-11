# First successful Global Volume source snapshot — 2026-10-11

## Result

**PASS.** The user's RunPod terminal screenshot confirms that `ops/sync_global_volume.sh` completed and printed:

`SUCCESS: source snapshot and manifest saved on the mounted Global Volume.`

## Snapshot details

- Source repository: `henokmeron/AI-PLAYBOOK.md`
- Source commit captured: `404dad8e59363ff7882b0cbb05bae1640e1e3d1a`
- Persistent archive:
  `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.tar.gz`
- Persistent manifest:
  `/workspace/ai-platform-backups/manifests/global-volume-manifest-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.txt`
- Source-commit metadata:
  `/workspace/ai-platform-backups/manifests/source-commit-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.json`

The screenshot shows the repository archive checksum passed `sha256sum -c`. It also shows the source commit, archive path, manifest path and existing runtime/model backup directories.

## Storage scope

- Global Volume: versioned committed source snapshot, manifest, runtime inventory and existing persistent assets.
- Existing runtime backups remain under `/workspace/runtime-setup`.
- Model files remain under `/workspace/gemma-4-31B-it`.
- Temporary `/tmp` working files remain temporary and are not the persistent copy.
- Azure remains the independent model backup.

## Important boundary

This archive captures the committed GitHub state at the commit listed above. Changes committed after that SHA are not part of this snapshot. After updating the playbook with this success record, run the sync script once more so the next snapshot includes the record itself.

## Ongoing rule

After each meaningful code/configuration/runtime milestone: commit source, tests and docs to GitHub; run the relevant tests; run `ops/sync_global_volume.sh`; verify the archive checksum and manifest. Never copy temporary API keys or secrets into the source snapshot.
