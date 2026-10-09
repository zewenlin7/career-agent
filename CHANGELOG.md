# Changelog

## Unreleased

### Added — v0.1b Resume Compiler

- Versioned hand-authored ResumeVariant documents and immutable revision persistence,
  exact Profile/JD references, captured fact revisions and duplicate/invalid input validation.
- Render-time verified-fact/snapshot/requirement checks, numeric token consistency and
  explicitly declared hard-field checks. No semantic truth or LLM tailoring claim.
- Deterministic full/short/optional content selection, stable priority tie-breakers,
  required-content preservation, decision records and an eight-compilation hard cap.
- Canonical zh-CN A4 single-column template with Chinese headings and mixed-script content,
  pinned Typst 0.15.1 and official Noto Sans CJK SC 2.004 Regular/Bold fonts.
- External font dependency setup with immutable URLs, SHA-256 verification, offline preflight,
  render-local snapshots and identical local/CI preparation; no system/embedded font fallback.
- Locale/schema/template/font-policy versions, actual font family and verified file hashes
  in artifact metadata; no font paths, font binaries or PDFs in git/wheel.
- Fixed 10.5 pt body, margins/spacing, compiler timeout and safe structured errors.
- Actual PDF inspection for page count, A4 dimensions, extractable/retained text,
  character bounds, font/minimum size and known glyph failures.
- RenderArtifact persistence with exact Variant revision FK, SHA-256, private opaque file
  references, findings, attempts and schema/template/layout/compiler/font version metadata.
- Create/get/revise/render Variant APIs and artifact metadata/download APIs; failed render
  reports are persisted without a misleading successful/downloadable file.
- Private artifact storage, traversal/symlink defenses, download integrity validation,
  request rollback file cleanup and template-injection regression tests.
- Three Chinese acceptance fixtures plus a mixed-script/font regression fixture and local
  example-generation script; English data remains auxiliary regression input. No LLM calls.
- CI configuration for pinned Typst 0.15.1; README/TODO/architecture updated to actual scope.

### Fixed — v0.1b review

- Retained-text validation now matches ordered, non-overlapping ranges in immutable normalized
  extraction. Deleting headings can no longer manufacture body text; duplicate/missing/overlapping
  text, Chinese/English and Unicode normalization have regression coverage.
- Accepted status is assigned only after byte read and SHA-256 calculation. Read/hash/storage
  failures clear success/file metadata, persist failed reports and cannot be downloaded.
- CJK punctuation uses a fixed content gutter, and vector bullets avoid ambiguous text-glyph
  mappings without relaxing page/font/retained-text validation or shrinking content.

### Verified locally — v0.1b

- Real CLI: `typst 0.15.1 (unknown commit)`; official font dependency setup completed from an
  empty external cache. Regular/Bold hashes match the pinned manifest; offline preflight passes.
- `normal_one_page_zh_cn`: accepted, one page, one attempt.
- `compressible_overflow_zh_cn`: 5 → 3 → 1 pages; short-form replacement then optional item
  removal in three attempts, preserving every required item.
- `impossible_one_page_zh_cn`: required content remains four pages; `layout_failed`, no accepted PDF.
- `mixed_script_font_regression`: accepted, one page; Chinese/Latin/numbers/punctuation extracted.
- Both successful Chinese acceptance PDFs were rendered to images and visually inspected:
  readable Chinese and technical terms, aligned bullet markers, no obvious tofu/overlap/clipping.
  This is an agent visual inspection, not a claim of user sign-off or perfect typography.
- Unit tests: **74 passed**. Integration tests: **50 passed**, real PostgreSQL and Typst.
- Final full suite: **124 passed in 13.36s**; includes empty-DB upgrade to head and Alembic
  drift check, failed read/hash report persistence and download refusal.
- Ruff check passes; formatter: **45 files already formatted**; strict mypy: **25 source files**.
- Wheel builds offline, includes the trusted Chinese `.typ` template and no font/PDF binaries.
- Tracked/untracked hygiene and whitespace checks pass. No system fonts were installed.

### Added — v0.1a Foundation

- v0.1a Foundation modular Python package with uv lockfile, Python 3.12 baseline,
  FastAPI/Pydantic v2, async SQLAlchemy/asyncpg, Alembic and PostgreSQL Compose configuration.
- Initial migration for personal profiles/facts/STAR structures, sources, companies,
  versioned jobs/requirements, application/event history, interview/knowledge records
  and run/step/model-call/tool-call/observation metadata.
- Explicit fact verification/rejection, proposed replacements with lineage/revisions,
  versioned profile/JD writes, application state/correction events and transaction guards.
- Typed `/api/v1` domain APIs and read-only run/step queries, pagination, stable safe errors.
- Model-independent request/task/schema contracts, static tier/capability/privacy policy,
  injected fake provider, validated results and usage/latency/cost/version metadata.
- Nullable provenance fields, validated metadata JSONB and unknown-usage semantics.
- External private-data configuration, ignore rules, allowlisted logs, basic redaction,
  private-path/raw-provider-error protection and synthetic fixtures.
- PostgreSQL integration/API tests including migration drift, FK/unique/delete behavior,
  rollback, revisions, concurrent application writes and privacy metadata rejection.
- Ruff, strict mypy and a synthetic PostgreSQL GitHub Actions workflow.
- README with actual capabilities/setup/API/testing, architecture boundaries and full
  milestone/optional-extension roadmap in TODO.

### Verified locally — v0.1a Foundation

- Docker Compose PostgreSQL starts healthy; initial Alembic upgrade succeeds from empty.
- Locked dependency installation succeeds in a new virtual environment.
- Full suite: **57 passed**, no warnings; includes real temporary PostgreSQL databases.
- Ruff check and format check pass; strict mypy passes for all 14 source modules.
- FastAPI starts under Uvicorn; live HTTP health and OpenAPI (21 operations) verified.
- Alembic reports no schema drift; tracked and untracked files pass whitespace checks.

The user confirmed v0.1a was committed/pushed and its remote CI passed.
The v0.1b changes have not been committed/pushed; their updated remote CI has not run.
No final v0.1.0 release has been made.
