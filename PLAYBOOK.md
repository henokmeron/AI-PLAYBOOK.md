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