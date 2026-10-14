# Fine-tuning path (future): LoRA / QLoRA for Qwen3.5-27B

Status: **plan only. No training has been run, no datasets exist, and no adapters exist.** The only
code is `agents/dataset_validator.py` (with tests), which checks a dataset before anyone spends GPU
time. Retrieval (RAG) remains the first tool for "know our documents"; fine-tuning is for
*behaviour* such as answer format, citation discipline, abstention and tool-protocol adherence, not
for memorising facts that change.

## 0. When to fine-tune at all

Fine-tune only when all of these hold:

1. A frozen evaluation set shows a **repeatable** failure that prompt and retrieval changes did not
   fix (for example JSON action-protocol violations in `agents/`, or daily/weekly rate confusion).
2. There are at least a few hundred reviewed examples of the desired behaviour, with clear data rights.
3. A rollback path exists (section 7) and the base model stays servable.

## 1. Dataset format and preparation

One JSON object per line (JSONL). Each record is checked by
`python -m agents.dataset_validator data.jsonl --max-tokens 8192`.

```json
{"schema_version": 1, "id": "handbook-0001", "split": "train",
 "source": "synthetic:employee-handbook-v1", "license": "internal-owned",
 "contains_personal_data": false,
 "messages": [
   {"role": "system", "content": "Answer only from the evidence. Cite [Source N]."},
   {"role": "user", "content": "EVIDENCE ... QUESTION How much annual leave?"},
   {"role": "assistant", "content": "25 days per year [Source 1]."}]}
```

What the validator enforces: required provenance fields (`source`, `license`,
`contains_personal_data`, and `consent_basis` when personal data is present), roles in order
(optional system, then user and assistant alternating, ending with assistant), unique ids, the
`train`/`validation`/`test` split vocabulary, **split leakage** (the same user prompt in two
splits), credential patterns (the shared `agents/redaction.py` list), a heuristic for unflagged
emails and UK NI numbers, line and record limits, and an approximate token-length cap matching the
8,192-token serving context.

Preparation steps:

1. Source examples from (a) reviewed production transcripts, only with customer agreement and after
   redaction; (b) synthetic examples generated from fictional or owned documents (as in
   `rag/sample_docs/`); (c) agent traces (`agents/trace.py`), from which tool-protocol examples can
   be rebuilt.
2. De-identify: remove names, emails, NI numbers and addresses unless consent and purpose are
   documented. Never include API keys, the gateway key or `RUNPOD_API_KEY`; the validator blocks the
   common patterns.
3. Human review: at least 10% double-reviewed, with every `test` example reviewed.
4. Freeze: store as `datasets/<name>/<version>/data.jsonl` on the Global Volume (not GitHub), with
   `sha256sum`, the validator report, and a `DATASHEET.md` (purpose, sources, licence, PII handling,
   known gaps).

## 2. Data rights and privacy

- Customer documents and conversations are **not** training data by default. Use requires a written
  agreement that names the purpose, retention and the right to withdraw. Record its id in
  `consent_basis`.
- Keep per-customer adapters separate (one tenant = one adapter) unless every contributor agreed
  to pooled training. A shared adapter trained on tenant A's data could leak A's facts to tenant B.
- Honour deletion. When a customer withdraws, delete their examples, retrain or retire any adapter
  trained on them, and log the action. Adapters are small, so retraining is cheap.
- Check the base model licence (registry `license` field) and every dataset licence before training.
  Record both in the adapter card.

## 3. Splits

- Split by **source document or conversation**, not by row, so that near-duplicates do not cross
  splits. The validator catches exact duplicate prompts only.
- Suggested split: 80/10/10 train/validation/test. The `test` split is frozen and never used for
  tuning decisions.
- Keep the existing evaluation assets (`evaluation/`, `eval/rag/` regression sets) as **external**
  benchmarks that are never trained on.

## 4. Feasibility on our hardware (estimates, not measured)

Qwen3.5-27B is a ~27B-parameter hybrid model (the platform already caps Mamba-style sequence state
in vLLM). Memory estimates:

| Setup | Weights | Fits A100 80GB? | Fits H100 80/94GB? | Notes |
| --- | --- | --- | --- | --- |
| LoRA on bf16 base | ~54 GB | **Tight**: rank ≤16, seq ≤4k, micro-batch 1, gradient checkpointing; risk of OOM | Feasible at seq 4–8k with more headroom on H100 NVL 94GB | Best quality; slower |
| QLoRA (4-bit NF4 base, bf16 adapters) | ~15–17 GB | **Yes**, seq 8k, micro-batch 1–2 | Yes | Small quality cost; needs bitsandbytes support for every layer type |
| Full fine-tune | ~54 GB + optimizer ≫ 80 GB | No | No | Out of scope |

Hard constraints:

- **No co-location.** The serving GPU is fully used by vLLM (`--gpu-memory-utilization 0.92`).
  Training needs a separate Pod or a planned serving outage; it must never run on the live Pod.
- **Framework support must be verified first.** Hybrid linear-attention or state-space layers need
  matching kernels in `transformers`/PEFT. Confirm that LoRA target modules exist for the attention
  *and* the linear-attention blocks, and that 4-bit quantisation covers them, using a 10-step dry
  run before budgeting a full run.
- Rough cost model (verify current prices): QLoRA over 2k examples × 2k tokens × 3 epochs is about
  12M tokens, likely 1–3 GPU-hours on one A100/H100. Budget a 2× retry margin.

## 5. Reproducible training recipe (to implement later)

- Pin everything: base model `huggingface_id` + exact revision (registry: `fc05daec…`), container
  image digest, `transformers`/`peft`/`trl`/`bitsandbytes` versions in a hashed lock file, and the
  dataset SHA-256.
- Config in a versioned YAML file: LoRA rank 16, alpha 32, dropout 0.05; target modules listed
  explicitly; LR 1e-4 cosine with 3% warm-up; 2–3 epochs; seed fixed; loss on assistant tokens only;
  chat template identical to serving (`enable_thinking: false` as in the vLLM launch).
- Output: `adapters/<name>/<semver>/` with the `adapter_model.safetensors` SHA-256, the config,
  the dataset hash, eval results and an `ADAPTER_CARD.md`. Store on the Global Volume and an
  off-Pod backup, never in Git.

## 6. Before/after benchmarks (gate for promotion)

Run the **same frozen suites** on the base and on base+adapter, with temperature 0:

1. The held-out `test` split (task metric: exact-match or rubric).
2. Existing RAG regression and safety sets (abstention, citation, daily-vs-weekly, stale-document
   checks). These must not regress.
3. Agent protocol suite: the rate of valid JSON actions, and task success on scripted multi-step
   tasks (run `agents/` against the live model).
4. General capability spot checks (a short generic chat set) to detect catastrophic forgetting.
5. Safety: refusal of unsafe tool requests, and prompt-injection documents.

Promote only if the target metric improves beyond run-to-run noise (run each suite twice) and
**no** safety or regression metric gets worse. Record results in `docs/results/`.

## 7. Versioning and rollback

- Add the adapter as a registry entry (for example `qwen3.5-27b+handbook-lora@1.0.0`) with
  `base_model_id`, `adapter_sha256`, `evaluation_status` and `selection_eligible: false` until it
  passes the section 6 gates.
- Rollback = select the base model id (adapters never modify base weights). Keep the previous
  adapter version loadable for at least one release.
- Never silently remap: the gateway's existing no-silent-fallback rule (registry
  `silent_model_fallback: false`) should also apply to adapter ids.

## 8. Serving with vLLM LoRA

vLLM serves LoRA adapters next to the base model:

```
vllm serve /workspace/models/Qwen3.5-27B/<rev> ... \
  --enable-lora --max-loras 2 --max-lora-rank 16 \
  --lora-modules handbook-v1=/workspace/adapters/handbook/1.0.0
```

Clients then request `"model": "handbook-v1"`. To verify before relying on this: that the pinned
vLLM build supports LoRA for this hybrid architecture; the extra memory (LoRA slots reduce KV-cache
headroom, so re-check `--gpu-memory-utilization` and `--max-num-seqs`); and per-request latency.
The gateway would need registry support for adapter ids (owner: gateway agent). Per-tenant adapters
also need the per-tenant key work from security finding H-2, so that tenant B cannot select tenant
A's adapter.
