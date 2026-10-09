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
