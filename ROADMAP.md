# GENESIS CORE Roadmap

This roadmap describes intended work. A feature is complete only when implemented, tested and documented. "Initial" means a usable first slice exists, not that the milestone is finished.

## Milestone 0 — Foundation
- [x] Python package and CLI entry point
- [x] Linux hardware diagnostics
- [x] Local web status endpoint and dashboard
- [x] Shared SQLite sessions and messages
- [x] First-party TUI and Studio foundations
- [x] Automated test workflow added and passing
- [ ] Configuration validation and structured logs
- [x] Initial local Test Bench for storage, permissions and environment diagnostics
- [x] First-launch welcome overview with hardware and local-runtime detection (initial)
- [x] Conservative hardware resource profiles and model memory estimates (initial)
- [x] Single detected local model can be selected as primary during guided setup

## Milestone 1 — Model connectivity
- [x] Common chat adapter contract (initial)
- [x] Ollama chat adapter (initial)
- [x] llama.cpp OpenAI-compatible chat adapter (initial)
- [x] LM Studio OpenAI-compatible chat adapter (initial)
- [x] Persistent primary-model selection for supported local runtimes
- [x] Provider adapter and agent-loop tests pass in CI
- [ ] Hugging Face Transformers local adapter
- [ ] Optional remote API mentor providers and secure secret storage
- [x] Hardware-aware first-run model recommendations and opt-in Ollama download (initial)
- [ ] Model capability and context-window inspection
- [ ] Streaming responses and cancellation

## Milestone 2 — Agent runtime
- [x] Basic context-aware chat loop (initial)
- [x] Persistent mission and goal representation (initial CRUD and status transitions)
- [x] Structured mission plans persisted as ordered tasks
- [x] Step-by-step mission execution with stored results and resume after interruption
- [x] Bounded planner / executor / observer loop over chat adapters (initial)
- [x] Structured mission plans with summaries, success criteria, assumptions and risks (initial)
- [x] Adaptive replanning after blocked tasks while preserving completed work (initial)
- [x] Persistent mission plan revision history (initial)
- [ ] Dependency-aware scheduling and parallel-safe task groups
- [ ] Plan quality scoring and outcome-based evaluation
- [x] Initial tool registry with JSON-schema subset validation and duplicate protection
- [x] Initial read-only workspace tools (directory listing and UTF-8 file reading, path-confined)
- [x] Initial fail-closed permission profiles and persistent approval queue (write/system actions remain gated)
- [x] Agent tool routing with bounded steps, repeated-call guard and observer review
- [x] Approval queue exposed through Studio API and TUI
- [ ] Configurable permission profiles and approval management UI
- [ ] Timeouts, budgets, retries and audit log
- [ ] Structured activity events shared by TUI and Studio
- [ ] Background mission scheduling, pause/resume controls and resource budgets

## Milestone 3 — Memory and learning
- [x] Persistent conversation history
- [x] Explicit episodic, semantic and procedural memory records with provenance and confidence (initial)
- [x] Searchable active memory retrieval injected into agent context (initial)
- [x] User controls to list, deactivate and delete memories (initial)
- [x] Explicit capture of fully completed missions into episodic memory using persisted observer-checked outcomes (initial)
- [x] Initial Experience Engine captures each mission task attempt with observer outcome and provenance
- [x] Studio experience explorer with outcome/status filters, evidence detail and review/archive controls
- [x] Initial exact-context experience grouping and human-reviewed lesson proposals (provenance retained; no automatic promotion)
- [x] User-triggered conversation memory proposals with exact user-message evidence and explicit review (initial)
- [ ] Verified conversation/session summarisation into episodic memory
- [x] Initial user-directed learning curricula and persistent practice attempts
- [x] Initial curriculum generation from user learning goals
- [ ] Gap analysis and adaptive curriculum generation
- [x] Initial practice tasks with transparent deterministic concept-coverage assessment
- [x] XP as a non-farmable progress indicator, not a proxy for intelligence

## Knowledge Engine — Initial local knowledge base
- [x] Import UTF-8 TXT, Markdown and reStructuredText files (initial)
- [x] Chunk documents with bounded size and overlap
- [x] Persistent SQLite document and chunk storage with content deduplication
- [x] SQLite FTS5 retrieval with a LIKE fallback
- [x] Source-linked excerpts and chunk citations
- [x] Agent context grounding from local knowledge with untrusted-source boundaries
- [x] TUI and Studio document ingestion, search and deletion
- [ ] Embedding-based semantic retrieval and hybrid ranking
- [x] Optional selectable-text PDF extraction (initial)
- [ ] Office document extraction and scanned-PDF OCR
- [ ] Knowledge graph, entity links and contradiction tracking

## Finalization — Studio chat and configurable search
- [x] First-party browser chat with persistent conversations (initial)
- [x] Optimistic chat feedback while the model is processing (initial)
- [x] Studio configuration for a self-hosted SearXNG endpoint
- [x] Persistent CLI search-provider configuration with environment overrides
- [x] Offline local-knowledge search remains the default
- [x] Token-level streaming from Ollama and OpenAI-compatible local adapters into Studio (initial)
- [ ] User cancellation and provider request interruption
- [ ] End-to-end integration suite against a mock model and temporary state
- [ ] Explicit opt-in live local-model smoke test and resource measurements

## Milestone 4 — Research and multimodal tools
- [x] Search provider interface with optional SearXNG and Brave adapters (initial)
- [x] Offline fallback to the local Knowledge Engine
- [x] Persistent research runs and source vault
- [x] Source provenance, URL deduplication and pending/approved/rejected review states
- [x] TUI, Studio and API research workflows (initial)
- [x] Bounded public web page retrieval and text extraction with URL/redirect validation (initial)
- [x] Initial multi-source synthesis with validated source-ID citations (human-approved sources only)
- [ ] Automated source freshness and cross-check signals
- [ ] PDF / document extraction
- [ ] Image analysis adapters
- [ ] Audio transcription and analysis
- [ ] Video frame and audio pipeline

## Milestone 5 — Skills and evaluation
- [x] Declarative skill manifests with instructions, tool scope and review checklist (initial)
- [x] Draft / pending / active / disabled lifecycle with explicit human approval (initial)
- [x] Immutable version snapshots and safe manifest import/export (initial)
- [ ] Skill execution harness with isolated, permissioned tool workflows
- [x] Initial automated skill evaluation: deterministic benchmark suites, baseline vs with-skill comparison and stored evidence (`/eval`)
- [x] Accepted evidence proposals can create non-active Skill drafts; existing human review is still required
- [ ] Regression gates that block activation and larger benchmark suites
- [ ] Skill marketplace and signing / trust metadata

## Milestone 6 — Training and evolution
- [ ] Dataset curation and consent / licensing checks
- [x] Initial baseline benchmark suite and score timeline (`/eval run`, `/evolve`)
- [x] Read-only Evolution Feedback Loop for benchmark regressions, recurring failures, skill evaluation warnings and repeated experience blockers
- [ ] Optional LoRA training integrations
- [ ] Compare base and candidate checkpoints
- [ ] Regression gates and rollback
- [ ] Hardware-aware training profiles

## Milestone 7 — Background autonomy
- [ ] Scheduler and quiet hours
- [ ] User-defined goals and resource budgets
- [ ] Pause / resume / stop controls
- [ ] Daily learning reports
- [ ] Safe self-extension workflow

## Milestone 8 — Ecosystem
- [ ] Plugin SDK
- [ ] Export / import portable agent identity
- [ ] Compatible memory transfer between models
- [x] Initial sequential multi-agent specialist orchestration using the primary model only
- [x] Mission planning and adaptive replanning delegated to Analyst → Planner specialists (initial)
- [x] Mission task execution routed through task-specific specialist prompts with the primary model (initial)
- [ ] Optional multi-model specialist network
- [ ] Extension catalogue and signing / trust metadata

## Design constraints
- Local-first and usable without an API key.
- Optional capabilities must remain optional.
- Core dependencies should stay lightweight.
- Every claimed improvement must be evaluated against a reproducible baseline.
- Tool execution and self-modification require scoped permissions and explicit approval.
