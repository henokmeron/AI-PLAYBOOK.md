# AI Platform Release (Global Volume)

Durable entrypoint for the RunPod-first release. Full guide: `docs/first-release-recovery.md` in the repository.

```bash
bash /workspace/ai-platform-release/START.sh             # start (or reuse) Qwen + gateway + console
bash /workspace/ai-platform-release/START.sh --preflight # checks only; starts nothing
bash /workspace/ai-platform-release/START.sh --check     # current status
```

- Only Qwen3.5-27B starts automatically. Gemma stays on the volume and never loads unless an operator switches models.
- Requires an 80GB-class NVIDIA GPU (A100 80GB or H100) with driver 580 or newer.
- The runnable environment is restored to `/tmp` from `/workspace/runtime-setup/qwen-vllm/`. It is never extracted onto `/workspace`.
- Source comes from GitHub (`feature/qwen3.5-27b-integration`). If GitHub is unreachable, the newest checksum-verified snapshot in `/workspace/ai-platform-backups/source-snapshots/` is used.
- `ops/` and `tree/` in this folder are legacy copies from an earlier launcher. The current `START.sh` does not use them.

Console access from your laptop:

```bash
ssh -N -L 18080:127.0.0.1:8080 -p <tcp-port> -i <key> root@<pod-ip>
# then open http://127.0.0.1:18080
```
