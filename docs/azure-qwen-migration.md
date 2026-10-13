# Azure migration readiness — Qwen3.5-27B (optional / deferred)

> **First release status:** RunPod-only. Azure is **not required** for chat, Document Q&A, recovery, or day-to-day operation.
> Keep this document for a future off-platform backup or Azure GPU migration. Do not treat it as a startup dependency.

This document prepares Azure portability. It does **not** create Azure resources, spend quota, or upload weights.

## Source-of-truth boundaries

| Asset | Authority |
| --- | --- |
| Source/config/docs | GitHub (`henokmeron/AI-PLAYBOOK.md`) |
| Large weights | Model object storage (Azure Blob planned) + RunPod `/workspace` working copy |
| Recoverable runtime archives | `/workspace/runtime-setup` (Gemma already; Qwen archive after first success) |
| Secrets | Key files / Key Vault — never Git, never browser bundles |

A Git commit alone does **not** back up model weights.

## Proposed Azure layout (not provisioned)

- Storage account (existing `llmplatform` pattern): container `models`
- Prefix: `models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654/`
- Separate prefix retained for Gemma: `models/gemma-4-31B-it/`
- GPU compute: choose SKU only after a priced estimate and approval (see cost worksheet)
- Networking: private endpoints preferred for Blob; SSH/HTTPS restricted to operator IP
- Secrets: Managed Identity for Blob read; API keys in Key Vault

## Transfer procedure (RunPod → Azure Blob)

1. On RunPod, complete `ops/download-qwen3.5-27b.sh --check` and keep the sha256 inventory under `/workspace/models/Qwen3.5-27B/manifests/`.
2. From an Azure-authenticated transfer host (or AzCopy with MI), recursive copy the revision directory to the Blob prefix above.
3. Re-list remote objects and compare file counts (11 shards + config/tokenizer files).
4. Download a random shard sample or full checksum verify against the RunPod inventory.
5. Only then mark the Azure copy as the durable backup.

Do not delete the RunPod `/workspace` copy until Azure verification succeeds and the operator confirms.

## Runtime requirements on Azure

- CUDA-capable VM or AKS GPU node sized for BF16 (~51+ GiB weights) or an approved FP8/INT4 variant
- Isolated Python/vLLM environment matching `runtime_profiles.qwen-vllm-nightly-isolated`
- OpenAI-compatible listen address behind the platform gateway
- Same registry YAML from Git; `runpod_path` vs Azure mount path overridden by environment, not by editing secrets into the browser

## Configuration / secrets separation

- Registry IDs and ports: Git
- Absolute mount paths: environment on the host
- API keys / storage keys: Key Vault or file permissions `600` on the host
- Browser/console receives only public catalog fields (`/v1/platform/models`)

## Deployment runbook outline

1. Compute: approved GPU SKU, disk sized for weights + KV cache + logs
2. Storage: Blob mount or staged local SSD copy with checksum verification
3. Networking: deny public model ports; expose only gateway
4. Security: MI, least privilege Blob read, no weight paths in client JS
5. Monitoring: GPU memory, `/health`, latency, error rate
6. Backup: Blob + Git tags + `/workspace` snapshots while RunPod remains secondary
7. Rollback: keep Gemma serving config as default; switch `production` only after evaluation

## RunPod → Azure component reuse (2026-10-13)

| Component | Reuse on Azure? | Notes |
| --- | --- | --- |
| `models/registry.yaml` + loader | Yes | Override paths via env; keep production default policy |
| `api/local_gateway.py` | Yes with hardening | Loopback prototype; Azure needs TLS, auth, network policy |
| Isolated vLLM serve scripts | Pattern yes | Rebuild env on Azure image; archive under `/workspace/runtime-setup/qwen-vllm` still TODO |
| RAG / document library | Yes | Point managed docs root at durable disk |
| Web console | Yes behind gateway | Never embed keys |
| Global Volume weights | Transfer then verify | Do not treat RunPod FUSE as Azure Blob |

## Remaining steps requiring explicit approval

- Continued paid RunPod GPU time while models stay loaded
- Restore Gemma main stack (`:8000`/`:8010`/`:8080`) after stopping Qwen
- Create or resize any Azure GPU VM / AKS node
- AzCopy upload of Qwen weights to Blob (egress/time cost)
- Change platform `production` default from Gemma to Qwen
