# One-GPU model switching procedure (prepared)

**Status:** procedure prepared; live switch **not executed** without operator approval.  
**Production default:** remains `gemma-4-31b-it` in `models/registry.yaml`.

## Why this exists

The Pod has a single GPU. Gemma (`:8000`) and Qwen (`:8002`) must not load together. Gateways refuse cross-runtime model ids with HTTP 409 instead of silently remapping.

## Preconditions (verify every time)

1. Global Volume mounted at `/workspace` (`findmnt` + Gemma `config.json` marker).
2. Both weight trees present (do not re-download if complete):
   - Gemma: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it`
   - Qwen: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`
3. Runtime archives present:
   - Gemma: `/workspace/runtime-setup/vllm-clean-env.tar.zst` (+ `SHA256SUMS`)
   - Qwen: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (+ `SHA256SUMS`)
4. Enough free space on `/tmp` (≥12 GiB) before any restore.
5. Operator approval if stopping a live serving model (stops answers; GPU billing continues until Pod stop).

## Dry-run (safe, no changes)

```bash
bash ops/switch-gpu-model.sh gemma --dry-run
bash ops/switch-gpu-model.sh qwen --dry-run
```

## Switch to Gemma (reversible outline)

1. Dry-run and confirm Qwen is the process holding VRAM.
2. **Approval required** to stop Qwen.
3. `SWITCH_CONFIRM=yes bash ops/switch-gpu-model.sh gemma`  
   (stops `:8002` only; does **not** auto-start Gemma or main ports).
4. If `/tmp/vllm-clean-env` missing: `bash scripts/restore-vllm-environment.sh`  
   (checksum + `zstd -t` + extract; refuses overwrite).
5. Start Gemma on `:8000` using the recovery runbook command (PATH includes env `bin`).
6. **Separate approval** to start main gateway `:8010` and console `:8080`.
7. Smoke: `/v1/models`, authenticated chat, optional Document Q&A.

## Switch to Qwen (reversible outline)

1. Dry-run; confirm Gemma down or approved to stop.
2. **Approval required** to stop Gemma `:8000` if up.
3. Ensure `/tmp/vllm-qwen-env` (live) or `bash ops/restore-qwen-runtime.sh`.
4. `SWITCH_CONFIRM=yes bash ops/switch-gpu-model.sh qwen` (or `ops/start-qwen-isolated.sh --start`).
5. Isolated gateway/console `:8013`/`:8083` only unless main promotion is approved.
6. Smoke: direct `:8002` + gateway chat; expect `platform_selection` when registry is loaded.

## Rollback

- To undo a Gemma-bound switch: stop `:8000`, start Qwen isolated stack again.
- To undo a Qwen-bound switch: stop `:8002`, restore/start Gemma as above.
- Never flip `models/registry.yaml` `production:` as part of a GPU switch.

## What this does *not* do

- Change production default
- Auto-start `:8010`/`:8080`
- Dual-load models
- Prove cold-start Pod recreation (still unverified end-to-end)
