# LLM Build Playbook

## 0. Project purpose
Build a commercial, general-purpose business AI platform using leading open-weight/open models as the starting point.

The long-term product is not simply an LLM. The LLM is the intelligence engine underneath a broader platform that can provide private, controllable AI capabilities to businesses.

Target capabilities include:
- Business chat and knowledge retrieval
- Document understanding and RAG (retrieval-augmented generation)
- Coding and programming
- Spreadsheet and report work
- Finance/accounting workflows
- Microsoft 365 integrations (Outlook, Excel, Teams, SharePoint, OneDrive, etc.)
- Business software integrations (for example Xero, QuickBooks, Sage)
- Meeting transcription, summarisation and minutes
- Tool/API use
- Workflow automation
- Memory and company-specific context
- Agent-like execution where appropriate

## Mandatory living playbook — continuously maintained

The platform and playbook evolve together. A significant change is unfinished until matching docs are updated, accurate, committed, and pushed to `main` with the code. Non-negotiable.

### A. Update with the change
In the same increment, record what changed, how to run/recover it, and the commit/release identity. Label **planned / implemented / tested / deployed / verified** (or VERIFIED / FAILED / NOT TESTED / BLOCKED). Do not document unbuilt work as done.

### B. No empty status commits
Keep docs accurate on active days. Do not invent status-only commits when nothing material changed.

### C. Ship on GitHub
Docs go with the code to `main`. Local-only doc edits are unfinished.

### D. Write for the next agent
Enough for a new agent to continue without chat: exact commands, where they run, how to verify. Never put secrets in docs.

### E. Keep history
Do not silently erase decisions or working configs. Mark superseded docs and link replacements.

### F. Pre-push check
Docs match code; verification claims are honest; recovery still valid; no secrets. Does not replace approval rules in `docs/AGENT_HANDOFF.md`.

### G. Verify, commit, push, and remote parity
Use `C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe` with `-C` set to `C:\Users\henok\src\AI-PLAYBOOK.md`. Never run git in `C:\Users\henok`.

1. `remote -v` must show exactly `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. If it does not, stop.
2. Run the focused tests for the change, then `python -m ops.run_tests`, then `git diff --check`. Read the diff for secrets, `__pycache__`, and `ops/_*.sh` / `ops/_*.py`.
3. Commit on `main` with `git commit -m "message"`. Never force-push. Never update git config. Never skip hooks.
4. Push `main`. Fast-forward `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration` only when that push is a true fast-forward. Do not use `--force`.
5. `git ls-remote origin` those three refs and require one SHA. A push is not a deployment. The pod checkout stays where it is until a separate approved source update.

## 1. Core business strategy
Do not compete only by owning a model.

Commercial value will come from:
1. Model selection and evaluation
2. Secure infrastructure
3. RAG and company knowledge
4. Tools and integrations
5. Workflow automation
6. Customer-specific configuration
7. Fine-tuning/adapters where justified
8. Reliability, monitoring and security
9. A continuously improving model-upgrade process

Intended business progression:
IT/AI services -> AI implementation -> AI employees/workers -> AI SaaS -> AI infrastructure/platform -> potentially specialised proprietary models.

## 2. Model strategy
We will start from leading open-weight models rather than training a foundation model from scratch.

The platform must remain model-independent.

New model lifecycle:
New model released -> discover -> security/licence checks -> download candidate -> evaluate -> compare with production -> approve -> deploy -> monitor -> rollback if required.

A new model should NOT automatically replace production merely because it is newer.

Model registry fields should include:
- model family
- exact model/revision
- licence
- source
- provenance
- hardware requirements
- evaluation results
- status (candidate / approved / production / retired)
- deployment configuration

Model choice is TBD. The shortlist should favour strong open-weight models with suitable commercial licensing, security posture, technical performance and practical deployment requirements. Preference is for trustworthy UK/EU/US/Western ecosystem providers where capability is competitive, but compliance is determined by the complete system and use case, not by the model's country of origin alone.

## 3. Storage and infrastructure
GitHub is the software/control hub, not the place for giant model weights.

Expected separation:
- GitHub: source code, configuration, documentation, evaluations, infrastructure code, playbook
- Model source/registry: Hugging Face and/or official model publisher
- Object storage: selected cloud/object storage for controlled copies of large model files
- GPU compute: chosen separately from storage
- Production API: hosted service exposing the model/platform

Azure is an option, not a requirement. We will choose infrastructure after evaluating cost, GPU availability, UK/EU data residency, security, reliability and commercial suitability.

Do not buy large cloud resources until the technical design requires them.

### Operator system manual

- Beginner map of the whole platform (GitHub vs volume vs Pod, ports, folders, what each piece is): **`docs/SYSTEM_MANUAL.md`**. Update it when the architecture changes.
- Named console login (admin / operator / viewer, no default password): **`docs/security/operator-auth.md`**. First administrator: `scripts/provision_console_operator.py create-admin`. This is local operator login, not Microsoft Entra.
- Source release and pre-shutdown checkpoint: **`docs/release/RECOVERY.md`** and **`docs/release/PRE_SHUTDOWN.md`**. The checkpoint does not stop the Pod.

### 2026-10-15 — AI IT Helpdesk

- Agent page is the IT Helpdesk: classify → docs/health/diagnostics → approval-gated local remediation → verify → incident report.
- Tools: `agents/builtin/helpdesk.py`. Docs: `docs/agents/helpdesk.md`. Mock E2E **VERIFIED**. Live Qwen on Pod `4lvr54b0wmkz6c` tip **`c069674`**: **VERIFIED** (`docs/results/helpdesk-live-qwen-2026-10-15.md`) — smoke + UI approval of `clear_temp_cache` only.
- Active Pod: `4lvr54b0wmkz6c` (A100 SXM, same Global Volume). Prefer Stop when idle.

### 2026-10-15 — Agent execution loop (progress + history)

- Console Agent desk supports async runs (`wait: false`), live status polling, cooperative cancel, serial `queued` tasks, IT-support incident reports, and redacted task history (defaults to `/workspace/agent-task-history` on the volume).
- Live on Pod `1cj381fjuujeq7` (tip **`a680580`**): E2E + Agent async **VERIFIED** 2026-10-15 (pod later replaced by `4lvr54b0wmkz6c`). Details: `docs/results/runpod-migrate-deploy-2026-10-15.md`.

### 2026-10-14 — RunPod-first first release (Qwen primary)

- **Hosting:** RunPod Global Volume + Pod GPU is the standalone first-release deployment. Azure is optional/deferred and not required to start, chat, or recover.
- **Primary model:** Qwen3.5-27B (`qwen3.5-27b`, revision `fc05daec18b0a78c049392ed2e771dde82bdf654`) on `:8002` with gateway `:8010` and console `:8080`.
- **Start:** `bash /workspace/ai-platform-release/START.sh` (see `docs/first-release-recovery.md`).
- **Cost control:** stop the paid Pod to halt GPU compute; keep the Global Volume for weights/archives/docs. Gemma weights may remain stored but are not required for normal operation.

## 4. Compliance-by-design
The initial commercial target is the UK, with architecture suitable for expansion into the EU and other Western markets.

The system must be designed around:
- GDPR / UK GDPR principles
- UK data protection requirements
- EU AI Act obligations where applicable
- Data minimisation
- Purpose limitation
- Tenant isolation
- Encryption in transit and at rest
- Identity and access control
- Secrets management
- Audit logging
- Retention/deletion controls
- International-transfer controls where relevant
- Security and vulnerability management
- Model/software supply-chain checks
- Model licence and commercial-use review
- Human oversight for higher-risk use cases

Important: no model is automatically approved by UK/EU/US regulators. Compliance depends on the model, deployment, data, contracts, security controls and intended use.

## 5. Multi-tenant architecture
Do not create a completely separate giant model for every company.

Prefer a shared model/platform with isolated customer data, tools and configuration.

Each customer's environment must be logically and technically isolated.

Customer-specific knowledge should normally be provided through RAG, tools, configuration and access controls rather than duplicating the base model.

## 6. Intelligence stack
A general business AI system will not be created by fine-tuning alone.

Target stack:
Base model + RAG + tools/APIs + memory + code execution where appropriate + integrations + planning/orchestration + evaluation + security controls + selective fine-tuning/adapters.

RAG means retrieval-augmented generation: the model retrieves relevant information from approved documents/databases at runtime rather than relying only on knowledge stored in its parameters.

Fine-tuning will be used selectively for behaviour, formatting, domain patterns or task performance where it provides measurable value.

## 7. Continuous learning vs continuous updating
The platform should distinguish:
- Model updates: replacing/upgrading the underlying model
- RAG updates: changing the information the model can retrieve
- Tool updates: adding or changing capabilities
- Fine-tuning: changing model behaviour/parameters
- Evaluation updates: improving our tests
- System updates: improving orchestration and infrastructure

The system should not learn everything simply from chat history. Knowledge and behaviour must be managed deliberately.

## 8. Evaluation system
Before promoting a model, evaluate at minimum:
- Reasoning
- Coding
- Tool calling
- Instruction following
- Long-context tasks
- Structured output
- Hallucination/error rate
- Business document tasks
- Spreadsheet/report tasks
- Latency
- Memory/GPU requirements
- Cost per useful task
- Safety/security behaviour

The evaluation suite itself becomes part of the company's intellectual property and competitive moat.

## 9. Automation goal
Every major development action should be documented so that later we can ask: Could another AI system reproduce this process?

The playbook should record:
- What was done
- Why it was done
- Exact tools/services used
- Configuration decisions
- Commands/code where useful
- Inputs and outputs
- Problems encountered
- Fixes
- Security/compliance implications
- What could be automated
- What should remain human-controlled

The eventual goal is for AI to automate increasingly large portions of model selection, testing, deployment, documentation and software construction.

## 10. Planned repository structure
Proposed starting structure:

/
|-- PLAYBOOK.md
|-- README.md
|-- models/
|   |-- registry.yaml
|   |-- candidates.yaml
|   `-- production.yaml
|-- evaluation/
|-- inference/
|-- api/
|-- rag/
|-- tools/
|-- training/
|-- updater/
|-- security/
|-- infrastructure/
|-- configs/
|-- tests/
`-- docs/

The structure can evolve as implementation starts.

## 11. Initial roadmap
Phase 1 — Foundation
- GitHub repository
- PLAYBOOK
- model registry
- infrastructure design
- first model selection
- inference prototype

Phase 2 — Evaluation
- automated benchmark suite
- cost/latency measurement
- regression tests

Phase 3 — Model lifecycle
- model discovery
- candidate downloads
- validation
- evaluation
- promotion/rollback

Phase 4 — General AI capabilities
- RAG
- tool calling
- memory
- APIs
- code execution
- structured outputs

Phase 5 — Business integrations
- Microsoft 365
- Outlook
- Excel
- Teams
- SharePoint
- OneDrive
- accounting/CRM/business APIs

Phase 6 — Commercial platform
- multi-tenancy
- authentication
- billing
- monitoring
- customer administration
- security/compliance controls

Phase 7 — Advanced model customisation
- LoRA/adapters
- fine-tuning
- specialised datasets
- proprietary evaluation data
- potentially continued pretraining if justified

## 12. Current decisions
- Canonical local checkout on this PC: `C:\Users\kokob\src\AI-PLAYBOOK.md`. Remote `origin`: `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. The working branch is `main`.
- Primary objective: build a commercial AI platform, not merely a standalone LLM.
- Start from open-weight models.
- Keep the platform model-independent.
- GitHub is the central software/control hub.
- Do not store huge model weights in GitHub.
- Hugging Face is a major model source/registry, not automatically our production storage.
- Azure is an infrastructure option, not mandatory.
- Prefer strong Western/UK/EU-compatible model ecosystems where capability is competitive.
- Compliance must be designed into the complete system.
- Document the work continuously.
- Educate the builder during implementation.
- Treat the playbook as a reproducible blueprint for future AI-assisted automation.

## 13. Change log
### 2026-10-22 — Saved redirect re-read, release checks, still NO-GO

- **VERIFIED:** Entra Authentication (Preview), not the manifest editor, shows platform Mobile and desktop applications and redirect `http://127.0.0.1:18080/api/microsoft/callback`. Supported accounts: Single tenant only - Default Directory. Tenant ID from Entra overview: `d595636e-9ef4-4890-b8a7-bde8dd5cab03`. Delegated `Mail.Read` and `User.Read` only. No mailbox was read. Microsoft stays **NOT CONFIGURED**. `MICROSOFT_TENANT=common` will not complete sign-in.
- **VERIFIED:** RunPod billing header re-read after reload: account balance $14.93, spend rate $3.197/hr, estimated time left 5 hours. An earlier load of the same page showed $15.46. Neither read was $0.00. Pod `xx9cjogra5vcwl` left running. Not deployed.
- **VERIFIED:** isolated `python -m ops.release.recover` of archive `d8c32ff` into a temp directory. That is not a fresh machine. No volume copy.
- **NOT TESTED:** second Windows computer. **NOT TESTED:** live Blackwell (needs a CC 12.0 GPU and driver 575 or newer). Go-live **NO-GO**.

### 2026-10-22 — Local release of 281eb62 and Microsoft read scope

- **VERIFIED:** H100 pod `xx9cjogra5vcwl` still running. `:8002`, `:8010`, and `:8080/api/status` returned 200. Pod checkout remains `a0e9422`. Not restarted.
- **VERIFIED:** local archive of `281eb628b51f100433e3f4ab0aad83b516050ae5`, SHA-256 `1a998f7103cc8ca4a9f3a14047eb37e14d95470bba87c232c085e09851b7dad7`, 375 members. Not on the volume. Weights were not copied off the volume.
- **NOT CONFIGURED:** Microsoft mail. Delegated `Mail.Read` is on the existing app. The loopback redirect was not confirmed saved in that pass, and no mailbox was read. A later pass re-read Authentication and confirmed the saved redirect. Mail is still **NOT CONFIGURED**.

### 2026-10-22 — Read-only Windows collectors
- **Implemented and tested on the development PC:** fixed collectors for `win.activation.inspect`, `hw.usb.inspect`, `net.wifi.inspect`, `net.proxy.inspect`, `net.tls.inspect`, `app.browser.inspect`, `app.permissions.inspect`, and `app.crash.evidence`. No product key, Wi-Fi password, proxy credential, private-key export, ACL change, firewall change, process kill, or browser-profile reset. `problem_resolved` stays false. Heartbeat checks were not expanded.
- **VERIFIED:** `python -m ops.run_tests` on Python 3.11.9, 38 modules, 0 failed, 1 skipped, exit 0. H100 pod `xx9cjogra5vcwl` was read-only inspected and left running. Inventory: `docs/results/asset-inventory-2026-10-22.md`.
- **NOT TESTED / NOT CONFIGURED** in that collector pass: live Blackwell, mail Graph, a second Windows computer. A later entry the same day confirmed delegated `Mail.Read` and the saved redirect. Mail stayed **NOT CONFIGURED**. Go-live **NO-GO**.

### 2026-10-21 — Living playbook lean trim
- Trimmed **Mandatory living playbook — continuously maintained** (A–F) to vital operational rules only. No feature claims.

### 2026-10-21 — Mandatory living playbook recorded
- Recorded the owner mandate **Mandatory living playbook — continuously maintained** (sections A–F) early in this playbook, after project purpose.
- Standing-rule pointer added in `docs/AGENT_HANDOFF.md`. Documentation discipline only; no platform features claimed as implemented in this entry.

### 2026-10-20 — Device job review fixes
- `DeviceStore.issue` accepts only read-only diagnostics. `print.spooler.restart` is rejected at issue time and is not executed. An approval id does not enable it.
- A matching operator name is not authority. Issuance requires `grant_from_session` from a server-side session with role `admin` or `operator` and the same tenant. Viewers, missing sessions, and cross-tenant grants are refused. There is no console route that passes a request field into `issue`.
- The signing key is stored in a sibling `*.key` file, not in the job JSON. Version 1 files are rewritten to version 2 on load without dropping jobs. Corrupt files fail closed and are not replaced. On POSIX the key and state files are mode `0600`. Windows keeps the current user's file ACL.
- A nonce without a recorded terminal state is `rejected`, not `accepted`, and is not HEALTHY. Replay after restart does not collect.

### 2026-10-20 — Endpoint evidence and job rejection
- Revoked or unauthorised device jobs are stored as `rejected` and are not collected. Expired jobs are not collected. A failed read-only collection is `failed`.
- Director `repair_jobs` and `endpoint_fleet` are HEALTHY only when evidence is present, successful, and newer than one day. See `docs/IMPLEMENTATION_STATUS.md`.

### 2026-10-20 — Canonical checkout
- The canonical local checkout is `C:\Users\kokob\src\AI-PLAYBOOK.md`.
- GitHub `origin` is `https://github.com/henokmeron/AI-PLAYBOOK.md.git` on branch `main`.
- Director `repair_jobs` is HEALTHY only for a fresh `live_windows` accept. A mock, fixture, missing, or stale check-in is not HEALTHY.

### 2026-10-07 — Project start
- Defined the project as a commercial open-weight LLM platform.
- Established model-independent architecture.
- Established GitHub as the central software/control hub.
- Established separation between code, model source, model storage and compute.
- Established UK/EU compliance-by-design as a core requirement.
- Established continuous model evaluation and controlled upgrading.
- Established long-term goal of general-purpose business AI capabilities.
- Established this playbook as a living document that will be updated throughout development.

### 2026-10-08 — Working baseline selected
- Chose Google Gemma 4 31B-it as the first practical working baseline so development can start now.
- This is a prototype baseline, not a permanent choice of foundation model.
- The Hugging Face repository currently lists the model under Apache-2.0 and provides the weights through Hugging Face storage.
- The full 31B repository is approximately 62.6 GB, so model files will not be stored on the developer PC or in GitHub.
- Mistral Large 4 remains a future candidate to evaluate when its public weights are released.


### 2026-10-08 — Azure storage created
- Azure Pay-As-You-Go subscription/storage is now available for the prototype.
- Storage will be used for model weights; GitHub will remain the code/control hub.
- No GPU compute has been created yet.


### 2026-10-08 — Model container created
- Created a private Azure Blob container named `models`.
- Purpose: dedicated private storage area for large model files.
- Important architecture lesson: the container stores the model; it does not run the model.
- The next task is a controlled transfer of the Gemma 4 31B-it files from Hugging Face into this container without downloading them onto the developer PC.


### 2026-10-08 — Gemma 4 downloaded to temporary Azure VM
- Connected to the temporary Ubuntu VM over SSH after correcting the VM network-interface inbound rule for TCP 22, restricted to the developer's source IP.
- Identified the separately attached 128 GiB data disk as `/dev/nvme0n2`; formatted it as ext4 and mounted it at `/mnt/model`. The OS disk remained separate.
- Installed `huggingface_hub` and the `hf` CLI in a dedicated Python virtual environment at `/home/azureuser/.hf-cli/venv`. The installer initially failed because pip was missing from its environment; rebuilding the virtual environment restored pip and the CLI installation succeeded.
- Authenticated to Hugging Face and confirmed the account with `hf auth whoami`.
- Ran a dry run for `google/gemma-4-31B-it`; Hugging Face reported 12 files totalling 62.6 GB.
- Downloaded the complete model repository to `/mnt/model/gemma-4-31B-it`; the CLI reported download and reconstruction complete (62.6 GB).
- Security note: do not put the Hugging Face token or SSH private key in GitHub or share them in chat.
- Current status: model files are on the temporary VM data disk only. They have not yet been verified in Azure Blob Storage. Keep the VM and data disk until the Blob copy has been verified; delete temporary resources only afterward.
- Next step: securely transfer the model directory into the private Azure Blob container `models`, verify the remote files, then clean up temporary compute and disk resources.


### 2026-10-09 — Download verification
- Verified the model directory with `du -sh`: 59G on the Linux VM disk.
- Verified both weight shards exist: `model-00001-of-00002.safetensors` (~47G as displayed by `ls -lh`) and `model-00002-of-00002.safetensors` (~12G).
- Verified the mounted data disk is 125G total with 61G available (50% used).
- The earlier Hugging Face dry-run reported 62.6 GB in decimal units; the local Linux tools display sizes using their own units/rounding. The completed download and both shard files are present.
- Next: enable a system-assigned managed identity on the temporary VM, grant it the minimum required Blob data role, upload to the private `models` container, verify the remote copy, then clean up the temporary VM/disk.


### 2026-10-09 — Azure transfer preparation
- Confirmed the Gemma 4 31B-it repository is downloaded on the temporary VM's attached data disk at `/mnt/model/gemma-4-31B-it`; local Linux tools report 59 GiB and show both safetensors shards (approximately 47G and 12G).
- Installed AzCopy via the Microsoft Ubuntu package feed. The installed package reports `10.33.0-beta`; before transferring the 62.6 GB model, prefer the official stable AzCopy release rather than a pre-release build.
- Confirmed the VM system-assigned managed identity is enabled.
- Assigned `Storage Blob Data Contributor` to that VM identity at the private `models` container scope. This is intended to permit blob data operations without storing a storage account key on the VM.
- Purpose explained: the VM/data disk is temporary transfer compute; Blob Storage is a separate durable storage layer and does not run the model. Copy the weights there, verify the remote copy, then delete the temporary VM and data disk to avoid unnecessary compute/disk charges. Do not delete the source copy until the remote copy is verified.
- Next: use the latest official stable AzCopy package, authenticate AzCopy with the VM's managed identity, identify the storage-account URL, upload the model directory to `models/gemma-4-31B-it`, and verify every expected file remotely.


### 2026-10-09 — Gemma upload to Azure Blob Storage completed
- Installed the stable AzCopy 10.32.8 package and set `AZCOPY_AUTO_LOGIN_TYPE=MSI` in the active VM shell to authenticate through the VM's system-assigned managed identity.
- Used `azcopy list 'https://llmplatform.blob.core.windows.net/models'` as a pre-upload access check; it returned no visible entries before the upload and no error.
- Uploaded `/mnt/model/gemma-4-31B-it` to `https://llmplatform.blob.core.windows.net/models/gemma-4-31B-it` using AzCopy recursive copy.
- AzCopy job `efc27ac6-a333-7c45-4dc0-c2ac25533fa7` reported 39 file transfers completed, 0 failed, 0 skipped, 62,578,689,665 bytes transferred, final job status Completed.
- Current status: upload job completed, but a separate read-back listing of the Blob destination is still required before declaring the remote copy fully verified.
- Keep the temporary VM and attached 128 GiB data disk until destination listing confirms both safetensors shards and expected configuration/tokenizer files. Then consider cleanup of temporary compute/disk resources while retaining the Blob copy.


### 2026-10-09 — Blob destination verified
- Ran `azcopy list 'https://llmplatform.blob.core.windows.net/models/gemma-4-31B-it' --machine-readable --running-tally`.
- Destination listing returned 39 files totalling exactly 62,578,689,665 bytes, matching the successful upload job.
- Confirmed both model weight shards are present:
  - `model-00001-of-00002.safetensors`: 49,784,788,364 bytes
  - `model-00002-of-00002.safetensors`: 12,761,549,884 bytes
- Confirmed supporting files include `config.json`, `generation_config.json`, `model.safetensors.index.json`, `processor_config.json`, `tokenizer.json`, and `tokenizer_config.json`.
- The 39 files include small Hugging Face cache metadata/lock files copied by the recursive transfer in addition to the 12 repository files shown in the dry run. These files are extra metadata and do not prevent using the model.
- The model copy is verified in Blob Storage. The temporary transfer VM and attached 128 GiB data disk can now be cleaned up after confirming the correct temporary resources in Azure Portal. Preserve the storage account `llmplatform`, its private `models` container and the `models/gemma-4-31B-it` blobs.


## 14. Expanded product vision: broad integrations, website intelligence and defensive cybersecurity

These requirements are part of the long-term product direction. They do not mean every capability must be implemented in the first prototype. Build them as modular services behind a model-independent platform, with permissions, evaluation and auditability from the beginning.

### 14.1 Defensive AI cybersecurity ("AI versus AI")

Goal: provide a commercial defensive-security capability that helps businesses detect, investigate and reduce cyber risk, including attacks assisted by AI agents. Use AI to help defend systems; do not promise that any system can prevent every attack.

Planned capability areas:
- Asset inventory and attack-surface visibility for customer-owned or explicitly authorised systems.
- Continuous monitoring of approved telemetry from security tools, cloud platforms, identity providers, endpoints, firewalls, DNS, web application firewalls (WAFs), application logs and audit systems.
- Detection and triage of suspicious activity, including unusual agent/tool behaviour, anomalous API use, credential misuse, prompt-injection attempts against business agents, suspicious privilege changes and possible data exfiltration.
- Defensive agents for alert enrichment, log correlation, investigation summaries, prioritisation, incident timelines, recommendations and evidence collection.
- Controlled security testing and configuration checks only within a written, approved scope; safe validation of discovered weaknesses; integration with existing scanners rather than uncontrolled internet-wide scanning.
- Response orchestration for approved actions, such as opening a ticket, isolating an endpoint through an authorised tool, disabling a token, blocking an indicator, or applying a WAF rule. Start in recommendation/dry-run mode; require human approval for high-impact actions until safety and reliability are established.
- An auditable incident workflow with evidence, confidence/uncertainty, timestamps, rationale, recommended actions, approvals, outcomes and rollback instructions.
- Security testing of our own AI platform and its agents: least-privilege tools, tool allowlists, input/output checks, sandboxed execution, secret protection, tenant isolation, prompt-injection resistance, exfiltration controls, rate limits and monitoring.
- Benchmark the capability against realistic defensive test cases, including false positives, false negatives, time to detect, time to investigate, unsafe action rate and recovery/rollback success.

Architecture principles:
- AI adds analysis and automation; it does not replace foundational security controls such as patching, MFA, least privilege, backups, network segmentation, secure configuration and incident-response procedures.
- Use multiple layers: deterministic controls and established security products, telemetry/rules, anomaly detection, AI-assisted investigation, policy-based approvals and human incident command.
- Separate read-only monitoring permissions from response permissions. Grant the minimum permissions required for each connector and customer.
- Tenant data and credentials must be isolated. Secrets belong in a managed secrets store, never in prompts, source code or logs.
- All active testing must be authorised by the asset owner, restricted to an explicit scope and time window, rate-limited, logged and stoppable. Do not scan or test government, third-party or arbitrary public systems without explicit written authorisation.
- Treat AI-generated security findings as hypotheses until supported by evidence. Include confidence levels and clear verification steps.
- Never claim "complete protection" or guarantee that no AI agent can hack a system. Position the product as layered prevention, detection, response and risk reduction.

### 14.2 Broad business and developer integrations

Do not hard-code the product to a short list such as Xero, QuickBooks or Sage. Create a connector framework that can expand across categories, including:
- Finance, accounting, payroll, ERP, procurement and billing
- Microsoft 365, Google Workspace, email, calendars, chat and collaboration
- CRM, customer support, ticketing, project management and HR
- Cloud providers, identity systems, endpoint/security tools, SIEM/SOAR, WAF/CDN and monitoring platforms
- Websites, content-management systems, e-commerce, booking systems and analytics
- Social media and publishing platforms where official APIs and the customer's permissions allow it
- Databases, data warehouses, object storage, internal APIs, webhooks and custom line-of-business software.

Connector design requirements:
- Prefer official APIs, vendor-supported OAuth and scoped access tokens. Use webhooks or event streams where available.
- Provide a documented connector SDK/interface so new integrations can be added without changing the core agent.
- Define each connector's capabilities, required permissions, data types, rate limits, retention behaviour and supported actions.
- Separate read/search actions from write/send/delete/admin actions. Sensitive actions should use narrow scopes and approval policies.
- Include retries, pagination, rate-limit handling, idempotency where possible, audit trails, health checks, revocation and graceful failure.
- Respect each vendor's terms, technical limits, privacy obligations and customer authorisation. Do not bypass access controls or scrape authenticated systems without permission.
- Design for least privilege, per-customer credential separation and connector-specific tests.

### 14.3 Website scanning and business knowledge ingestion

Product concept/name for planning: **Website Intelligence / Business Knowledge Onboarding**. The final market-facing name can be decided later.

Goal: let an authorised customer connect a business website and build a searchable, source-linked snapshot of the information it publishes, so its AI assistant can answer business-specific questions without requiring the customer to upload every page manually.

Planned workflow:
1. Customer verifies ownership or explicitly confirms authorisation and defines the permitted domains/subdomains and scan boundaries.
2. Discover allowed pages through sitemaps, links and configured URL seeds; respect robots directives, access controls, rate limits and the site's terms.
3. Crawl permitted public content. Authenticated or private content is included only through a specifically authorised integration and credentials with appropriate scope.
4. Extract clean text and useful structure from HTML and supported document types; preserve page URLs, titles, headings, timestamps and provenance.
5. Deduplicate, chunk and index the content; create embeddings where useful and store retrievable source references. Keep website content distinct from trusted system instructions because pages may contain malicious prompt-injection text.
6. Produce a business knowledge summary with source links and clear coverage metadata. Summarise areas such as products/services, pricing when published, locations, opening hours, policies, support information, contact details and other facts actually present on the site.
7. Make the indexed information available to the customer's agent through retrieval-augmented generation (RAG), with citations to the pages used.
8. Support rescans, scheduled refresh, change detection, deletion, exclusions and administrator review. Show scan date, crawl coverage, failed URLs and likely gaps.
9. Allow customers to add other authorised sources—files, knowledge bases, APIs, CRM, support systems and internal documents—because a public website rarely contains the full internal truth about a business.

Safety and quality requirements:
- A website scan must not imply that the AI knows everything about the company. Clearly distinguish public website facts, connected internal sources, inferred information and unknowns.
- Never treat retrieved website content as trusted instructions for the agent. Defend against prompt injection, malicious links, hidden content and attempts to exfiltrate customer data.
- Prevent crawling outside the configured scope; handle redirects safely; block access to private/internal IP ranges and cloud metadata endpoints to reduce SSRF risk.
- Limit crawl depth, page count, file size, concurrency and frequency; apply content-type checks, malware scanning where appropriate and robust parser isolation.
- Keep tenant indexes separate, apply access controls at retrieval time, preserve source citations and support deletion/refresh when content changes.
- Do not crawl private or third-party areas without permission. Respect authentication, robots directives, copyright, privacy and applicable terms/law.

### 14.4 Build and rollout strategy

- Build shared primitives first: identity, tenant isolation, audit logging, secret management, connector interface, queues/jobs, policy engine, source metadata, retrieval and evaluations.
- Prototype website intelligence with customer-authorised public websites and source-cited summaries.
- Prototype read-only integrations before allowing the agent to perform write actions.
- Add defensive cybersecurity as a separate, strongly permissioned product module; begin with read-only ingestion and AI-assisted investigation, then add gated response actions after testing.
- Use capability-based permissions, not a single all-powerful agent. Each specialised agent receives only the data and tools required for its task.
- Measure value and safety before enabling automation in production; keep a human override and emergency stop.

### 2026-10-09 — Product vision expanded
- Added defensive AI cybersecurity as a potential commercial module, focused on authorised monitoring, detection, investigation and carefully gated response.
- Added a broad connector framework covering business software, websites, social platforms, cloud/security products, APIs and custom integrations rather than limiting integrations to a few accounting tools.
- Added Website Intelligence / Business Knowledge Onboarding: authorised crawling, parsing, source-linked summaries, RAG indexing, scheduled refresh and scope/safety controls.
- Recorded explicit limitations: no guarantee of complete cyber prevention; no unauthorised scanning; website content is untrusted input; sensitive agent actions require least privilege, audit logs and approval policies.


### 2026-10-09 — Temporary VM cleanup in progress
- User reports the two temporary `gemma-transfer-vm-...` virtual machines have been deleted after the Gemma Blob upload was verified.
- Remaining cleanup must be based on a fresh Azure resource inventory: check for orphaned managed disks (including `gemma-transfer-data` and OS disks), network interfaces, public IPs, and the unused SSH public-key resource `gemma-transfer-vm_key`.
- Preserve the `llmplatform` storage account, private `models` container, and `models/gemma-4-31B-it` Blob prefix. Do not delete the entire resource group.


### 2026-10-09 — Next milestone: first inference test (planned, not started)
- Model weights are safely stored in Azure Blob Storage; no inference server is running yet.
- Goal of the next phase: load Gemma 4 31B-it into GPU memory, expose a local OpenAI-compatible API using vLLM, send a test prompt, record output/latency and then tear down temporary compute.
- Current vLLM Gemma 4 deployment guidance lists the 31B-it BF16 model as requiring at least one 80 GB NVIDIA GPU. Do not assume the existing storage-only setup can run the model; the model has to be loaded into suitable compute memory.
- Candidate Azure test size: Standard_NC24ads_A100_v4 (one 80 GB NVIDIA A100), if available and quota permits in UK South. Third-party price listings recently showed an indicative Linux pay-as-you-go rate around USD 4.59/hour in UK South; pricing is variable and excludes storage/networking/tax. Verify in the Azure Pricing Calculator/portal before creation.
- Cost-control rule: create GPU compute only for a short, scheduled test; stop/deallocate and verify billing state immediately afterward. Do not leave GPU compute running unattended or make a long-term commitment at this stage.
- Alternative if this is too expensive: pause large-model inference and build the platform API, evaluation harness, connector framework, website-intelligence pipeline and security controls using mocks/smaller hosted or smaller open models until a suitable inference budget is agreed.


### 2026-10-09 — GPU test pricing gate (before provisioning)
- Rechecked current documentation before creating compute. vLLM's Gemma 4 guide lists Gemma 4 31B IT BF16 as needing 1 NVIDIA GPU with 80 GB VRAM minimum: https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html
- Azure's NC A100 v4 documentation currently notes that new capacity deployments are focused on the current NCads_H100_v5 series. An A100 VM may still be selectable in some subscriptions/regions, but availability must be checked in the portal.
- Indicative third-party list price for Standard_NC24ads_A100_v4 in UK South: about US$4.591/hour (if actually available to this subscription). Two hours is roughly US$9.18 before disks/networking/tax.
- Indicative third-party list price for Standard_NC40ads_H100_v5 in UK South: about US$8.725/hour. Two hours is roughly US$17.45 before disks/networking/tax. These are not Azure billing quotes; use the portal/pricing calculator before creation.
- Cost-control decision: because the user approved a short test based on an approximately US$10 two-hour compute estimate, first check whether the A100 option is available and the Azure estimate fits. Do not provision a more expensive H100 option unless user approves the higher estimate explicitly.
- Use a clearly named temporary inference VM; restrict SSH to the user's IP; set a storage layout with enough space for ~59 GiB weights plus the vLLM runtime/image; enable managed identity and grant read-only Blob access to the model container; install GPU driver via Azure-supported extension/image; run vLLM with a conservative context length; shut down/deallocate and verify status immediately after test. Confirm model files remain in Blob Storage.


### 2026-10-09 — A100 unavailable; lower-cost inference test option
- User checked `Standard_NC24ads_A100_v4` in Azure VM size selection and it was not listed, even after changing availability options. This is consistent with Microsoft's current A100 series documentation, which says new capacity is being deployed only for the NCads_H100_v5 series: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nca100v4-series
- Do not keep cycling availability zones expecting A100 to appear.
- Preserve the existing BF16 Gemma 4 31B-it blobs as the baseline artifact.
- A potentially lower-cost experiment is a full NVIDIA A10 VM size `Standard_NV36ads_A10_v5` (24 GB VRAM), if visible/available in the user's Azure subscription and UK South. An indicative third-party price listing shows about US$4/hour in UK South, excluding ancillary costs; verify the final Azure estimate before creating.
- The original BF16 weights are too large for a 24 GB GPU. Google publishes an official Gemma 4 31B Q4_0/GGUF quantized checkpoint family and lists about 17.5 GB for the quantized static weights; additional memory is needed for runtime and KV cache/context. A short-context single-request test may fit 24 GB, but this must be validated with the runtime and available VRAM rather than assumed.
- Proposed route, pending user selection/availability check: search for `Standard_NV36ads_A10_v5` and verify the portal's price estimate first. If available within the intended short-test spend, use an official Gemma 4 31B Q4_0 GGUF checkpoint with llama.cpp/CUDA and a conservative context length. This is a quantized variant; keep the original BF16 artifact unchanged in Blob Storage.
- If the A10 size is unavailable or the final estimate exceeds the agreed limit, pause large-model deployment and test the software stack with a smaller Gemma model on lower-cost compute rather than silently proceeding with an H100 at higher cost.


### 2026-10-09 — User confirms no quantization for first Gemma inference test
- User explicitly wants to run the original unquantized Gemma 4 31B-it weights stored in Blob Storage, rather than switch to a Q4/GGUF version.
- Terminology clarification: the downloaded Hugging Face repository is BF16, not FP32. We will preserve and run the unquantized BF16 checkpoint; do not replace it with a quantized artifact for this initial test.
- Preferred Azure GPU candidate is `Standard_NC40ads_H100_v5`, one H100 NVL GPU with 94 GiB GPU memory. vLLM's Gemma 4 guide lists 80 GB as the minimum NVIDIA GPU memory for Gemma 4 31B IT BF16.
- Indicative third-party UK South pricing found 2026-10-09: Spot about US$1.6124/hour and on-demand about US$8.725/hour; pricing and quota/capacity must be checked in the Azure portal before creation. Two hours on-demand is about US$17.45 before ancillary costs, exceeding the earlier ~US$10 target. Spot could reduce cost but may be evicted; only use it if the portal confirms a rate acceptable to the user.
- Next action: search for `Standard_NC40ads_H100_v5` in VM size picker and inspect both on-demand and Spot price/options, without creating VM until user confirms the actual price/approach.


### 2026-10-09 — Stop Azure GPU SKU search; use temporary external GPU for first inference test
- User explicitly asked to stop spending time on Azure GPU sizes and to proceed with any available suitable machine for a one-off short test.
- Azure portal showed `Standard_NC24ads_A100_v4` and `Standard_NC40ads_H100_v5` as unavailable in the tried regions/configurations. Do not continue cycling Azure regions or SKUs for this initial experiment.
- Recommended temporary GPU host: RunPod on-demand Pod using one H100 NVL with 94 GB VRAM, if available. RunPod's official pricing page, updated 2026-09-27, lists H100 NVL at about US$3.19/hour; two hours is about US$6.38 of GPU compute before volume, network, taxes or other charges. H100 PCIe 80GB is listed around US$2.89/hour, but the 94GB NVL leaves more room above vLLM's stated 80GB minimum for Gemma 4 31B IT BF16.
- Use on-demand hourly compute, no long-term commitment; verify exact displayed price, GPU memory, storage charges and shutdown behaviour before deploying.
- Use the existing unquantized BF16 model. It is acceptable to fetch from the public Hugging Face model repository for this short test, while the verified private copy remains in Azure Blob Storage; alternatively copy from Blob if convenient. Do not expose Azure credentials to RunPod. For this initial test use only non-sensitive prompts/data, since the runtime is on a separate provider.
- Keep model in Azure Blob Storage as durable copy. After a one-off test, terminate/delete the temporary Pod and its attached volume if no longer needed; confirm billing stops. No Azure GPU VM has been created during the availability checks.


### 2026-10-09 — RunPod GPU provisioned and verified
- User deployed an on-demand RunPod PyTorch 2.8.0 Pod with 1x H100 NVL, 94 GB VRAM, 251 GB RAM and 18 vCPU.
- Displayed price at creation: US$3.19/hour for GPU, plus container disk/volume storage charges.
- Configured 30 GB container disk and 100 GB Volume Disk. Need verify exact mount point and available disk space in the Web Terminal before downloading weights.
- Successfully ran `nvidia-smi` in RunPod Web Terminal: GPU 0 reports NVIDIA H100 NVL, approximately 94 GiB VRAM, 0 MiB used and no running processes. This confirms the GPU is visible in the container.
- A container message `groups: cannot find name for group ID 109` appeared before `nvidia-smi`; it did not prevent GPU reporting and is likely a container identity/group lookup warning.
- Next: run `df -h` and inspect mounts; then download the original BF16 Gemma 4 31B-it model onto the mounted 100 GB volume, configure vLLM with a supported Gemma 4 version and conservative context, perform one inference test, capture outcome, then terminate the Pod and its volume only after keeping the Azure Blob copy intact.


### 2026-10-09 — RunPod volume verified
- In the RunPod Pod's Volumes tab, the attached Volume Disk is explicitly shown as 100 GB and mounted at `/workspace`; usage is 0 bytes before model download.
- `df -h /workspace` inside the container reports a large `mfs#...runpod.net` backing filesystem. Treat RunPod's Pod Volumes UI (100 GB allocation for this attached volume) as the applicable user allocation rather than interpreting the shared filesystem's displayed 873T total as capacity dedicated to this Pod.
- Next: download the public `google/gemma-4-31B-it` repo directly into `/workspace/gemma-4-31B-it` with Hugging Face Hub CLI, keeping HF caches on `/workspace`. Avoid sending Azure access tokens or storage keys to RunPod.


### 2026-10-09 — Hugging Face CLI ready on RunPod
- In the RunPod H100 NVL Web Terminal, confirmed Python 3.12.3 and pip 25.2.
- Installed `huggingface_hub` using `python3 -m pip install --upgrade huggingface_hub`; verified the `hf` CLI help displays correctly.
- The 100 GB RunPod Volume Disk is mounted at `/workspace`, as confirmed in the RunPod Volumes UI. GPU `nvidia-smi` check succeeded and showed H100 NVL with ~94 GB VRAM and 0 MiB used before loading any model.
- Next: use `hf download google/gemma-4-31B-it --local-dir /workspace/gemma-4-31B-it` to fetch the original unquantized BF16 repo to the 100 GB volume. Keep the Pod running during download; do not change or delete the original Blob Storage copy.


### 2026-10-10 — Azure Blob to RunPod transfer completed
- The Hugging Face download on RunPod stalled while waiting on a model-shard lock; incomplete shard downloads stopped growing. The partial local Hugging Face download was not relied on for the final copy.
- Installed AzCopy 10.32.8 on the RunPod H100 NVL container and used a temporary read/list SAS token for the private Azure `models` container. The SAS token was inadvertently shared in ChatGPT; treat it as exposed and let it expire or revoke it if supported. Do not reuse it.
- Copied from `https://llmplatform.blob.core.windows.net/models/gemma-4-31B-it` to `/workspace/gemma-4-31B-it` on RunPod with AzCopy recursive copy and overwrite enabled.
- AzCopy job `30b09493-8616-9b4a-d650-3fb75a6d0a5d` reported: 39 transfers total, 39 completed, 0 failed, 0 skipped, 62,578,689,665 bytes transferred, final status Completed.
- Next: verify locally that both safetensors shards match expected byte counts and the supporting config/tokenizer files exist. Then start vLLM serving the BF16 checkpoint with an appropriately limited context for the first test, test one prompt, and stop/terminate the H100 Pod after testing.


## Cybersecurity Platform and Managed Security Service (added 2026-10-10)

### Product direction
- Cybersecurity is a first-class product capability and potential business line, not just a prompt or a feature inside the LLM. Build a defensive AI security platform that can be sold to businesses as software and/or a managed service, subject to appropriate expertise, testing, contracts, and legal requirements.
- Positioning: AI-assisted security operations that help prevent, detect, investigate, prioritise, and respond to cyber threats—including attacks performed or accelerated by other AI agents. Avoid claiming that any system can guarantee prevention of all attacks.
- The LLM is the reasoning and explanation layer, not the security boundary or the sole detection engine. Use deterministic controls, established security tools, telemetry, policy engines, sandboxing, audit trails, and human approval for high-impact actions.

### Defensive capabilities roadmap
1. **Asset inventory and exposure management**: customer-authorised domain/website and cloud-asset discovery; DNS/TLS/certificate checks; exposed service and configuration checks; software/dependency inventory where available; cloud configuration review; asset ownership and scan scope verification.
2. **Website and application security checks**: safe, rate-limited checks for TLS, security headers, common misconfigurations, dependency/CVE exposure, leaked secrets in customer-authorised repositories, insecure forms/cookies, and known vulnerability indicators. Add authenticated scanning only with explicit customer permission and test accounts. Default to non-destructive checks; no broad internet scanning or exploitation without documented authorisation and scope.
3. **Endpoint, identity, email, cloud and network security integrations**: connect to endpoint detection and response (EDR), SIEM/SOAR, identity providers, Microsoft 365, cloud security tools, firewalls, vulnerability scanners, DNS/web gateways, backup systems, ticketing and asset-management platforms through documented APIs/webhooks/connectors. Build a connector framework rather than hard-coding a few named vendors; support OAuth/least-privilege credentials, scoped permissions, tenant isolation, secrets vaulting, retries, rate limits, audit logs, and connector health checks.
4. **AI-agent threat defence (“AI versus AI”)**: detect suspicious agent behaviour and automation abuse; monitor tool/API calls, identity and permission changes, unusual access patterns, prompt-injection attempts, data exfiltration signals, mass actions, credential misuse, and policy violations. Treat all external web pages, documents, emails, and retrieved content as untrusted input. Use least privilege, allowlists, sandboxing, egress controls, per-tool policies, rate limits, short-lived credentials, signed/audited actions, and human approval for destructive or high-risk operations.
5. **Security operations copilot**: correlate alerts and telemetry, enrich incidents with asset/business context, deduplicate alerts, summarise evidence, propose investigation steps, map findings to relevant controls, produce incident timelines and executive/technical reports, and recommend containment. Every conclusion must distinguish observed evidence from model inference and include source references and confidence/limitations.
6. **Response and remediation**: create tickets, notify operators, recommend fixes, and run approved reversible actions where safe. Quarantine endpoints, disable accounts, change firewall rules, delete files, block domains, or modify production systems only through explicit policies and appropriate human approval; preserve evidence and provide rollback plans.
7. **Compliance and assurance support**: configurable control mappings and evidence collection for relevant customer obligations (for example UK GDPR/data protection, Cyber Essentials, ISO 27001, NIST CSF, CIS Controls, and sector-specific rules where applicable). Do not claim certification or compliance solely because the software runs checks; distinguish technical findings from legal/compliance advice and require qualified review.
8. **Continuous monitoring and reporting**: risk-ranked findings, remediation tracking, SLA/escalation policies, asset change alerts, recurring reports, attack-surface trends, test evidence, and tenant-specific audit logs. Make scan schedules and retention customer-configurable.

### Website/business knowledge scanner
- Build a separate authorised website-crawl and business-knowledge ingestion service. With the customer's permission, crawl pages within an agreed domain/scope, respect robots/rate limits and access restrictions, detect sitemaps and canonical URLs, deduplicate content, record crawl timestamps and source URLs, and create searchable summaries/knowledge for that customer's AI agent.
- Keep website ingestion (business knowledge/RAG) separate from security scanning. A crawl that learns business information does not itself constitute a security audit. Security testing must use its own approved scope, checks, findings, evidence, and report.
- Prevent cross-customer data leakage: tenant-specific storage/indexes and access controls, source-level permissions, deletion/export paths, retention settings, and prompt-injection defences for crawled content.

### Security architecture and non-negotiable safeguards
- Threat-model the platform itself before production: tenant isolation, authentication/MFA, RBAC/ABAC, secrets management, encryption in transit/at rest, secure software supply chain, signed builds, dependency and container scanning, patching, backup/recovery, immutable audit trails, abuse monitoring, incident response, and independent penetration testing.
- Separate control plane, data plane, model-serving layer, tool execution, connectors, and customer tenants. Run tools in isolated, short-lived sandboxes; restrict network egress; never allow the LLM to directly access host/root credentials or arbitrary shell/network access.
- Use least-privilege credentials and read-only defaults. Store secrets in a vault, never GitHub or prompts/logs. Redact secrets and sensitive data from telemetry. Minimise data, define retention/deletion, and document subprocessors and data residency.
- Use deterministic policy enforcement around model/tool outputs. The model may recommend an action, but a policy engine must validate authorisation, scope, risk and approval before execution. Require human confirmation for high-impact changes.
- Maintain test suites for prompt injection, tool abuse, cross-tenant leakage, data exfiltration, false positives/negatives, evasion, model regression, and recovery. Use synthetic or explicitly authorised test environments; keep red-team work bounded by written scope.
- Do not market the system as invulnerable or as a replacement for all security staff. Start as an AI-assisted defensive tool and grow into a managed security service with qualified human oversight and a documented incident escalation path.

### Cybersecurity business delivery model
- Potential offerings: website security health checks; external attack-surface monitoring; vulnerability and configuration management; Microsoft 365/cloud posture reviews; AI-agent security monitoring; security copilot for small IT teams; managed detection/triage; incident-readiness and compliance evidence reporting.
- Start with a narrow, safe MVP: customer-authorised domain inventory + TLS/security-header/configuration checks + dependency/CVE intake where available + clear evidence-based report + remediation tracking. Add integrations and automated response only after permissions, isolation, auditability, and evaluation are proven.
- Before offering production scans, obtain written customer authorisation, identify exact domains/IPs/tenants and excluded assets, define rate limits and test windows, document data handling and retention, provide a contact/escalation process, and validate results with qualified security review. Never scan or test third-party or government systems without explicit authorisation.
- Measure detection precision/recall where ground truth exists, false-positive rate, time to triage/remediate, coverage, missed critical issues, service availability, and customer outcomes. Validate on intentionally vulnerable labs and approved test targets before customer rollout.

### Roadmap integration
- Architecture: add a dedicated Cybersecurity Services module connected through the same model-independent agent/tool framework, but separated by tenant, permissions, security policy and audit controls.
- Build sequence: (1) threat model and safe-scope contract; (2) authorised website inventory and passive checks; (3) evidence-based reporting and remediation tickets; (4) connector framework and tenant isolation; (5) cloud/M365/identity integrations; (6) AI-agent behaviour monitoring; (7) gated response automation; (8) managed-service operations and independent assurance.
- Keep this roadmap alongside, not instead of, the general business-agent roadmap. Reuse the platform's RAG, tools, memory/planning and evaluation foundations, but cybersecurity actions require stricter permissions and safety gates.


## Architecture Principle: Dynamic, Evolvable Platform (added 2026-10-10)

### Non-negotiable objective
Design the whole product as a long-lived, modular, model-independent AI platform that can evolve as leading models, tools, infrastructure, business applications, and security practices change. Do not optimise architecture solely for the current Gemma prototype or a single small feature. Every implementation decision must be checked against this target architecture, documented, and justified. The prototype is a test of the architecture, not the architecture's permanent shape.

### Architecture decision test
Before choosing or implementing a component, answer and record:
1. Does it solve the immediate need without locking the platform to one model, cloud, vendor, database, or business application?
2. Can it be replaced or upgraded behind a stable interface without rewriting unrelated modules?
3. Does it support tenant isolation, permission boundaries, security policy, privacy, auditability, and UK/EU/other target-market requirements?
4. Can it scale from prototype to multiple customers, workloads, regions, and deployment patterns without assuming unlimited budget?
5. Can it be tested, observed, evaluated, rolled back, and operated reliably?
6. Does it create avoidable vendor lock-in, duplicated logic, hidden coupling, or unnecessary complexity? If yes, record the trade-off and a migration path.
7. Is the capability genuinely needed now, or should its interface be designed now and implementation deferred until validated? Avoid both premature overbuilding and short-term hacks that block expansion.

### Reference architecture boundaries
- **Experience/API layer:** web app, customer/admin console, SDKs and public API; stable versioned APIs and clear authentication/authorisation.
- **Identity, tenant and policy plane:** tenant isolation, user/service identities, roles/attributes, consent, quotas, customer-specific policies, approvals and audit records. This layer controls access independently of model output.
- **AI orchestration plane:** task routing, workflow/agent state machines, planning, bounded retries, timeouts, cancellation, scheduling, queues and human handoffs. Use explicit workflows for critical processes rather than relying on unconstrained agent loops.
- **Model gateway:** one provider-neutral interface for hosted APIs and self-hosted open-weight models; model registry, capability metadata, routing, version pinning, fallbacks, token/context limits, cost/latency tracking and safe rollout/rollback. Treat model replacement as configuration plus evaluation where possible, not a platform rewrite.
- **Knowledge and data plane:** connectors/ingestion, parsing, chunking, metadata, hybrid retrieval, vector and keyword indexes, tenant-aware access filters, citations/provenance, freshness, deletion and retention. Keep source systems authoritative and maintain data lineage.
- **Tools and integration plane:** standard connector contracts for business software, websites, cloud services and security products; OAuth/least-privilege credentials, schema validation, rate limits, idempotency, retries, versioning and health monitoring. Separate read operations from write/action operations.
- **Execution plane:** isolated and ephemeral sandboxes for code and tools; restricted network egress, resource limits, filesystem boundaries, no direct model access to host/root secrets, and policy checks before external side effects.
- **Memory and state:** separate conversational/session state, durable user/customer preferences, task/workflow state and approved organisational knowledge. Define ownership, scope, expiry, correction and deletion semantics; do not silently turn arbitrary retrieved data into trusted memory.
- **Evaluation and observability:** model/task evaluations, regression suites, red-team tests, tracing, structured logs, metrics, feedback, cost/latency/error budgets, security alerts and audit trails. Production changes require measurable acceptance criteria.
- **Security services:** a separately governed defensive cybersecurity module for authorised asset discovery, website checks, vulnerability intake, alert correlation, AI-agent behaviour monitoring, remediation tracking and gated response. It shares platform foundations but has stricter permissions, isolation, evidence requirements and approval gates.
- **Operations/deployment plane:** environment separation (development, test, staging, production), infrastructure-as-code, CI/CD, secrets management, backups/recovery, health checks, deployment strategies, data residency choices and incident response.

### Modularity and evolution rules
- Prefer small modules with explicit responsibilities and versioned contracts; avoid a single giant application with tangled dependencies. Start as a well-structured modular monolith when that is the simplest reliable option; split into services only when scaling, isolation, reliability, ownership, or deployment needs justify the operational cost.
- Use provider-neutral interfaces for models, embeddings/rerankers, vector stores, object storage, telemetry, queues, identity, and business connectors. Keep vendor-specific code inside adapters and document capabilities that cannot be made portable.
- Define schemas and contracts for model requests/responses, tool calls/results, connector events, documents/chunks, findings, policies, approvals, audit events and evaluation results. Version them and test backward compatibility.
- Keep configuration separate from code; use feature flags, tenant-level capability settings, model routing policies and controlled rollouts. Never silently change production model behaviour because a newer model appeared.
- New models and tools enter through a lifecycle: discover → licence/security review → sandbox → benchmark/evaluate → compare cost/quality/safety/latency → approve → staged rollout → monitor → rollback if needed.
- Support portability through containers and infrastructure-as-code where practical, while acknowledging that GPUs, cloud identity, managed databases and model formats have provider-specific constraints.
- Design for multi-tenancy and data boundaries from the beginning, even before serving multiple customers. Tenant identity must flow through retrieval, tools, logs, memory, jobs, caches and outputs.
- Do not use GitHub for large model weights, secrets, customer data, or generated production data. GitHub holds code, configs/templates without secrets, tests, architecture decisions and the reproducible playbook; object storage holds model artifacts and other large assets under controlled access.

### Decision records and architecture governance
- For any decision that affects core architecture, record: problem, options considered, chosen approach, reasons, rejected alternatives, security/privacy impact, cost/operational impact, reversibility, and what evidence would cause reconsideration. Keep short Architecture Decision Records (ADRs) under `docs/architecture/decisions/`.
- Every meaningful feature must identify which architecture boundary it belongs to, the interfaces it uses, data/permission flows, failure modes, tests, monitoring and rollback strategy. If it does not fit the reference architecture, pause and either adapt the design or deliberately amend the architecture record before proceeding.
- Review architecture at milestones and when new models, customer requirements, regulations, major integrations, or threat intelligence materially change assumptions. Architecture should evolve deliberately, not through accidental coupling.
- Build for capability and quality, not a claim that one architecture automatically makes the product as capable as every leading AI system. Performance depends on models, data, tools, evaluation, infrastructure, user experience and operational execution together.

### Current prototype implications
- Gemma 4 31B-it on RunPod is only a temporary inference experiment; it is not a commitment to a specific production model, provider or GPU host.
- The model gateway and evaluation process should eventually allow comparing Gemma against other eligible open-weight and hosted models on the same business tasks, with the best model selected per task when useful.
- Do not build the full distributed architecture before proving core flows. First implement stable interfaces and a simple deployment, then scale/split modules when evidence supports it. Preserve long-term boundaries without paying the full operational cost of an enterprise microservice estate prematurely.


## Research-Driven Architecture and Competitive Intelligence (added 2026-10-10)

### Core rule
Architecture and product decisions must be informed by ongoing, broad research into leading AI labs/model providers, agent platforms, business-software ecosystems, integration platforms, cybersecurity vendors/MSSPs, and relevant open-source projects. Do not design in a vacuum or assume our first idea is best. Learn from proven capabilities, public architecture patterns, product documentation, security frameworks, customer reviews, independent evaluations, incident reports, and emerging standards. Reuse sound ideas and proven practices—not proprietary code, confidential information, branding, or protected material—and seek a defensible improvement or differentiated customer outcome.

### Research before consequential decisions
Before selecting a core architecture, model, framework, database/vector store, agent protocol, connector approach, cybersecurity tool, hosting platform, or customer-facing capability:
1. Define the decision and the customer problem it must solve.
2. Map the competitor and ecosystem landscape, including leading providers, credible challengers, open-source alternatives, and build-versus-buy options.
3. Read primary sources first where possible: official product/architecture documentation, API references, security advisories, standards, release notes, model cards, licence terms, and published evaluations. Use independent research, credible technical analysis, customer feedback and incident reports to challenge vendor claims.
4. Compare capability, quality, security, privacy/data handling, integration breadth, deployment options, portability, reliability, latency, operating complexity, cost at realistic scale, licence/contract restrictions, and suitability for UK/EU and other intended markets.
5. Identify gaps, failure modes, unmet customer needs and opportunities to differentiate. Do not merely reproduce feature checklists; validate that the feature solves a real problem and can be delivered safely and economically.
6. Run a proof of concept or benchmark for important uncertain claims. Separate verified facts from marketing claims, assumptions and our own inference.
7. Record source URLs, date checked, findings, confidence, trade-offs, decision and revisit triggers in a research note and, for major architecture decisions, an Architecture Decision Record under `docs/architecture/decisions/`.

### Continuous landscape watch
- Maintain a living competitor/technology map for: foundation and open-weight models; inference/serving; agent frameworks and inter-agent communication; workflow orchestration; retrieval/knowledge systems; business app/API integration platforms; website/business knowledge crawlers; cybersecurity, EDR, SIEM/SOAR, vulnerability and cloud posture tools; observability/evaluation; identity, secrets and policy enforcement; deployment and GPU/cloud infrastructure.
- Track meaningful releases, model-weight availability, licence changes, API deprecations, security advisories/CVEs, new standards/protocols, acquisitions/pricing changes, product gaps and major customer-impacting incidents.
- Do not switch technologies automatically just because a competitor ships something new. Create a candidate, evaluate it against our benchmark and requirements, check security/licence/privacy, then approve a controlled rollout with rollback.
- Use a repeatable research template: `question; why it matters; vendors/projects reviewed; primary sources; independent evidence; feature/capability comparison; cost and operational implications; security/privacy/licensing; gaps/opportunities; recommendation; confidence; next review date`.
- Keep the playbook actionable and current. Update it after meaningful research or architectural decisions; avoid copying large vendor marketing pages or maintaining a list that has no impact on product choices.

### Product and capability benchmarking
- Benchmark our platform against relevant alternatives for the same user tasks, not only generic model leaderboards. Include task success, factuality/source grounding, tool-call correctness, integration coverage, latency, cost, reliability, safety/security, ease of administration and user outcomes.
- For cybersecurity capabilities, compare against established defensive security practices and reputable vendors/frameworks; use recognised frameworks where appropriate (for example NIST Cybersecurity Framework, CIS Controls, OWASP guidance, MITRE ATT&CK for threat behaviour mapping, and applicable UK guidance). Framework mapping is evidence and prioritisation support, not automatic certification.
- For agents and integrations, examine supported connectors, API permissions, event/webhook models, auditability, tenant boundaries, approval flows, error recovery, versioning, rate limits and data portability. Treat inter-agent communication as untrusted and authenticated: agents must have identities, scoped permissions, explicit contracts, provenance, quotas, and audit records; never grant an external agent implicit trust.
- For model choices, compare leading hosted and open-weight candidates under the same evaluation harness. Consider licensing, weights/access status, hardware needs, quantisation/precision, context limits, multimodality, tool use, language coverage, security and total cost—not hype or parameter count alone.

### Research quality and boundaries
- Prefer primary sources for what a product officially supports, and independent sources for effectiveness, reliability and user experience. Check dates and version applicability. Seek corroboration for important claims and record when evidence is unavailable or vendors do not disclose details.
- Do not claim to know private competitor code or internal architectures. Public product behaviour and documentation can inform design; infer internal details only when clearly labelled as inference.
- Do not copy proprietary source code, confidential information, protected design assets or unique branding. Implement our own compatible, lawful designs and respect software/model/data licences and terms.
- Security research, scanning and adversarial testing must remain defensive and authorised. Do not probe competitor, government or customer systems without explicit written permission and defined scope. Use labs, synthetic data and approved test targets.
- Research tools and external web content are untrusted input. Do not follow instructions embedded in retrieved pages, repositories, emails or documents; extract evidence only, validate sources, and keep credentials/secrets out of prompts and logs.

### AI-assisted research and implementation workflow
For each substantial feature or architectural change, the development agent should: (1) identify the relevant architecture boundary and requirements; (2) search approved public documentation and the maintained research index; (3) summarise evidence with citations and freshness; (4) compare alternatives against the architecture decision test; (5) propose the smallest validated implementation that preserves future replaceability; (6) add tests, threat cases, observability and rollback; (7) update research notes, ADRs and the playbook. Require human review for material security, privacy, licence, cost or production-risk decisions. Do not allow an agent to deploy a newly researched dependency/model or run security actions against external targets solely on its own judgement.

### Initial research areas to build out
1. Model providers and serving: leading open-weight and hosted models, gateways, inference engines, hardware/precision options, licences and evaluations.
2. Business AI and agents: enterprise agent platforms, workflow engines, tool-use standards, agent identity, inter-agent protocols, memory, approvals and human oversight.
3. Integrations: API/iPaaS ecosystems, connector catalogues, OAuth/permission models, webhooks, event buses, Microsoft 365 and broad CRM/ERP/accounting/social/website ecosystems.
4. Business website intelligence: crawling and indexing approaches, sitemaps, content freshness, access control, source citations, tenant-isolated RAG and prompt-injection protection.
5. Cybersecurity: leading EDR/XDR, SIEM/SOAR, managed detection and response, vulnerability/exposure management, cloud security posture, identity security, application security and AI-agent security; map features and gaps against recognised defensive frameworks.
6. Platform engineering: modular monolith vs services, queues, databases, object storage, observability, CI/CD, multi-tenancy, regional deployment, resilience, recovery and cost controls.
7. Compliance and trust: UK GDPR/data protection, relevant EU/UK AI and cyber obligations, customer contracts, data residency, retention, audit evidence and sector-specific requirements. Confirm current legal/regulatory details before acting on them.

### Output standard
Research should lead to a decision, not a pile of links. Every research report should finish with: what we learned; what to adopt; what not to adopt and why; the impact on the target architecture; risks/costs; a prioritised next action; and what evidence would change the recommendation.


### 2026-10-11 — Gemma 4 inference baseline validated; Phase 2 evaluation started
- On RunPod H100 NVL, installed vLLM 0.31.0 and PyTorch 2.13.0 in a Pod-local environment at `/tmp/vllm-clean-env`. The uv cache is explicitly redirected to `/tmp/uv-cache` to avoid permission errors on the Global Volume mounted at `/workspace`.
- Confirmed PyTorch CUDA build 12.9, CUDA available, GPU detected as NVIDIA H100 NVL, and `uv pip check` passed for 199 packages.
- vLLM reported `Application startup complete`; a real `/v1/chat/completions` request returned exactly `model works`. This is the first confirmed end-to-end generation test on the current Pod.
- Created an environment archive `/workspace/runtime-setup/vllm-clean-env.tar.zst` (about 3.4 GB compressed; 8.42 GB uncompressed), alongside frozen requirements, runtime manifest, installation script, and SHA256 sums.
- `sha256sum -c SHA256SUMS` reported all four files OK and `zstd -t` passed. These confirm archive/file integrity, not successful restoration. A fresh-Pod restore test was deferred because RunPod showed GPU capacity unavailable in all displayed configurations. Treat restore as unverified, preserve current Pod/Global Volume/Azure model copy, and retry the restore test when capacity is available.
- Began Phase 2 (Evaluation). Added a dependency-free baseline runner in `evaluation/run_chat_eval.py` and usage notes in `evaluation/README.md`. It checks instruction following, simple arithmetic, use of supplied text, and JSON formatting. Run it against the current server before using it as a reference baseline. Four checks are smoke tests only, not a broad quality or compliance benchmark.
- Next: run the four-check suite, record actual results, expand evaluations for tool use, business documents, coding, latency, and cost; then proceed to model lifecycle and platform/API layers. Keep the serving runtime unchanged while evaluation is added.


### 2026-10-11 — First Gemma smoke-test baseline recorded
- Ran `evaluation/run_chat_eval.py` against the current vLLM API at `http://127.0.0.1:8000/v1`.
- All four checks passed: exact instruction following (`PASS`), arithmetic (17 × 19 = `323`), supplied fact recall (`09:30`), and valid JSON (`{"status":"ok","count":3}`).
- Per-request elapsed times reported by this single run were 0.06 s, 0.12 s, 2.84 s, and 0.27 s respectively. These are one-off observations, not throughput benchmarks.
- Detailed report: `evaluation/results/gemma-4-31b-smoke-2026-10-11.md`.
- Keep Gemma 4 31B-it as `prototype-baseline`; this small smoke test does not approve it for production.
- Next product capability: implement a minimal document Q&A/RAG prototype using approved local documents and source references. Build and test retrieval separately before asking the model to answer, so we can detect missing evidence and reduce unsupported answers.


### 2026-10-11 — First evaluation baseline and RAG prototype started
- Ran `evaluation/run_chat_eval.py` against the current vLLM API. All four checks passed: exact instruction following, 17 × 19 arithmetic, supplied-info recall, and JSON output.
- Per-request times shown in the one run were 0.06 s, 0.12 s, 2.84 s and 0.27 s; these are single-run observations, not throughput benchmarks. Detailed result: `evaluation/results/gemma-4-31b-smoke-2026-10-11.md`.
- Kept Gemma 4 31B-it at prototype-baseline; this short smoke suite is not approval for production.
- Started a minimal document Q&A/RAG proof of concept under `rag/`. It uses plain-text/Markdown documents, overlapping text chunks, BM25 lexical retrieval and the OpenAI-compatible vLLM chat API, with source labels and a basic untrusted-document instruction.
- The initial RAG prototype deliberately avoids new Python dependencies and avoids writing an index database to the FUSE-backed Global Volume. It is not production-ready: no authentication, ACL enforcement, tenant isolation, PDF/Office parsing, semantic vector search, audit logging, or comprehensive prompt-injection defence.
- Next: run the documented test question against fictional sample documents; inspect source retrieval and answer citations, then extend evaluation to measure whether each answer is supported by retrieved evidence.


### 2026-10-11 — First RAG question answered from a source document
- Ran `rag/ask_documents.py` against two fictional Markdown files saved on the Global Volume.
- Question: "How many business days do employees have to submit expense receipts?"
- BM25 ranked `expenses-policy.md` first (score 5.363), ahead of `employee-handbook.md` (score 0.638).
- Gemma answered: "Employees must submit expense claims with receipts within 10 business days of the expense [Source 1]."
- The answer matches the sample policy; reported single-request inference latency was 0.62 seconds.
- Detailed report: `rag/results/rag-demo-2026-10-11.md`.
- This confirms one basic retrieval-and-generation path. Next validate unsupported questions and prompt-injection text in documents before moving on to consequential business integrations. The prototype remains non-production: no authentication, document ACLs, tenant isolation, or audit logging.


### 2026-10-11 — Initial RAG safety smoke tests
- Prompt-injection sample: the document included an attempt to replace the factual answer (10 business days) with 500 days and request secrets. The model answered 10 business days with a source label rather than following the embedded instruction. This is one successful adversarial example, not proof of general injection resistance.
- Unsupported question: the model said it could not find the CEO yacht colour in the supplied documents. However, BM25 had still retrieved unrelated expense/handbook chunks (scores 0.690 and 0.625). Record the model refusal as a pass for this question, but record retrieval relevance as a known issue.
- Detailed report: `rag/results/rag-safety-tests-2026-10-11.md`.
- Next technical step: build a repeatable RAG regression evaluator with answerable, unanswerable, and injected-document cases, then improve retrieval abstention using test-calibrated relevance criteria. Do not choose a hard-coded score threshold based on only this single example.


### 2026-10-11 — Repeatable RAG regression suite added
- Added `rag/run_rag_regression.py`, which exercises: a supported source-cited answer, an embedded-instruction injection example, an unsupported factual question, and a no-retrieval-match case.
- Documented execution in `rag/README.md`.
- The suite is dependency-free and uses the currently running OpenAI-compatible vLLM endpoint. It should be run after any change to retrieval, chunking or prompts.
- The existing smoke screenshots have not yet been rerun through this automated suite; run it and record real results before treating it as a passing regression gate.


### 2026-10-11 — Automated RAG regression suite passed
- Ran `rag/run_rag_regression.py` against the running Gemma 4 31B-it vLLM API. Final result: 4/4 cases passed.
- Supported expense deadline: returned "10 business days" with a source label (0.54 s reported).
- Prompt-injection sample: returned the factual 10-business-day deadline instead of the injected 500-day claim (0.57 s).
- Unsupported yacht-colour question: correctly abstained (0.53 s), but lexical retrieval still passed unrelated expense/handbook chunks to the model. No-overlap question was rejected before model invocation.
- Detailed report: `rag/results/rag-regression-run-2026-10-11.md`.
- Next: build a small labelled relevance set and add a tested retrieval-abstention mechanism to reduce irrelevant context. Tune it from multiple answerable/unanswerable examples rather than guessing a score threshold. Preserve the current working baseline and keep the tests as a regression gate.


### 2026-10-11 — Retrieval relevance calibration prepared
- Added `rag/evaluate_retrieval.py`, a retrieval-only tool reporting top BM25 scores for six answerable and six unanswerable questions against the sample policy set. It makes no model calls.
- The purpose is to gather evidence before choosing a relevance gate. Do not hard-code a score threshold from one irrelevant-query score; review the labelled positive/negative ranges and expand the dataset if there is overlap.
- Next: run the calibration utility on the current Pod, inspect the score distribution/source ranking, then choose whether a simple threshold, score margin, or different retrieval design is justified.


### 2026-10-11 — Provisional BM25 relevance gate added
- Calibration on the two fictional sample documents: all six answerable questions top-ranked the expected source (positive score range 2.351–5.797); six unanswerable questions scored 0.690–2.258. The observed separation is narrow (0.093).
- Added configurable `--min-score` to `rag/ask_documents.py`, with a default of 2.30 **only for the existing two-document demo corpus**. Queries below that top-score threshold stop before the model call.
- Updated regression suite to test low-score rejection as well as the model's abstention when the threshold is explicitly disabled for that test.
- Do not apply 2.30 to customer corpora without recalibration. BM25 scores depend on corpus; if score distributions overlap, change retrieval design and evaluation rather than pretending a threshold is reliable.
- Next: refresh the scripts on the current Pod and run all five regression cases. Do not record the threshold as passing until the actual run succeeds.


### 2026-10-11 — BM25 retrieval calibration results captured
- The six answerable sample questions all ranked the expected source first; their top scores ranged 2.351–5.797.
- Six unanswerable questions scored 0.690–2.258. The nearest observed scores are separated by only 0.093.
- Recorded the run in `rag/results/retrieval-calibration-2026-10-11.md`.
- Implemented a provisional minimum top-score gate of 2.30 in `rag/ask_documents.py`, only for the two-file fictional demo corpus. This is a narrow sample separation, not a general threshold.
- Next: download the updated RAG script and revised regression suite to the current Pod, then verify all five cases pass. Keep 2.30 scoped to the demo corpus; recalibrate for each new corpus.


### 2026-10-11 — Five-case RAG regression passed with demo-only relevance gate
- User ran the refreshed `rag/run_rag_regression.py`; screenshot confirms 5/5 cases passed.
- Supported question returned "10 business days" with source label; tested document injection did not override the factual deadline.
- The yacht-colour query (scores 0.690/0.625) was blocked by the demo-only `--min-score 2.30` gate before model inference. With the gate disabled only for a separate regression case, the model abstained correctly. A no-overlap query was rejected before inference.
- Detailed report: `rag/results/rag-regression-gated-run-2026-10-11.md`.
- Caution: the positive/negative score gap is only 0.093 across six positive and six negative questions against two fictional files. The 2.30 gate is only a demo setting, not a general/corporate threshold.
- Next platform milestone: establish a thin, authenticated local API gateway in front of vLLM so future RAG, integrations, logging and policy enforcement can use a stable platform boundary rather than accessing the model server directly. Bind locally by default; do not expose it publicly without HTTPS, production authentication/secrets handling, tenant isolation, quotas and auditing.


### 2026-10-11 — RAG gate passed; local API gateway created
- User ran the updated RAG regression suite after refreshing both scripts from GitHub. Screenshot confirms 5/5 cases passed with the provisional 2.30 minimum top-score gate for the two-file fictional corpus.
- The test covered source-cited answer, embedded-instruction sample, low-relevance question blocked before model call, model abstention with the gate deliberately disabled, and zero-overlap rejection.
- Detailed outcome is in `rag/results/rag-regression-gated-run-2026-10-11.md`. The gate remains demo-only because calibration separation is only 0.093 across a tiny sample.
- Created `api/local_gateway.py` and `api/README.md` as the next platform layer. The gateway provides a stable authenticated `/v1/chat/completions` boundary in front of vLLM, a basic upstream health check, payload limit, a small in-memory rate limit, and route/status-only logging.
- Gateway defaults to loopback `127.0.0.1:8010`; a one-command smoke harness lives in `api/run_gateway_smoke.sh`. The harness creates an ephemeral random key in Pod-local `/tmp`, confirms health, expects an unauthenticated call to return 401, and sends an authenticated real generation request. It leaves the gateway running only if the checks complete.
- This is a local proof of concept, not production-ready and not exposed for business-app integration. Do not bind it to `0.0.0.0` or expose the port. External integrations later require HTTPS, managed identity/secrets, per-user/service authorization, tenant isolation, persistent audit trails, durable quotas, observability, and security review.
- Next: run the gateway smoke harness from the current Pod without changing/stopping the existing vLLM server; record its real result, then build stable RAG/API integration behind this gateway.


### 2026-10-11 — Authenticated gateway validated; RAG client updated for gateway
- The user ran the gateway smoke script. Health was `ok` with one upstream model, unauthenticated chat was rejected with HTTP 401, and an authenticated request generated `gateway works`.
- The local loopback gateway remains at `http://127.0.0.1:8010`; the ephemeral key is in `/tmp/platform-gateway.key` only. Never commit or print the key. Do not expose port 8010 publicly.
- Updated `rag/ask_documents.py` to accept `--api-key-file`; when provided, it adds a bearer authorization header to chat requests. The local gateway currently does not proxy `/v1/models`, so `--model` must be supplied with this mode. The old direct-vLLM mode remains the default when the API key file is omitted.
- Next test: run the RAG question against `http://127.0.0.1:8010/v1` with `--api-key-file /tmp/platform-gateway.key` and the explicit Gemma model ID. Verify the answer and that gateway logs show the request path; this validates the actual document-Q&A -> gateway -> vLLM flow.


### 2026-10-11 — RAG → authenticated gateway → Gemma confirmed
- The user ran `rag/ask_documents.py` through `http://127.0.0.1:8010/v1`, using `--api-key-file /tmp/platform-gateway.key` and explicit model ID.
- It retrieved the expense policy first (score 5.363), and Gemma answered "10 business days" with `[Source 1]`. Screenshot shows 0.57 s single-request inference latency.
- Detailed record: `rag/results/rag-through-gateway-2026-10-11.md`.
- The RAG client now uses the authenticated gateway. This is still a CLI-based prototype; the next milestone is a single authenticated `POST /v1/rag/ask` API for future business apps.
- Keep gateway and vLLM loopback-only. Do not expose the temporary shared-key gateway publicly; production use requires real identity, HTTPS, tenant isolation, durable auditing, managed secrets, quotas and security review.


### 2026-10-11 — Single-endpoint RAG API implemented; live test pending
- Added `POST /v1/rag/ask` to the local API gateway. It uses the shared standard-library retrieval module `rag/rag_engine.py`, applies the demo-only minimum score, invokes the local vLLM upstream, and returns `status`, answer text, source file/chunk/score metadata and retrieval details.
- Both chat and RAG routes share the gateway bearer-key authentication, payload size check and per-client in-memory rate limiter. RAG requests validate question length and `top_k`; keys/prompts/answers are not logged.
- Added `api/openapi.yaml` as a versioned API contract and documented the guarded upgrade/test in `api/README.md`.
- Updated gateway has **not yet been run in the live Pod**. The next action is to run `api/upgrade_gateway_with_rag_smoke.sh` in the second terminal. It syntax-checks files, saves a previous gateway copy, restarts only the gateway (not vLLM), and attempts rollback if tests fail.
- Keep binding to `127.0.0.1`. Do not expose this prototype publicly. The current demo threshold is not suitable for arbitrary customer corpora, and the shared key is only a temporary local development credential.


### 2026-10-11 — API gateway RAG endpoint implementation files prepared
- Added shared BM25 functions in `rag/rag_engine.py` so the CLI and API gateway can use the same retrieval behaviour.
- Updated `api/local_gateway.py` with authenticated `POST /v1/rag/ask`; the HTTP response includes `status`, answer, model, source metadata, and retrieval score/abstention information.
- Added OpenAPI 3.1 contract at `api/openapi.yaml`.
- Added `api/upgrade_gateway_with_rag_smoke.sh` for the existing live gateway and updated `api/run_gateway_smoke.sh` for a fresh start. Both use a loopback listener and check authentication plus an end-to-end document answer. The in-place upgrade script has a rollback path and does not stop vLLM.
- Code is committed, but the new HTTP endpoint has not yet passed a live test. Run the guarded upgrade script before claiming it works. The previous gateway version is backed up locally at `/tmp/platform_gateway.py.pre-rag` by the script.


### 2026-10-11 — Authenticated RAG HTTP endpoint verified end to end
- The guarded gateway upgrade/smoke script ran successfully. It syntax-checked files, restarted only the gateway, kept vLLM running, and confirmed upstream health.
- `POST /v1/rag/ask` rejected missing credentials, returned the correct 10-business-day answer plus source metadata for the supported question, and abstained before model generation for the low-relevance yacht question.
- Final output: `ALL GATEWAY + RAG API TESTS PASSED.`
- Full record: `api/results/gateway-rag-api-live-2026-10-11.md`.
- Gateway stays loopback-only on the Pod; API key is ephemeral in `/tmp/platform-gateway.key`. No public exposure or real customer data.
- Next: add deterministic unit tests for the shared BM25 retrieval engine so ranking, chunking and zero-match behavior can be tested without spending GPU time; then use the same tests as a regression gate before extending ingestion or integrations.


### 2026-10-11 — GPU-free RAG retrieval unit tests added
- Added `rag/tests/test_rag_engine.py`, which tests case-insensitive tokenization, empty input, chunking/overlap, expected source ranking for expenses and office-hours questions, zero-overlap retrieval, and top-k limits.
- These tests use Python's standard library and do not call the model or the vLLM API. They can catch basic retrieval regressions without GPU inference costs.
- Documented the one-command fetch/run sequence in `rag/README.md`.
- Next: run the tests on the active Pod, fix any failures before altering ranking, then build broader ingestion/format support only after the retrieval core is stable.


### 2026-10-11 — RAG engine unit tests passed
- The user ran `rag/tests/test_rag_engine.py`: 10 tests ran in 0.003 seconds and all passed.
- Covered case-insensitive tokenization, empty inputs, chunk splitting/overlap, expected BM25 source ranking for expense and office-hours questions, zero-overlap retrieval, and top-k limit.
- Detailed record: `rag/results/rag-engine-unit-tests-2026-10-11.md`.
- These tests run without model inference and can be used as a cheap local regression check. They do not prove retrieval quality on real corpora or make the prototype production-ready.
- Next: broaden document ingestion beyond Markdown/plain text to practical business file types (at minimum CSV and DOCX with standard-library parsers where feasible), while preserving source references and adding parser tests. PDF/XLSX support should be added with deliberate dependency and safety decisions rather than blindly installing packages into the current working model environment.


### 2026-10-11 — Expanded RAG ingestion to common business formats; tests pending
- Added `rag/document_loaders.py` using only the Python standard library. Initial supported types: TXT, Markdown, CSV, HTML/HTM, and DOCX.
- CSV is flattened by row; HTML parser omits script/style/noscript/SVG text; DOCX parser extracts paragraphs from `word/document.xml`. Source-file size is capped at 10 MiB and uncompressed DOCX document XML at 20 MiB.
- Integrated the loader into `rag/rag_engine.py`, updated CLI help and gateway scripts to fetch the new module.
- Added tests for CSV, HTML, DOCX, unsupported files and source attribution, in addition to the existing tokenizer/chunking/BM25 tests.
- No live gateway change has been applied by the GitHub commit alone. Next: fetch the loader/engine/tests to the active Pod, run syntax compilation and unit tests; only after they pass, use the guarded upgrade script to update the running gateway, then re-run the end-to-end gateway + RAG checks.
- PDF and XLSX parsing remain deferred. No third-party parsing dependencies have been installed in the working model environment.


### 2026-10-11 — Clarify loader test status
- After adding CSV/HTML/DOCX loading, the user ran the compilation and general retrieval test command. Screenshot showed `Ran 10 tests`, matching the old retrieval tests; it did **not** confirm discovery of the five added loader tests.
- Added a dedicated `rag/tests/test_document_loaders.py` suite (8 tests) and explicit instructions to run it separately.
- Keep the live gateway unchanged until the focused parser suite passes. The 10 existing retrieval unit tests did pass; parser verification remains pending.


### 2026-10-11 — Focused document-loader tests passed
- The user ran `rag/tests/test_document_loaders.py`: 8 tests ran in 0.010 seconds and all passed.
- Covered TXT reading, CSV row extraction, HTML script/style exclusion, DOCX paragraph extraction, invalid/unsupported input rejection, 10 MiB input-size guard, source filename preservation, and CSV/DOCX source ranking.
- Report: `rag/results/document-loader-tests-2026-10-11.md`.
- The new loader has now passed its focused parser suite; the existing 10 retrieval tests were also previously confirmed to pass.
- Next: run the guarded gateway upgrade script to deploy the updated shared loader/retrieval modules and re-test health, unauthenticated rejection, supported RAG answer/source metadata, and low-relevance abstention. The script upgrades only the gateway and does not restart the model server.
- PDF/XLSX ingestion remains deferred pending a deliberate parser/dependency choice.


### 2026-10-11 — Gateway upgraded after loader tests; smoke tests passed
- After the dedicated loader suite passed 8/8, the guarded upgrade script fetched and syntax-checked the gateway and shared retrieval module, stopped/restarted only the gateway, and left vLLM running.
- Health check passed; unauthenticated RAG request was rejected; supported expense question returned "10 business days" with source metadata; low-relevance question was blocked before model generation (score 0.69 < demo threshold 2.30).
- User screenshot confirms `ALL GATEWAY + RAG API TESTS PASSED`.
- Detailed result: `api/results/gateway-after-loader-upgrade-2026-10-11.md`.
- Validation boundary: live smoke tests still use the Markdown demo corpus. Parser unit tests passed for CSV/HTML/DOCX, but actual live RAG API requests against those file types remain unverified.
- Next: add a separate fictional CSV and DOCX to the configured RAG document folder, ask a question whose answer exists only in each one through `POST /v1/rag/ask`, and confirm source metadata points to the correct source file. Do not expose the gateway or use real customer data.


### 2026-10-11 — Verify common business document types through HTTP API
- After CSV/HTML/DOCX parser unit tests passed 8/8 and the gateway was upgraded successfully, created `api/test_format_ingestion.sh`.
- The script starts a second temporary loopback gateway on port 8011 with an isolated temporary corpus, tests a CSV fact and a DOCX fact through `POST /v1/rag/ask`, verifies answer and source filename, then cleans up the test gateway/files. It does not change the current gateway on 8010 or the vLLM model server on 8000.
- The relevance gate is set to 0 only for this isolated format test because the 2.30 threshold is calibrated specifically for the two Markdown demo files, not a different corpus.
- This test is pending execution. Do not claim CSV/DOCX works end-to-end until it passes.


### 2026-10-11 — PDF support added to business document ingestion
- Added text-based PDF parsing to `rag/document_loaders.py`, including page markers, a 10 MiB file cap, 300-page cap, and 5-million-character extracted-text cap. Password-protected PDFs and scanned/image-only PDFs are explicitly rejected because OCR is not included.
- Chose pinned `pypdf==6.20.0` after checking the official PyPI project page. PyPI identifies it as pure Python, BSD-3-Clause, Python >=3.9, with a ~402 KB universal wheel. The wheel SHA-256 is pinned as `f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad`. Details: `rag/PDF_SUPPORT.md` and `rag/requirements-ingestion.txt`.
- Added `rag/setup_pdf_support.sh`: it verifies the wheel, persists it under `/workspace/runtime-setup/rag-wheelhouse` on the Global Volume, and extracts it to `/tmp/rag-deps`. It does not modify the working vLLM environment.
- Added PDF tests to `rag/tests/test_document_loaders.py` for text extraction/page marker, blank/scanned-PDF rejection, malformed PDF rejection, and source filename preservation through retrieval. Total focused loader suite is now 12 tests, awaiting the user's run with `PYTHONPATH=/tmp/rag-deps`.
- Updated gateway startup/upgrade scripts to require pypdf 6.20.0 and expose the isolated parser target via `PYTHONPATH`.
- Expanded `api/test_format_ingestion.sh` to test CSV, DOCX and PDF through an isolated temporary gateway at port 8011. The PDF-specific end-to-end test remains pending.
- Next sequence: run `rag/setup_pdf_support.sh`; download loader/engine/test file and run syntax compilation plus the 12 tests; then run guarded gateway upgrade; finally run CSV/DOCX/PDF end-to-end test. Do not claim PDF is verified live until the corresponding tests pass.
- Source reference: https://pypi.org/project/pypdf/6.20.0/


### 2026-10-11 — PDF-enabled document loader suite passed
- User ran parser tests with `PYTHONPATH=/tmp/rag-deps`; screenshot confirms `Ran 12 tests in 0.064s`, `OK`.
- Covered text-based PDF extraction and page marker, no-text/scanned PDF rejection pending OCR, malformed PDF rejection, and PDF filename preservation through retrieval. Existing TXT/CSV/HTML/DOCX tests passed in the same suite.
- Detailed record: `rag/results/document-loader-tests-with-pdf-2026-10-11.md`.
- The PDF parser dependency remains separate from the working vLLM environment and its wheel is saved with checksum on the Global Volume.
- Next: run the guarded gateway upgrade; after it passes, run the temporary isolated CSV/DOCX/PDF HTTP integration test. Until that passes, mark PDF parsing as unit-tested, not end-to-end verified.


### 2026-10-11 — Gateway passed after PDF dependency upgrade
- After parser unit tests passed 12/12, user ran the guarded gateway upgrade. Screenshot confirms gateway health, unauthenticated request rejected, correct source-cited 10-business-day answer, and low-relevance abstention before model generation.
- Final command output: `ALL GATEWAY + RAG API TESTS PASSED`. The vLLM model server was not restarted.
- Report: `api/results/gateway-after-pdf-dependency-upgrade-2026-10-11.md`.
- End-to-end API support for CSV, DOCX and PDF remains pending. Next run `api/test_format_ingestion.sh` against the isolated temporary gateway on port 8011; do not alter the main gateway on 8010 or vLLM on 8000.


### 2026-10-11 — CSV, DOCX and PDF verified end to end through RAG API
- User ran `api/test_format_ingestion.sh`; screenshot confirms all three API integration tests passed.
- CSV query returned "Visitors must check in at Gate C" with source `visitor-rules.csv`.
- DOCX query returned Project Helios launch review on 18 November with source `launch-review.docx`.
- PDF query returned Project Orion purchase order review on 23 November with source `project-review.pdf`.
- All requests returned `status: answered`, source citations, and expected source filenames. pypdf 6.20.0 was verified.
- The temporary test gateway stopped itself; main gateway at 8010 and vLLM at 8000 remained untouched.
- Report: `api/results/csv-docx-pdf-integration-2026-10-11.md`.
- Coverage boundary: these are fictional, text-based, small samples; not proof every real-world file layout works. Scanned PDF OCR, password-protected PDFs, XLSX spreadsheets and production hardening remain separate work.
- Next: add business Excel `.xlsx` ingestion using an isolated, pinned parser dependency and tests that preserve sheet names, rows and source attribution; do not install it into the vLLM environment.


### 2026-10-11 — Excel XLSX ingestion implemented; tests pending
- Added `openpyxl==3.1.5`, `et-xmlfile==2.0.0` and `defusedxml==0.7.1` as hash-pinned wheels under `rag/requirements-xlsx.txt`, with a verified isolated setup script `rag/setup_xlsx_support.sh`. Package details and limits: `rag/XLSX_SUPPORT.md`.
- Updated `rag/document_loaders.py` to read `.xlsx` files using a read-only workbook loader. It preserves sheet name/state, row numbers and cell coordinates; reads cached formula values rather than recalculating formulas; and applies file/uncompressed-size/sheet/row/column/text limits.
- Added four parser tests for worksheet text, source attribution/retrieval, malformed workbook, and empty workbook.
- Updated gateway startup/upgrade scripts to require the pinned XLSX dependency alongside pypdf; expanded the isolated format integration test to query CSV, DOCX, PDF and XLSX.
- Next: run XLSX setup, then syntax compile and the now-16-test parser suite with `PYTHONPATH=/tmp/rag-deps`. Do not alter the live gateway until all parser tests pass. Then run guarded gateway upgrade and combined four-format integration test.


### 2026-10-11 — XLSX parser tests passed
- The user screenshot confirms `openpyxl 3.1.5`, `et-xmlfile 2.0.0` and `defusedxml 0.7.1` were verified under `/tmp/rag-deps`; the Global Volume holds the wheel artifacts and checksum list.
- The expanded document-loader suite ran 16 tests in 0.243 seconds and all passed. Coverage includes TXT, CSV, HTML, DOCX, text-based PDF, XLSX, source attribution, malformed/empty documents and resource limits.
- The working vLLM environment was not modified; document parsing dependencies are isolated from it.
- Detailed record: `rag/results/document-loader-tests-with-xlsx-2026-10-11.md`.
- Next: run `api/upgrade_gateway_with_rag_smoke.sh`, then `api/test_format_ingestion.sh` to verify CSV, DOCX, PDF and XLSX through the HTTP API. XLSX remains unverified end to end until the final HTTP integration test passes.


### 2026-10-11 — Gateway passed with PDF and XLSX parser dependencies enabled
- User screenshot confirms the gateway upgrade verified pypdf 6.20.0, openpyxl 3.1.5, et-xmlfile 2.0.0 and defusedxml 0.7.1.
- New gateway and shared retrieval engine compiled; only the gateway process was stopped/restarted (old PID 3118), not vLLM.
- Health passed, unauthenticated requests were rejected, the supported source-grounded policy question passed, and the low-relevance question was blocked before generation at demo threshold 2.3.
- Final output: `ALL GATEWAY + RAG API TESTS PASSED`.
- Report: `api/results/gateway-after-pdf-xlsx-upgrade-2026-10-11.md`.
- Next: run `api/test_format_ingestion.sh` for CSV/DOCX/PDF/XLSX against isolated port 8011. Excel is parser-tested and gateway-startup-validated but remains unverified end-to-end until its HTTP integration case passes.


### 2026-10-11 — CSV, DOCX, PDF and XLSX confirmed through RAG API
- User screenshot shows `ALL CSV/DOCX/PDF/XLSX INTEGRATION TESTS PASSED`.
- CSV: visitor check-in answer "Gate C", source `visitor-rules.csv`.
- DOCX: Project Helios review date "18 November", source `launch-review.docx`.
- PDF: Project Orion review date "23 November", source `project-review.pdf`.
- XLSX: Q4 marketing budget "27,500", source `department-budget.xlsx`.
- Each response had `status: answered` and correct source metadata.
- Temporary format-test gateway stopped itself; the main gateway on 8010 and vLLM on 8000 remained untouched.
- Detailed result: `api/results/csv-docx-pdf-xlsx-integration-2026-10-11.md`.
- This verifies four synthetic documents, not arbitrary real-world file layouts. Scanned-PDF OCR, formula recalculation, complex spreadsheet/table handling, customer auth/tenant isolation and production hardening remain open tasks.
- Next: build persistent document management around the API—safe upload, list and delete operations, per-document metadata and re-index-on-query—using an isolated test directory first. Do not ingest real customer files or expose the loopback prototype publicly.


### 2026-10-11 — Managed document collection API implemented; validation pending
- Added `rag/document_library.py`: validated collection names and filenames, allowlist for TXT/MD/CSV/HTML/DOCX/PDF/XLSX, strict base64 decoding, 10 MiB decoded-file limit, parser validation before storing, duplicate protection unless `overwrite=true`, and list/delete operations. Paths are constrained to a configured managed root; writes avoid assuming atomic rename support on the FUSE mount.
- Extended `api/local_gateway.py` with authenticated `POST /v1/rag/documents`, `GET /v1/rag/documents?collection=...`, `DELETE /v1/rag/documents?collection=...&filename=...`; `POST /v1/rag/ask` now accepts an optional collection identifier.
- Main gateway setup/upgrade scripts download and compile the document-library module and configure managed storage at `/workspace/rag-managed-docs` on the mounted Global Volume. Main gateway has not yet been upgraded to this feature.
- Added `rag/tests/test_document_library.py` (14 no-GPU unit tests) and `api/test_document_management.sh` for isolated authenticated upload/list/query/delete tests on port 8012 and temporary storage.
- Updated OpenAPI contract to version 0.3 with document endpoints.
- The managed collection BM25 threshold defaults to 0.0 in this prototype because the demo threshold is not calibrated for new collections. This is intentionally documented as not production-safe; calibrate per collection before business use.
- Next: run syntax compilation and all document-library unit tests, then run the isolated API management script. Only after both pass should the main gateway be upgraded and a harmless test document be uploaded to the Global Volume.


### 2026-10-11 — Persistent source and runtime archival is now an explicit build requirement
- User clarified that this is an ongoing reusable platform build, not disposable testing. The permanent requirement is: every meaningful change must be in GitHub version history and backed by a versioned snapshot on the mounted Global Volume; runtime packages/assets must be reconstructible without preserving every ephemeral `/tmp` file.
- Added `ops/PERSISTENCE.md` documenting the authority and purpose of GitHub, Global Volume, Pod-local temporary storage and the independent Azure backup.
- Added `ops/sync_global_volume.sh`. It verifies that `/workspace` is mounted as the expected Global Volume, resolves a full GitHub commit SHA, downloads and validates that complete source archive, stores it immutably at `/workspace/ai-platform-backups/source-snapshots/`, verifies its SHA-256, inventories existing runtime backup/wheelhouse/model artifacts, and captures copies/checksums of deployed runtime Python files if present. It does not copy API keys or other secrets.
- Existing persistent assets already noted: model in `/workspace/gemma-4-31B-it/`; vLLM runtime archive/frozen requirements/manifest/install script in `/workspace/runtime-setup/`; PDF/XLSX wheels and checksums in `/workspace/runtime-setup/rag-wheelhouse/`; Azure remains an independent backup.
- **Important status:** the new source snapshot script has been committed to GitHub, but the user has not yet run it on the live Pod. Do not claim the complete GitHub source snapshot is already mirrored to the Global Volume until a successful run confirms the archive and manifest paths.
- Operating rule: after every meaningful code/config/dependency/model/runtime change, commit source/tests/docs in GitHub, run tests, run `ops/sync_global_volume.sh`, and check the checksum output. Do not treat Pod-local `/tmp` content or temporary API keys as persistent assets.


### 2026-10-11 — First Global Volume source sync blocked safely; mount check corrected
- User ran the document library unit tests: **14 tests passed**.
- User then ran `ops/sync_global_volume.sh`. It aborted before copying anything because its mount validation falsely rejected the reported mount `fuse.geeseefs 5aac0c77-6fcc-4be9-a112-dfe3890d1373`, which matches the expected Global Volume filesystem from prior diagnostics.
- The script was corrected to read filesystem type and source separately and compare the filesystem type exactly against `fuse.geeseefs`. No file was copied by the failed attempt.
- Next: fetch the corrected script from GitHub, run `bash -n`, and run the sync again. Verify the printed snapshot and manifest paths plus successful SHA-256 checks. Do not claim the source snapshot exists until this succeeds.


### 2026-10-11 — Repeated Global Volume sync preflight failure corrected again
- The user ran the script pinned to commit `4c21052c13c05ff42db2829b9124100664610945`; output showed the corrected `Detected filesystem: fuse.geeseefs` message but it still rejected the volume. My prior diagnosis that the user was still downloading the old script was wrong.
- No files were copied by either failed attempt.
- Replaced filesystem-type string equality with two checks: `findmnt` must report `/workspace` itself as the mount target, and the expected Gemma `config.json` must exist on that mounted path. This should avoid the false rejection while refusing to copy if the volume is not mounted or lacks the expected model.
- New script commit: `81778c1a8da93a7a9e3b46884bb5b6ed82663282`.
- Next: fetch that exact commit, confirm it contains `MODEL_MARKER=`, run `bash -n`, then run the sync. Do not claim the snapshot exists until the script confirms archive and manifest checksums.


### 2026-10-11 — First complete source snapshot verified on Global Volume
- User screenshot confirms `ops/sync_global_volume.sh` finished with `SUCCESS: source snapshot and manifest saved on the mounted Global Volume.`
- Captured GitHub commit: `404dad8e59363ff7882b0cbb05bae1640e1e3d1a`.
- Source archive: `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.tar.gz`.
- Manifest: `/workspace/ai-platform-backups/manifests/global-volume-manifest-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.txt`.
- Screenshot confirms archive checksum passed. Runtime inventory and deployed runtime copies were captured where present; existing model/runtime backup folders were preserved.
- Full record: `ops/results/global-volume-snapshot-2026-10-11.md`.
- This snapshot contains the committed repository at the specified SHA. After committing this success record, re-run the sync script once to produce a newer snapshot that includes this record.


### 2026-10-11 — Document management API tests passed on isolated temporary storage
- User screenshot confirms `ALL DOCUMENT-MANAGEMENT API TESTS PASSED`.
- The temporary gateway rejected unauthenticated upload; upload returned 201; list returned metadata; duplicate upload returned 409 without overwrite; traversal filename was rejected; query returned the finance contact with `finance-notice.md` source; delete succeeded and list was empty.
- Test used temporary storage and cleaned it up. Existing main gateway on 8010 and vLLM were untouched.
- Detailed result: `api/results/document-management-api-2026-10-11.md`.
- Next: upgrade the main gateway to the document-management version, then verify upload/list/question/delete using a controlled test collection under `/workspace/rag-managed-docs` on Global Volume. Only then can we say the persistent document-management path is verified. Cross-Pod persistence still needs a recovery/re-attach test.


### 2026-10-11 — Source snapshot refreshed before live document-storage deployment
- User screenshot confirms successful source snapshot at commit `bd44a9d3bca78837c039fca140b2d8543b0bab83`; archive checksum passed.
- Archive: `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-bd44a9d3bca78837c039fca140b2d8543b0bab83.tar.gz`.
- Manifest: `/workspace/ai-platform-backups/manifests/global-volume-manifest-bd44a9d3bca78837c039fca140b2d8543b0bab83.txt`.
- Report: `ops/results/global-volume-document-management-snapshot-2026-10-11.md`.
- The isolated document management API tests previously passed all checks. Next: upgrade the main gateway, write and query a small non-sensitive canary under `/workspace/rag-managed-docs/`, verify it physically exists on the Global Volume, then run a fresh source snapshot so this next milestone is persistent too.


### 2026-10-11 — Source snapshot verified; document management API ready for live Global Volume test
- User screenshot confirms latest successful source archive at commit `bd44a9d3bca78837c039fca140b2d8543b0bab83` with archive checksum `OK`; manifest is present under `/workspace/ai-platform-backups/manifests/`.
- The temporary document-management API tests passed all 14 checks, including upload/list/duplicate protection/path-traversal/query/delete. This did not touch the persistent volume.
- Added `ops/test_persistent_document_storage.sh`: after the guarded gateway upgrade, it verifies the Global Volume mount and model marker, uploads a small fictional canary via the real API into a unique collection under `/workspace/rag-managed-docs/`, confirms the file physically exists, lists it through the API, asks a question, and checks the source filename. It intentionally retains the tiny canary for a later cross-Pod re-attach test. It doesn't print the API key.
- Next: run `api/upgrade_gateway_with_rag_smoke.sh` on the current Pod (restarts only the gateway, never vLLM), then run `ops/test_persistent_document_storage.sh`. If that passes, re-run `ops/sync_global_volume.sh` to save the newly committed operational script and deployment milestone to a newer immutable archive.
- No claim of cross-Pod persistence yet: this next test proves writes/reads on the actual mounted Global Volume; a later attach/recovery test should verify the canary from a replacement Pod.


### 2026-10-11 — Live document management verified on the Global Volume
- User screenshot confirms the live gateway health check passed; a 136-byte fictional canary document was uploaded, physically found under `/workspace/rag-managed-docs/`, listed through the live API, and queried successfully through RAG with the expected answer and source metadata.
- Final result: `SUCCESS: document upload/list/retrieval verified at the mounted Global Volume path.`
- Retained canary: collection `global-canary-1791758676`, file `global-volume-canary.md`. It contains fictional data and is intentionally retained for a later Pod re-attach persistence test.
- Detailed report: `api/results/live-global-volume-document-persistence-2026-10-11.md`.
- Boundary: this proves persistence on the currently mounted Global Volume, not yet across Pod stop/recreation/re-attachment. Do not upload real customer data until production security, tenancy, retention and recovery controls are tested.


### 2026-10-11 — Live document storage verified on Global Volume
- User screenshot confirms `ops/test_persistent_document_storage.sh` completed with `SUCCESS: document upload/list/retrieval verified at the mounted Global Volume path.`
- Gateway health and upstream were both OK.
- Live upload stored a 136-byte fictional canary in collection `global-canary-1791758676`; physical file verified at `/workspace/rag-managed-docs/global-canary-1791758676/global-volume-canary.md`.
- Live API listing returned its metadata, and a live RAG query returned `GLOBALVOL-58317` from the canary source.
- The canary is intentionally retained for a future Pod re-attach persistence test.
- Detailed report: `ops/results/live-global-volume-document-storage-2026-10-11.md`.
- Remaining: sync this latest report/source to the Global Volume; later test re-attachment to a fresh Pod. Do not use real customer documents until tenant isolation, access control, encryption, retention, backup and audit controls are implemented and tested.


### 2026-10-13 — Document Q&A and same-Pod recovery milestone closed
- Branch `cursor/local-web-console` milestone commit family through `9d35189` (lifecycle), with prior calc/recovery commits `d54f1cb` and `b782f7b`.
- **Document Q&A (completed for this milestone):**
  - Conversational Document Q&A with bounded, validated, untrusted client history.
  - Managed collections: upload/list/query/delete with searchable confirmation and index removal.
  - Deleted-document leakage hardened: history sanitisation strips answers that cite files no longer in the collection; answers are scoped to the current collection inventory.
  - Spreadsheet extraction keeps sheet/row/cell/header context; decimal-safe numeric rendering; stored vs displayed currency for weekly calculations (`stored=` / `displayed=` / deterministic weekly aid).
  - Duplicate workbook evidence collapsed by identical extracted rows while listing filenames; conflicting values stay separate.
  - Isolated test stack supported on `:8012` / `:8082` without touching main `:8010` / `:8080` or restarting the model.
- **Recovery (completed for this milestone):**
  - `ops/preflight-recovery.sh` and `ops/start-platform.sh` provide idempotent same-Pod restart helpers (reuse healthy listeners; do not force-restart).
  - `ops/start-test-console-8082.sh` recovers the isolated Document Q&A test console.
  - Runbook: `docs/recovery-runbook.md`. Persistent assets and source snapshots live under `/workspace` (including `/workspace/ai-platform-backups/source-snapshots/` and `/workspace/rag-managed-docs/`).
  - Full Pod-recreation / cold-start restore remains unverified until a controlled drill passes.
- **Validation evidence (local unit suites at milestone close):** `python -m unittest rag.tests.test_rag_engine rag.tests.test_document_loaders rag.tests.test_document_library api.test_rag_conversation` → **62 tests OK**.
- **Deferred (explicit):** advanced manual-guided reasoning across local-authority fee frameworks (combining operations-manual Process E guidance with Fee-to-LA worksheet membership, framework-tab navigation, and age-band/placement rate selection when the authority appears only on a framework sheet’s LA list). Incomplete WIP for that feature was reverted and is not part of this milestone.


### 2026-10-13 — Qwen3.5-27B integration started (offline Stage 1–3/5; live serve blocked)
- Goal: add `Qwen/Qwen3.5-27B` as a second open-weight model without disturbing the working Gemma Document Q&A / recovery stack.
- Baseline branch point: `861086a` on `cursor/local-web-console`. Work continues on `feature/qwen3.5-27b-integration`.
- Official model facts recorded: Apache-2.0; Hugging Face revision `fc05daec18b0a78c049392ed2e771dde82bdf654`; 11 safetensors shards; multimodal image-text model; vLLM card requires a fresh nightly/main install (do not mutate `/tmp/vllm-clean-env`).
- Hardware note from prior Gemma runbook: Pod historically used NVIDIA H100 NVL ~94 GB. BF16 Qwen ~51+ GiB weights should fit with limited context **only if Gemma is not loaded**. Concurrent dual-model serving on one GPU is refused.
- **Added (version-controlled):** expanded `models/registry.yaml` (schema v2, Gemma remains production default, Qwen as `integration-candidate`); `models/registry_loader.py`; isolated ops scripts `ops/download-qwen3.5-27b.sh`, `ops/install-qwen-vllm-env.sh`, `ops/start-qwen-isolated.sh` (`:8002`), `ops/start-test-gateway-qwen.sh` (`:8013`/`:8083`); backward-compatible gateway model selection + authenticated `/v1/platform/models` catalog (no filesystem paths); Azure prepare-only docs `docs/azure-qwen-migration.md`, `docs/azure-qwen-cost-estimate.md`; operator guide `docs/qwen3.5-27b-integration.md`.
- **Not done in this pass (blockers):** RunPod SSH to `216.81.245.29:48480` was connection-refused (Pod/SSH appears stopped; starting it is billed). Therefore Qwen weights were **not** downloaded, the isolated vLLM env was **not** installed on the Pod, and Qwen has **not** answered a live request. Main `:8010`/`:8080` and Gemma were not restarted.
- **Still requiring operator approval before live validation:** start the RunPod Pod; optionally stop Gemma on `:8000` to free VRAM; then run the Qwen download/serve/smoke sequence in `docs/qwen3.5-27b-integration.md`. Azure GPU/Blob spend remains unapproved.
- **Still deferred:** advanced manual-guided LA fee framework reasoning; promoting Qwen to production default; claiming multimodal/tool-calling support.


### 2026-10-13 — Issue #1 safe-repo autonomous handover
- Tracking: GitHub issue [#1](https://github.com/henokmeron/AI-PLAYBOOK.md/issues/1) and `AUTONOMOUS_WORK_QUEUE.md`.
- Synced feature branch through remote queue commit `2b319cb`; revalidated local suites (**69 OK**); refreshed queue checklist for offline-complete items only.
- Cursor-browser probe evidence retained: Global Volume `cmv2p5m0d000007jk9o3931ea` (~66.4 GB); no running Pod; balance was −$0.23; SSH refused.
- Live Qwen download/serve/snapshot still blocked pending credits + running Pod + optional Gemma-stop approval. Main `:8010`/`:8080` untouched.

### 2026-10-13 — Qwen3.5-27B live isolated stack validated
- Download + isolated vLLM serve on `127.0.0.1:8002` (revision `fc05daec…`, 11 shards) succeeded; chat smoke returned **`QWEN_OK`**.
- Isolated gateway `127.0.0.1:8013` and console `127.0.0.1:8083` started; authenticated gateway smoke also **`QWEN_OK`**.
- Production default left as Gemma; main `:8010`/`:8080` not modified. Gemma `:8000` was not running while Qwen owned the GPU.
- Evidence: `ops/results/qwen-live-stack-2026-10-13.md` and `/workspace/platform-diagnostics/qwen/`.
- Still deferred: restore Gemma after Qwen stop; promote Qwen; Azure spend; fresh feature-branch volume source snapshot.

### 2026-10-13 — Tonight completion (dual-model recoverable state)
- Phase 1–8 executed on `feature/qwen3.5-27b-integration` against live Pod (A100 80GB) + Global Volume.
- Qwen remains on isolated `:8002`/`:8013`/`:8083`; live chat + isolated Document Q&A (upload/ask/delete) **PASS**.
- Registry selection: explicit model id works; cross-runtime requests return **HTTP 409** (no silent fallback). Catalog reports `runtime_loaded`.
- Production default still Gemma. Main `:8010`/`:8080` not started. Gemma overlay env missing; restore from `/workspace/runtime-setup/vllm-clean-env.tar.zst` before Gemma serve.
- Local regression: **70 tests OK**. Acceptance: `ops/results/tonight-completion-acceptance-2026-10-13.md`.
- Snapshot helper: `ops/snapshot-source-commit.sh <sha>` for immutable Global Volume source archives without weight duplication.

### 2026-10-13 — Post-acceptance runtime archive + Gemma env restore (no switch)
- Inspected live Pod: Qwen `:8002`/`:8013`/`:8083` still up; main/Gemma ports down; Global Volume mounted; snapshots `7072cab`/`534a891` preserved.
- **VERIFIED:** archived Qwen venv to `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (~3.8G) with `SHA256SUMS` OK; no secrets; no overwrite of prior assets.
- **VERIFIED:** Gemma `/workspace/runtime-setup/vllm-clean-env.tar.zst` checksum + `zstd -t` OK; restored to `/tmp/vllm-clean-env` (vLLM 0.31.0) **without** starting Gemma; Qwen kept serving.
- **PREPARED:** `ops/switch-gpu-model.sh` now dry-run by default (`SWITCH_CONFIRM=yes` to act); procedure in `docs/one-gpu-model-switch.md`; Qwen restore helper `ops/restore-qwen-runtime.sh`.
- **PREPARED ONLY:** console model picker design in `docs/console-model-picker-design.md` (not implemented).
- **BLOCKED without approval:** stop/switch live Qwen → Gemma main `:8000`/`:8010`/`:8080`; production default change; picker on main console.
- Evidence: `/workspace/platform-diagnostics/tonight/post-acceptance-inspect.json`; `ops/results/post-acceptance-runtime-2026-10-13.md`.

### 2026-10-13 — Final mission (picker + Qwen-primary code; live serve blocked on new Pod driver)
- Shipped console model picker, registry `production: qwen3.5-27b`, and `ops/start-first-release.sh`.
- New Pod `usual_coral_ape` (SSH `216.81.151.54:13774`) has NVIDIA **driver 570** / CUDA 12.8. Current vLLM wheels need cudart 13 → engine fails with insufficient driver. Weights + archives on Global Volume remain intact.
- **Next:** redeploy same volume on driver ≥580, then `bash ops/start-first-release.sh --start` and E2E browser tests.
- Acceptance: `ops/results/final-mission-acceptance-2026-10-13.md`.

### 2026-10-15 — Cloud Agent cannot use the RunPod key

- Started from `4f3f4f82af268e6363182b886dac3a9a5cc01faf`. TCP `216.81.248.126:19091` accepts a connection. This Cloud Agent has no private key, no RunPod credential, and no self-hosted worker. The Pod was not changed.
- Resume in Cursor on the Windows PC at `C:\Users\henok\src\AI-PLAYBOOK.md`. The key is `C:\Users\henok\.ssh\id_ed25519`. The read-only SSH check and the console-only deploy command are in `docs/AGENT_HANDOFF.md`. Deploy the console only after `:8002` and `:8010` already return HTTP 200. Do not run `START.sh` without a separate approval. Do not paste the key or a Microsoft application id into chat.

### 2026-10-15 — Idle Pod confirmed; read-only device check-in is source-only

- Pod `1g41ejmd99iyun` is an A100 SXM at $1.79/hour. SSH `root@216.81.248.126 -p 19091` worked. The old port `11165` refused. The Global Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` is mounted. Qwen weights (11 shards) and the 3.8G runtime archive are present. GPU memory was 0. Ports 8002, 8010, and 8080 were not listening. Nothing was started or stopped.

### 2026-10-15 — Current Pod blocked by NVIDIA driver 570

- Current Pod `tn28umxi9a5lqx` (“relative_emerald_ant”), SSH `root@185.216.23.194 -p 45209`. Same Global Volume. Archive checksum and snapshot `01e7692` **OK**. Driver **570.172.08**. `START.sh --preflight` correctly fails `nvidia-driver>=580` and does not start Qwen. Redeploy the same volume on a host with driver ≥580 (RunPod CUDA 13 filter). Evidence: `docs/results/runpod-driver570-health-2026-10-15.md`.
- `ops/release/deploy-console-only.sh` can replace only the console, and only after Qwen and the gateway are already healthy. It was not run.
- Enrolled computers can submit operating system, disk, memory, and boot time through `integrations/endpoint_worker.py`. The server stores a hash of the device secret. There is no remote-control command. Catalog evidence is mock-tested. A collector call on the developer Windows PC was schema-valid and was not sent to the Pod.
- Microsoft Graph is still not connected. A personal Microsoft account cannot open Entra app registrations (AADSTS16000). No application was created.

### 2026-10-21 — Blackwell runtime pin corrected to CUDA 12.9 (NOT TESTED on GPU)

- **Why:** The earlier registry profile `qwen-vllm-blackwell-cu130` assumed an official vLLM CUDA 13.0 wheel. On 2026-10-21 that wheel returned HTTP 404. Mixing a CUDA 12.9 vLLM binary with a CUDA 13 PyTorch build is refused.
- **Implemented (source only):** runtime profile `qwen-vllm-blackwell-cu129`; lockfile `ops/blackwell-runtime.lock` pins `vllm=0.32.0+cu129`, `torch=2.13.0+cu129`, driver major ≥575, compute capability major ≥12, Python `>=3.11,<3.15`. Installer `ops/install-qwen-blackwell-env.sh` sources the lock, downloads the wheel URL, verifies SHA-256 `9918be806fb2808c406547ff4f9f43870ac6ff28dc4b179291fcf532145bb50b`, installs with `--torch-backend=cu129`, runs `vllm download-kernels`, and refuses `/tmp/vllm-qwen-env`, `/tmp/vllm-clean-env`, and live installs under `/workspace`. Serve helper remains `ops/start-qwen-blackwell.sh` on `:8002` without starting the gateway or console.
- **H100 baseline unchanged:** saved A100 archive `/workspace/runtime-setup/qwen-vllm` stays `torch 2.13.0+cu126`. The installer never writes into that archive. Profile `qwen-vllm-nightly-isolated` remains the H100/A100 path.
- **VERIFIED (offline):** published cu129 wheel HEAD 200 (~534 MiB); streamed SHA-256 matches the lockfile; published cu130 wheel still absent (HTTP error). `ops.test_qwen_blackwell_runtime` and `models.tests.test_registry_loader` pass. Full suite: `python -m ops.run_tests` on Python 3.12 — 38 modules, exit 0 (one automatic module retry on Windows for transient `WinError 10053` under load — assertions unchanged).
- **Git / release:** commit `7037ae9eff56d7694ca79c335f90e445bdf1fdc1` on `origin/main`. Recover with SHA-256 `841a231a8e01ebe83b4fd6a79e315b0a54f76c8581b01fbc936d5e5074b64d13` (`git archive --format=tar.gz` of that commit; 370 members). Do not use the earlier `2c5bab93…` digest. Volume copy not verified.
- **NOT TESTED:** no RTX PRO 6000 (compute capability 12.0) was available. `install-qwen-blackwell-env.sh --install`, `--check`, `--serve`, and `--infer` were not run on GPU. Do not claim Blackwell inference works.
- **BLOCKED / next:** obtain a CC 12.0 host with driver ≥575 without stopping the working H100 stack; run install → check → serve → infer; keep go-live **NO-GO** until live E2E, Entra, and endpoint controls are verified.

### 2026-10-21 — Release archive extraction hardening

- **Implemented in source:** ops/release/package.py now validates archive paths across POSIX and Windows conventions, rejects Windows drive/UNC paths, backslash traversal, NULs and colon-based alternate data streams, and refuses symlink/hardlink/device/FIFO members. Recovery also refuses a symlink destination and still requires a matching SHA-256 and empty destination.
- **Regression tests:** ops/test_release_package.py covers Windows path forms and symlink/hardlink members. Verified GitHub Actions run 39690350318 completed successfully on commit b25294644ffd69415ecb4291723047ec647e8b41. The focused ops.test_release_package suite passed, and the workflow produced a 374-member source archive with SHA-256 e92c9005052d63006a03004bfe212ace11969074a86be6c3c2b333624b33fdf1. Artifact: AI-PLAYBOOK-b25294644ffd69415ecb4291723047ec647e8b41 (ID 12387414455), containing the archive and manifest; artifact ZIP SHA-256 097ec6835443b489a0e186a82781043e5cf5f09fd5c6aef2b847d998bf6da4a1. The artifact is retained for 90 days and was not copied to the RunPod Global Volume. This is focused release-test evidence, not a full-suite or live-deployment pass.
- **Release automation:** .github/workflows/verify-and-package.yml runs the focused release tests, creates a commit-versioned archive plus SHA-256 manifest, and uploads them as a 90-day Actions artifact. The full project suite remains **NOT RUN** in this session.
- **Operational boundary:** no RunPod account inventory, Global Volume inspection/copy, model load, Microsoft Graph call, or paid-resource mutation was performed. Production remains **NO-GO** until live acceptance and integrations are verified.
