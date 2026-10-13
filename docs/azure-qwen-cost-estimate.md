# Cost-estimation worksheet — Qwen3.5-27B (indicative only)

**Not a quote.** Verify live prices in RunPod and the Azure Pricing Calculator before any purchase. No paid Azure resources are created by this worksheet.

## Assumptions

| Assumption | Value used here |
| --- | --- |
| Model | Qwen3.5-27B BF16 (~50–65 GiB on disk) |
| Alternate | FP8 / INT4 checkpoints if VRAM-constrained |
| RunPod GPU (historical platform) | 1× H100 NVL ~94 GB (same class as Gemma baseline) |
| Azure GPU candidates | NC H100-class or equivalent; availability TBD |
| Usage pattern for first validation | a few hours of interactive smoke tests, not 24/7 |
| Concurrent models | false (switch, do not dual-load) |

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
