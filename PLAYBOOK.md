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
