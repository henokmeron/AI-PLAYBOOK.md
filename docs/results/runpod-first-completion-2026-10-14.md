# RunPod-first completion report — 2026-10-14

## 1. Branch and commit

- Branch: `feature/qwen3.5-27b-integration`
- Base tip before this finish pass: `d748762`
- Final commit: see Git tip after this report lands (recorded in volume `VERSION.txt` and snapshot name)

## 2. Qwen as default

- Registry `production` / `defaults.active_model_id`: `qwen3.5-27b`
- Revision: `fc05daec18b0a78c049392ed2e771dde82bdf654`
- Gateway health `default_model_id`: `qwen3.5-27b`
- Label: **VERIFIED**

## 3. Live E2E (chat, selection, Document Q&A)

Targeted re-run of `ops/_pod_e2e_verify.py` on the live H100 NVL Pod (services already up; no Qwen re-download). `FAILS: NONE`.

| Check | Result |
| --- | --- |
| Chat `PLATFORM_OK` | **VERIFIED** |
| Model catalogue Qwen default | **VERIFIED** |
| Gemma while Qwen live → HTTP 409 | **VERIFIED** |
| Document upload / ask / delete | **VERIFIED** |
| Empty collection abstain | **VERIFIED** |
| Console `/api/status` ready | **VERIFIED** |
| Idempotent `start-first-release.sh --start` reuses ports | **VERIFIED** |

Browser UI via SSH tunnel on the operator laptop: **NOT TESTED** in this finish pass (loopback console/API on the Pod was verified).

## 4. RunPod-only (no Azure required)

- No Azure imports in `.py` / `.sh` / `.js` runtime paths: **VERIFIED**
- Startup scripts do not call Azure APIs: **VERIFIED**
- Azure docs marked optional/deferred: **VERIFIED** (this change set)
- Label: **VERIFIED** — first release operates without Azure

## 5. Persistent storage and recovery

| Item | Result |
| --- | --- |
| `/workspace` is `fuse.geesefs` Global Volume | **VERIFIED** |
| `START.sh` present | **VERIFIED** |
| Qwen model path + 11 shards | **VERIFIED** |
| Archive `vllm-qwen-env.tar.zst` + `sha256sum -c` + `zstd -t` | **VERIFIED** |
| Live env on `/tmp` only | **VERIFIED** |
| Idempotent `--check` / reuse healthy ports | **VERIFIED** |
| Fresh empty-Pod recovery drill (second Pod) | **NOT TESTED** (cost control; no second Pod) |

## 6. Tests run

- `ops/start-first-release.sh --check`
- Archive checksum verification
- `ops/_pod_e2e_verify.py` (targeted live)

## 7. Snapshot

Filled at ship time under `/workspace/ai-platform-backups/source-snapshots/`.

## 8. Services and ports

| Service | Port | State at inspection |
| --- | --- | --- |
| Qwen vLLM | 8002 | up |
| Gateway | 8010 | up |
| Console | 8080 | up |
| Gemma | 8000 | down (expected) |

## 9. Remaining blockers

- None for first-release RunPod operation.
- Fresh-Pod cold restore remains **NOT TESTED** (would need a second Pod or a deliberate stop/start of this Pod after `/tmp` wipe).
- Full browser console click-through depends on a local SSH tunnel (`18080`).

## 10. GPU stop safety

**VERIFIED (procedure):** Stop the paid Pod in RunPod UI to halt GPU compute charges; keep the Global Volume so weights/archives/docs/release folder remain. Storage fees may continue. Do not delete the volume. Restart later with `bash /workspace/ai-platform-release/START.sh`.
