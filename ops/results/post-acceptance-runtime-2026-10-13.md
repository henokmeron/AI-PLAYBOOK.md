# Post-acceptance runtime work (2026-10-13)

Continuation from acceptance at `7072cab` / tip `534a891`. Did **not** re-download models or re-run successful Qwen smoke suites.

## Inspection (VERIFIED)

| Item | Result |
| --- | --- |
| Global Volume | Mounted `fuse.geesefs` at `/workspace` |
| GPU | A100 80GB PCIe, ~71 GiB used by Qwen |
| Ports | `:8002`/`:8013`/`:8083` up; `:8000`/`:8010`/`:8080` down |
| Model dirs | Gemma + Qwen configs present (unchanged) |
| Source snapshots | `7072cab…` and `534a891…` archives present |
| Gemma archive | `vllm-clean-env.tar.zst` — `sha256sum -c` **OK**, `zstd -t` **OK** (~3.4G → ~8.4G) |
| Qwen `/tmp` env | Present (~9.5G) before archive |

## Qwen runtime archive (VERIFIED)

| Item | Value |
| --- | --- |
| Path | `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` |
| Size | ~3.8G |
| Companion | `SHA256SUMS`, `requirements-frozen.txt`, `runtime-manifest.txt`, `vllm-version.txt` (`0.32.0rc1.dev62+g624a5ddaf`) |
| Method | `ops/archive-qwen-runtime.sh` streamed tar+zstd to volume; refused overwrite; excluded key/pem/.env patterns |
| Live impact | Qwen kept serving (`:8002` still up after archive) |
| Restore helper | `ops/restore-qwen-runtime.sh` (**PREPARED**; not exercised — target already exists) |

## Gemma runtime restore (VERIFIED extract only)

| Step | Result |
| --- | --- |
| Integrity | `SHA256SUMS` OK + `zstd -t` OK |
| Extract | `scripts/restore-vllm-environment.sh` → `/tmp/vllm-clean-env` |
| Checks | vLLM **0.31.0**; Torch CUDA available; GPU name A100 |
| Started Gemma? | **No** (by design) |
| Qwen after extract | Still up |

## Switching procedure (PREPARED)

- `ops/switch-gpu-model.sh` now dry-runs unless `SWITCH_CONFIRM=yes`
- Runbook: `docs/one-gpu-model-switch.md`
- Live switch **not executed** (needs approval — would stop Qwen answers)

## Console model picker (PREPARED ONLY)

- Design: `docs/console-model-picker-design.md`
- No UI/code change to main or isolated console in this pass

## Blocked / not claimed complete

- Production default still Gemma
- Main services not restored/tested end-to-end
- Live GPU switch not performed
- Qwen archive restore-test (extract into empty `/tmp`) not performed
- Cold-start Pod recreation still unverified

## Single safest next action

See operator message: approval to **stop Qwen and start Gemma on `:8000` only** (still not main `:8010`/`:8080` until a second approval), **or** leave Qwen running and **stop the Pod** when finished to halt GPU charges.
