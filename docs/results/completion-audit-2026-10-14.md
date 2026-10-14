# Completion audit — 2026-10-14

Checked against GitHub `main` at the commit that contains this file, and a read-only look at Pod `3s3mh10hrkhocw` at 20:52 UTC. The Pod was not restarted. The 126.03 GB storage measurement was not repeated.

Labels: **VERIFIED COMPLETE**, **PARTIALLY COMPLETE**, **NOT TESTED**, **BLOCKED**, **NOT STARTED**.

“Pushed” means the source is on GitHub `main`. “Deployed” means the running Pod is executing that source. Those are different. The Pod checkout is still `0b49946` plus one uncommitted `PATH` line.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Startup: `ninja` is on `PATH` when Qwen launches | **PARTIALLY COMPLETE** | Fix is in `ops/start-first-release.sh` (commit `083fa58`, now on `main`). Local test `ops/test_qwen_launch_path.py` passed this session. The first fresh A100 start failed before the fix; the successful start used the same `PATH` prefix by hand. A new Pod has **not** been started from the published script. |
| Startup: preflight, restore to `/tmp`, reuse a healthy Qwen | **PARTIALLY COMPLETE** | `ops/release/START.sh` and `ops/start-first-release.sh`. Live preflight and cold start were verified earlier on this A100 (`docs/AGENT_HANDOFF.md`). Not re-run tonight. |
| Recovery snapshot and checksums | **PARTIALLY COMPLETE** | Snapshot `…-01e7692.tar.gz` checksum matched its manifest on 2026-10-14. Newer `main` commits after `01e7692` do not have a new snapshot. Archives were not re-hashed tonight. |
| Qwen is the default for chat and Document Q&A | **PARTIALLY COMPLETE** | Code and local tests are on `main` (`c232323`). `models/registry.yaml` production id is `qwen3.5-27b`. Tests: omitted model resolves to Qwen; unknown ids return `unknown_model`; a non-Qwen upstream id returns `model_not_loaded`. **Deployed: no.** The live gateway is the older checkout. It is still serving Qwen because that is the only model loaded. |
| Responses name the model that answered | **PARTIALLY COMPLETE** | New code returns `model: qwen3.5-27b` for Document Q&A and `platform_selection.resolved_id` for chat. Covered by `api/test_gateway_reliability.py` on a fake server. Not re-checked on the live Pod tonight. |
| Gemma is optional and not a silent fallback | **PARTIALLY COMPLETE** | Registry `silent_model_fallback: false`. Local tests refuse Gemma while the upstream is port 8002. Gemma weights and archive remain on the volume. No live Gemma switch tonight. |
| Storage: one Qwen copy, one Gemma copy | **VERIFIED COMPLETE** | Read-only `du` on 2026-10-14: 126.03 GB. No second checkpoint. Not repeated. |
| RAG quality | **PARTIALLY COMPLETE** | Benchmark v1 is in `eval/rag/` and `docs/results/rag-benchmark-2026-10-14.md` (40 questions, not a production proof). Live text/PDF/XLSX Q&A was verified earlier on this Pod, then those uploads were deleted. Demo files still present: `/workspace/rag-demo-docs/expenses-policy.md` and `employee-handbook.md`. |
| Agents and tools | **PARTIALLY COMPLETE** | `agents/` unit tests passed this session except one bad assertion, which is fixed in this commit. Live proof is one calculator task (`docs/agents/live-smoke-2026-10-14.md`). Search, PDF, spreadsheet, and abstention are **not** live-verified through the agent. |
| Approval controls | **PARTIALLY COMPLETE** | The runtime pauses when a tool sets `requires_approval`. Local test `test_consequential_tool_pauses_and_resumes_after_approval` passed. No shipped agent tool sets that flag. There is no approval button in the console. |
| Integrations | **NOT STARTED** as real connectors | `integrations/` has a fake connector and unit tests. No authorised external account has been tested. |
| Security | **PARTIALLY COMPLETE** | `docs/security/baseline-review.md`. Nginx on `0.0.0.0:8081` is still an accepted, deferred exposure. Not re-tested tonight. |
| Testing | **PARTIALLY COMPLETE** | Local suites exist and were re-run for startup, registry, and agents. Live model load was not repeated. |
| Maintainability and docs | **PARTIALLY COMPLETE** | Handoff, recovery notes, and this checklist exist. `AUTONOMOUS_WORK_QUEUE.md` had drifted behind `main` and is corrected with this commit. |
| Cost control | **PARTIALLY COMPLETE** | One A100 Pod is still running. Price was last recorded as $1.79/hour and was not re-checked on the billing page. No new Pod was created. |
| Deploy the published `main` onto the Pod | **NOT STARTED** | Requires an approved restart. Do not do it just because GitHub moved. |
