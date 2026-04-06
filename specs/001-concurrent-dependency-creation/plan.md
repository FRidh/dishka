# Implementation Plan: Concurrent Dependency Creation

**Branch**: `001-concurrent-dependency-creation` | **Date**: 2026-04-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-concurrent-dependency-creation/spec.md`

## Summary

Add concurrent dependency creation to dishka. When a `ConcurrencyStrategy` is passed via `concurrency=` to `make_container()`/`make_async_container()`, independent factories within each topological layer of the resolution DAG are dispatched concurrently. The feature delivers: runtime dispatch (`run()`), code generation (`compile()`), per-factory executor routing (`@provide(executor=…)`), and built-in strategies for asyncio, trio, and thread/process pools. Sequential behavior remains the default with zero overhead when concurrency is not configured.

## Technical Context

**Language/Version**: Python 3.11+ (uses `asyncio.TaskGroup`, `ExceptionGroup`)  
**Primary Dependencies**: None new — stdlib only (`asyncio`, `concurrent.futures`, `contextvars`); `trio` optional for trio strategy  
**Storage**: N/A  
**Testing**: pytest, nox (unit + integration sessions)  
**Target Platform**: Linux/macOS/Windows (same as dishka)  
**Project Type**: Library  
**Performance Goals**: Zero overhead on sequential path; concurrent path must show overlap via synchronization primitives (FR-015)  
**Constraints**: No anyio dependency; no wall-clock assertions in tests; line length 79 chars; strict mypy  
**Scale/Scope**: Core library feature touching container, registry, code_tools, dependency_source, entities, and provider modules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Performance-First | ✅ PASS | Zero overhead when concurrency not configured; concurrent path adds one virtual dispatch per layer per `get()` call. Codegen eliminates even that. |
| II. Correctness Through Type Hints | ✅ PASS | All new protocols, strategies, and public API fully typed. mypy strict on new code. |
| III. Test-First (NON-NEGOTIABLE) | ✅ PASS | All 6 user stories have acceptance scenarios with synchronization-based verification. No wall-clock assertions. TDD cycle required. |
| IV. Minimal, Clean API | ✅ PASS | Single new kwarg `concurrency=` on existing functions. `@provide(executor=)` extends existing decorator. Strategy protocols are opt-in. |
| V. Modular, Reusable Providers | ✅ PASS | Providers unchanged; executor tag is optional metadata. |
| VI. Async Compatibility Without Abstraction Layers | ✅ PASS | Separate asyncio and trio code paths; no anyio. |
| Quality: Python version | ⚠️ NOTE | Requires 3.11+ (for `asyncio.TaskGroup`). This is a minimum version bump from 3.10 → 3.11 for the concurrent feature. Constitution allows this with justification: `TaskGroup` is the correct stdlib primitive for structured concurrency. Must be treated as breaking change (MAJOR version bump). |
| Quality: Minimal diff | ✅ PASS | Changes scoped to concurrency feature only. |
| Quality: Linting | ✅ PASS | All new code passes ruff, ast-grep, mypy. |

## Project Structure

### Documentation (this feature)

```text
specs/001-concurrent-dependency-creation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/dishka/
├── entities/
│   ├── key.py                    # DependencyKey (unchanged)
│   └── concurrency.py            # NEW: ConcurrencyStrategy protocols, ExecutorTag, built-in strategy classes
├── dependency_source/
│   └── factory.py                # MODIFIED: add executor tag field to Factory
├── provider/
│   └── make_factory.py           # MODIFIED: add executor= kwarg to @provide
├── code_tools/
│   ├── code_builder.py           # MODIFIED: helper methods for concurrent code emission
│   └── factory_compiler.py       # MODIFIED: topological layer compilation, compile() hook integration
├── graph_builder/
│   └── builder.py                # MODIFIED: compute topological layers at graph build time
├── registry.py                   # MODIFIED: store topological layers, pass to compiler
├── async_container.py            # MODIFIED: concurrent resolution path using strategy.run()
├── container.py                  # MODIFIED: concurrent resolution path for sync strategies
└── concurrency/                  # NEW: directory for strategy implementations
    ├── __init__.py
    ├── _asyncio.py               # AsyncioStrategy, AsyncioSemaphoreStrategy (run + compile)
    ├── _trio.py                  # TrioStrategy (run + compile)
    └── _sync.py                  # ThreadPoolStrategy, ProcessPoolStrategy (run + compile)

tests/unit/
└── container/
    └── test_concurrency/         # NEW: test directory
        ├── test_asyncio.py       # Async concurrent resolution, error propagation, cancellation
        ├── test_semaphore.py     # Semaphore limiting
        ├── test_trio.py          # Trio concurrent resolution
        ├── test_sync.py          # Thread pool, process pool
        ├── test_dispatch.py      # Per-factory executor dispatching
        ├── test_codegen.py       # Codegen parity tests for all strategies
        └── test_diamond.py       # Diamond deduplication across all strategies
```

**Structure Decision**: Follows existing dishka layout. New `concurrency/` package under `src/dishka/` for strategy implementations. New `entities/concurrency.py` for protocols and types (consistent with other entity definitions in `entities/`). Tests in `tests/unit/container/test_concurrency/`.

## Complexity Tracking

No constitution violations requiring justification. The Python 3.11+ requirement is noted and accepted per constitution rules (concrete reason: `asyncio.TaskGroup`).
