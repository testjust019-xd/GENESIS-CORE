# GENESIS CORE Roadmap

This roadmap describes intended work. A listed feature is not implemented until it is present, tested and documented.

## Milestone 0 — Foundation
- [x] Python package and CLI entry point
- [x] Linux hardware diagnostics
- [x] Local web status endpoint and dashboard
- [ ] Automated tests and CI
- [ ] Configuration validation and structured logs

## Milestone 1 — Model connectivity
- [ ] Common model adapter interface
- [ ] Ollama adapter
- [ ] llama.cpp server adapter
- [ ] LM Studio OpenAI-compatible adapter
- [ ] Hugging Face local adapter
- [ ] Optional remote API mentor providers
- [ ] Model capability and context-window inspection

## Milestone 2 — Agent runtime
- [ ] Mission and goal representation
- [ ] Planner / executor / observer loop
- [ ] Tool registry with JSON schemas
- [ ] Permission profiles and approval workflow
- [ ] Timeouts, budgets, retries and audit log

## Milestone 3 — Memory and learning
- [ ] Session and episodic memory
- [ ] Searchable knowledge store with provenance
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
