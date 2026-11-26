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

## Milestone 1 — Model connectivity
- [x] Common chat adapter contract (initial)
- [x] Ollama chat adapter (initial)
- [x] llama.cpp OpenAI-compatible chat adapter (initial)
- [x] LM Studio OpenAI-compatible chat adapter (initial)
- [x] Persistent primary-model selection for supported local runtimes
- [x] Provider adapter and agent-loop tests pass in CI
- [ ] Hugging Face Transformers local adapter
- [ ] Optional remote API mentor providers and secure secret storage
- [x] Hardware-aware first-run model recommendations and opt-in Ollama download (initial)\n- [ ] Model capability and context-window inspection
- [ ] Streaming responses and cancellation

## Milestone 2 — Agent runtime
- [x] Basic context-aware chat loop (initial)
- [x] Persistent mission and goal representation (initial CRUD and status transitions)
- [x] Structured mission plans persisted as ordered tasks
- [x] Step-by-step mission execution with stored results and resume after interruption
- [x] Bounded planner / executor / observer loop over chat adapters (initial)
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
- [x] Explicit capture of fully completed missions into episodic memory using persisted observer-checked outcomes (initial)\n- [ ] Verified conversation/session summarisation into episodic memory
- [ ] User-directed learning missions
- [ ] Gap analysis and curriculum generation
- [ ] Practice tasks and skill assessments
- [ ] XP as a progress indicator, not a proxy for intelligence

## Milestone 4 — Research and multimodal tools
- [ ] Search providers and browser workflow
- [ ] Source verification and citation storage
- [ ] PDF / document extraction
- [ ] Image analysis adapters
- [ ] Audio transcription and analysis
- [ ] Video frame and audio pipeline

## Milestone 5 — Training and evolution
- [ ] Dataset curation and consent / licensing checks
- [ ] Baseline benchmark suite
- [ ] Optional LoRA training integrations
- [ ] Compare base and candidate checkpoints
- [ ] Regression gates and rollback
- [ ] Hardware-aware training profiles

## Milestone 6 — Background autonomy
- [ ] Scheduler and quiet hours
- [ ] User-defined goals and resource budgets
- [ ] Pause / resume / stop controls
- [ ] Daily learning reports
- [ ] Safe self-extension workflow

## Milestone 7 — Ecosystem
- [ ] Plugin SDK
- [ ] Export / import portable agent identity
- [ ] Compatible memory transfer between models
- [ ] Optional multi-model specialist network
- [ ] Extension catalogue and signing / trust metadata

## Design constraints
- Local-first and usable without an API key.
- Optional capabilities must remain optional.
- Core dependencies should stay lightweight.
- Every claimed improvement must be evaluated against a reproducible baseline.
- Tool execution and self-modification must be permissioned and auditable.
