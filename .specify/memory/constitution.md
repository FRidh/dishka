<!--
SYNC IMPACT REPORT
==================
Version change: 1.2.0 → 1.2.1
Bump rationale: PATCH — clarified and strengthened the no-unnecessary-changes
  rule in Quality Standards: reformatting or touching code outside the PR scope
  is explicitly prohibited, not just discouraged. Existing wording already
  covered ruff format; this makes the constraint general and unambiguous.
Modified principles: None.
Added content: Explicit "minimize unnecessary code changes" rule in Quality
  Standards (Linting section expanded).
Removed content: None.
Templates checked:
  - .specify/templates/plan-template.md ✅ (no conflicts)
  - .specify/templates/spec-template.md ✅ (no conflicts)
  - .specify/templates/tasks-template.md ✅ (no conflicts)
Deferred items: None.
-->

# Dishka Constitution

## Core Principles

### I. Performance-First

Dishka MUST be fast enough that DI overhead is never a bottleneck for adopters.
The library outperforms alternatives by design, not by accident.

- Resolution of cached dependencies MUST have negligible overhead
  (no per-call allocation in the hot path).
- Benchmarks MUST be maintained and run as part of CI for regressions.
- New features MUST NOT degrade existing performance characteristics
  without explicit justification and a documented trade-off.
- Complexity introduced solely for performance MUST be measured and
  validated before merging.

### II. Correctness Through Type Hints

All public API MUST be fully typed. Type hints are not documentation—they
are machine-checked contracts.

- Every public class, function, and method MUST carry complete type
  annotations.
- mypy MUST pass on `src/dishka/` (excluding vendored `_adaptix/`) at
  the project's configured strictness level.
- New code MUST NOT use `Any` without an inline comment justifying the
  exception.
- Type information MUST be leveraged at runtime where it drives
  resolution (e.g., `DependencyKey`).

### III. Test-First (NON-NEGOTIABLE)

Tests MUST be written before or alongside implementation. No feature or
bugfix is complete without tests.

- Unit tests MUST cover all new logic in `tests/unit/`.
- Framework integrations MUST have integration tests under
  `tests/integrations/`.
- The Red-Green-Refactor cycle MUST be followed: tests fail first, then
  implementation makes them pass.
- Test coverage for core modules (`container`, `graph_builder`,
  `provider`) MUST NOT regress.
- Tests MUST NOT use wall-clock time measurements in assertions (e.g.,
  `time.sleep`, `asyncio.wait_for` timeouts, or `assert elapsed < N`).
  Concurrent execution MUST be verified using synchronization primitives
  such as `threading.Event`, `asyncio.Event`, `threading.Barrier`, or
  trio checkpoints—never by measuring elapsed time.

### IV. Minimal, Clean API

Dishka focuses exclusively on dependency injection. Scope creep into
unrelated concerns is prohibited.

- The public surface MUST remain small: `Provider`, `@provide`,
  `@alias`, `@decorate`, `make_container`, scopes.
- New public symbols require explicit justification—prefer extending
  existing abstractions over adding new ones.
- Framework integrations MUST NOT leak dishka internals into user code.
- Users MUST NOT need to annotate their own classes with dishka-specific
  markers to participate in DI.

### V. Modular, Reusable Providers

Provider design MUST encourage decomposition and reuse rather than
monolithic factories.

- Each `Provider` SHOULD have a single, clear responsibility.
- Providers MUST be independently testable in isolation.
- The scoping model (APP → REQUEST → ACTION → STEP) MUST remain the
  canonical contract for dependency lifetimes.
- Cross-scope dependencies MUST be validated at container creation time,
  not at runtime.

### VI. Async Compatibility Without Abstraction Layers

Async code MUST work natively with both `asyncio` and `trio`.
Compatibility MUST be achieved directly—without delegating to anyio or
any other async-abstraction library.

- `make_async_container()` and all async provider factories MUST
  function correctly under both `asyncio` and `trio` event loops.
- anyio MUST NOT be added as a dependency; compatibility is the
  responsibility of dishka's own code.
- Async primitives (locks, context vars, task groups) MUST be sourced
  from the standard library (`asyncio`, `contextvars`) or from
  sniffio-style runtime detection where unavoidable—never from a
  mandatory third-party async-abstraction layer.
- New async features MUST be tested under both `asyncio` and `trio` in
  CI before merge.
- If a behaviour is fundamentally impossible to reconcile between the
  two runtimes, the discrepancy MUST be documented explicitly in the
  public API and raised as a tracked issue before shipping.

## Quality Standards

**Python version**: The current minimum supported version is **Python 3.10**.
Bumping the minimum to 3.11 is permitted when there is a concrete reason
(e.g., a needed stdlib feature or simplification). Such a bump MUST be
treated as a breaking change and require a MAJOR version increment.

**Linting**: Code MUST pass ruff (zero errors) and ast-grep (`sg scan`) before
merge. ruff format MUST NOT be applied globally—only format code authored in
the PR. Linter rules in `linter-rules/` MUST be consulted and updated when new
code patterns are introduced. Many checks are strict; false positives MUST be
verified carefully before suppressing any warning.

**Minimal diff**: Changes MUST be limited to what is necessary to implement the
feature or fix. Code that is not touched by the change MUST NOT be reformatted,
renamed, or restructured. Incidental cleanups MUST be submitted as separate PRs.

**Type checking**: All code MUST pass mypy with no new failures. The check
excludes `integrations/` and `_adaptix/`.

**Testing**: All PRs MUST pass the full nox suite (unit tests, integration
tests, and example app tests) before merge. Integration tests for each
supported framework MUST pass in the relevant nox session before merging a
change touching that integration. Tests can be scoped by framework tag or run
against the latest library version explicitly. Requirement files are in
`/requirements/`.

**Documentation**: User-facing changes MUST include updated documentation,
built via sphinx. The build MUST produce no warnings.

**Security audit**: Changes to GitHub Actions workflows MUST be audited with
zizmor before merge.

**Spell check**: All code and documentation MUST pass the typos spell checker
before merge.

**Vendored code**: `src/dishka/_adaptix/` is excluded from linting and mypy;
changes to it require explicit review.

## Development Workflow

**Branching**: Features and bugfixes MUST be developed on branches from
`develop`; PRs target `develop`. The `main` branch reflects released versions
only.

**Compatibility**:

- New parameters MUST NOT be required; existing call sites must not break.
- Behavior changes MUST be introduced under a toggle, not unconditionally.
- Breaking changes to the public API MUST be flagged in the PR description
  and require a MAJOR version bump.

**Scope constraints**:

- New features MUST NOT exceed the scope of the IoC container. They MUST fit
  the overall API design and SHOULD be discussed with maintainers before
  implementation begins.
- Bugfixes are always welcome without prior discussion.

**Integrations**: New framework integrations are NOT accepted into the
library. Authors are encouraged to publish them as separate projects.

**Translations**: New documentation translations are accepted only when at
least three (3) maintainers are willing to support them and can translate all
future documentation changes in a timely manner.

**PR checklist** — every PR MUST:

1. Pass ruff and ast-grep linting with zero errors.
2. Pass mypy with no new failures.
3. Pass the full nox suite and any integration sessions touched by the change.
4. Pass the typos spell checker.
5. Pass the zizmor security audit if GitHub Actions files were modified.
6. Include or update tests for all changed behavior.

## Governance

This constitution supersedes all other practices. Amendments require:

1. A PR description explaining the motivation and impact.
2. Approval from at least one maintainer.
3. A migration plan for any breaking governance changes.
4. Version increment according to the policy below.

**Versioning policy**:
- MAJOR: Backward-incompatible governance/principle removals or redefinitions.
- MINOR: New principle or section added, or materially expanded guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

All PRs and code reviews MUST verify compliance with these principles.
Complexity deviations MUST be justified in the PR description and tracked.
Use `CLAUDE.md` for runtime development guidance specific to this repo.

**Version**: 1.2.1 | **Ratified**: 2026-04-05 | **Last Amended**: 2026-04-05
