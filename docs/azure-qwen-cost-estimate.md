# Cost-estimation worksheet — Qwen3.5-27B (indicative only)

> **Optional / deferred.** First release runs on RunPod only. This worksheet is for future comparison, not a startup requirement.

**Not a quote.** Verify live prices in RunPod and the Azure Pricing Calculator before any purchase. No paid Azure resources are created by this worksheet.

## Assumptions

| Assumption | Value used here |
| --- | --- |
| Model | Qwen3.5-27B BF16 (~52 GiB on disk observed) |
| Alternate | FP8 / INT4 checkpoints if VRAM-constrained |
| RunPod GPU (historical platform) | 1× H100 NVL ~94 GB (Gemma baseline) |
| RunPod GPU (2026-10-13 live Qwen) | 1× **A100 80GB PCIe** — ~71 GiB VRAM used while serving |
| Azure GPU candidates | NC H100-class or equivalent; availability TBD |
| Usage pattern for first validation | hours of interactive smoke tests, not 24/7 |
| Concurrent models | false (switch via `ops/switch-gpu-model.sh`) |

## Observed tonight (fill $/h from RunPod console; do not invent prices)

| Observation | Value |
| --- | --- |
| Qwen weights on Global Volume | ~52 GiB at `/workspace/models/Qwen3.5-27B/fc05daec…` |
| Gemma weights on Global Volume | ~59 GiB (unchanged) |
| Model loaded continuously while Pod runs | Yes (Qwen on `:8002` until stopped) |
| Switching models | Requires stop one runtime / start the other (one GPU) |
| Safe shutdown | Stop vLLM processes; stop Pod from RunPod UI to halt GPU billing; keep Global Volume |

## Expected charge categories

1. **GPU compute time** (dominant) — Pod/VM hours while model is loaded
2. **Persistent volume / managed disk** — storing Gemma + Qwen weights
3. **Object storage** — Azure Blob for durable Qwen copy
4. **Network egress** — RunPod → Azure transfer; client traffic usually smaller
5. **Public IP / load balancer** (if any) — avoid exposing raw vLLM ports
6. **Logging/monitoring** — optional
7. **Tax / currency conversion**

## Rough scenario sketch (fill with live numbers before approval)

| Scenario | Compute hours | Indicative compute | Storage delta | Transfer | Notes |
| --- | --- | --- | --- | --- | --- |
| Download + checksum on existing RunPod | 1–3 h wall time | existing Pod rate × hours | +~60 GiB on `/workspace` | HF download ingress | Requires Pod running |
| Isolated Qwen smoke (Gemma stopped) | 1–2 h | same | none beyond weights | none | Needs approval to stop Gemma |
| Azure Blob backup copy | transfer duration | transfer VM optional | Blob ~60 GiB | egress from source | No GPU required for copy |
| Azure GPU soak test | 2 h | SKU $/h × 2 | local SSD as needed | none | Explicit approval required |

Replace every `$/h` cell with calculator output dated and signed off by the operator.

## Cost-control rules

- Prefer stopping GPU compute immediately after smoke tests
- Keep weights on cheap storage; do not keep idle GPUs for downloads alone when avoidable
- Do not dual-load Gemma and Qwen (wastes VRAM and risks OOM)
- Do not promote Qwen to default until evaluation justifies the ongoing serving cost
