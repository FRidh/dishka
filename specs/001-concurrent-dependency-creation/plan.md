# Implementation Plan: Concurrent Dependency Creation

**Branch**: `001-concurrent-dependency-creation` | **Date**: 2026-04-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-concurrent-dependency-creation/spec.md`

## Summary

Add opt-in concurrent dependency resolution to dishka. Users pass a `ConcurrencyStrategy` via `concurrency=` kwarg on `make_container()` / `make_async_container()`. The container resolves the dependency graph in topological layers — factories within each layer are independent and dispatched concurrently via the strategy. Built-in strategies: `AsyncioStrategy`, `AsyncioSemaphoreStrategy`, `TrioStrategy`, `ThreadPoolStrategy`, `ProcessPoolStrategy`. Sequential behavior is unchanged when `concurrency=` is omitted.

## Technical Context

**Language/Version**: Python 3.11+ (uses `asyncio.TaskGroup`; project minimum remains 3.10 — concurrency feature raises at construction on < 3.11)
**Primary Dependencies**: None new — stdlib only (`asyncio`, `concurrent.futures`, `contextvars`); `trio` optional for trio strategy
**Storage**: N/A
**Testing**: pytest (`tests/unit/`); concurrency verified via synchronization primitives (events, barriers), not wall-clock time
**Target Platform**: Cross-platform (Linux, macOS, Windows)
**Project Type**: Library (PyPI package)
**Performance Goals**: Zero overhead on sequential path; concurrent path overhead limited to topological computation + dict lookups (negligible vs I/O savings)
**Constraints**: No anyio dependency; no wall-clock assertions in tests; `asyncio.Lock` / scope lock semantics preserved
**Scale/Scope**: Affects `container.py`, `async_container.py`, `make_container()`, `make_async_container()`, new `concurrency/` module; ~500-800 lines new code + ~300-500 lines tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Performance-First | PASS | Zero overhead on sequential path (no code changes when `concurrency=None`). Concurrent path trades dict lookups for parallel I/O — net positive. |
| II. Correctness Through Type Hints | PASS | Protocols are fully typed. `concurrency=` kwarg is typed. No `Any` without justification. |
| III. Test-First (NON-NEGOTIABLE) | PASS | Tests use synchronization primitives (events, barriers), not wall-clock time. All scenarios from spec have acceptance tests. |
| IV. Minimal, Clean API | PASS | Two new protocols + five implementations + one new kwarg. All strategies are opt-in. No existing public symbols changed. |
| V. Modular, Reusable Providers | PASS | No changes to Provider API. Concurrency is orthogonal to provider design. |
| VI. Async Compatibility Without Abstraction Layers | PASS | asyncio and trio supported via separate code paths. No anyio. |
| Quality: Python version | PASS | Project minimum stays 3.10. Feature requires 3.11+ at runtime (checked at strategy construction). No MAJOR bump needed. |
| Quality: Linting | PASS | New code follows existing style (79-char lines, ruff, mypy). |
| Quality: Minimal diff | PASS | Changes scoped to new module + minimal modifications to container files. |
| Quality: Compatibility | PASS | New kwarg is optional with `None` default. Existing call sites unaffected. |

**Post-Phase-1 re-check**: No violations introduced. The `ConcurrencyStrategy` protocol with `run()` only is forward-compatible with a future optional `compile()` codegen hook (Priority 5) — no breaking changes needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-concurrent-dependency-creation/
├── plan.md              # This file
├── research.md          # Phase 0 output (complete)
├── data-model.md        # Phase 1 output (complete)
├── quickstart.md        # Phase 1 output (complete)
├── contracts/
│   └── concurrency_api.md  # Phase 1 output (complete)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/dishka/
├── concurrency/                    # NEW — concurrency module
│   ├── __init__.py                 # Re-exports protocols + strategies
│   ├── _protocols.py               # AsyncConcurrencyStrategy, SyncConcurrencyStrategy
│   ├── _resolver.py                # ConcurrentResolver (topological layers + dispatch)
│   ├── _asyncio.py                 # AsyncioStrategy, AsyncioSemaphoreStrategy
│   ├── _trio.py                    # TrioStrategy
│   └── _sync.py                    # ThreadPoolStrategy, ProcessPoolStrategy
├── async_container.py              # MODIFIED — add concurrency= kwarg, delegate to resolver
├── container.py                    # MODIFIED — add concurrency= kwarg, delegate to resolver
└── __init__.py                     # MODIFIED — re-export new public symbols

tests/unit/
└── test_concurrency/               # NEW — concurrency tests
    ├── test_asyncio_strategy.py    # Priority 1: basic async concurrency
    ├── test_semaphore.py           # Priority 2: bounded concurrency
    ├── test_trio_strategy.py       # Priority 3: trio support
    ├── test_thread_pool.py         # Priority 4: sync thread pool
    ├── test_process_pool.py        # Priority 4: sync process pool
    ├── test_topological_layers.py  # Shared: layer computation
    ├── test_diamond.py             # Shared: deduplication
    ├── test_error_propagation.py   # Shared: error handling
    └── test_cancellation.py        # Shared: cancellation safety
```

**Structure Decision**: New `concurrency/` subpackage under `src/dishka/` keeps concurrency code isolated from existing container logic. Container files get minimal modifications (check for `_concurrency` slot, delegate to resolver if set).

## Implementation Priorities

Implementation follows the priority order defined in the spec. Each priority is independently shippable and builds on the previous.

### Priority 1: Async Concurrency (asyncio)

**Scope**: Core infrastructure + asyncio strategy

1. **Protocols** (`_protocols.py`): Define `AsyncConcurrencyStrategy` with `run()` method. Include `DependencyKey` in signature from day one (FR-013).
2. **Topological resolver** (`_resolver.py`): `ConcurrentResolver` with `_compute_layers()` (BFS + Kahn's algorithm) and `async resolve()`. Handles cache reads, factory invocation, generator protocol, `_exits` registration.
3. **AsyncioStrategy** (`_asyncio.py`): `asyncio.TaskGroup`-based implementation. Unwraps single-exception `ExceptionGroup` for clean error propagation.
4. **AsyncContainer integration** (`async_container.py`): Add `_concurrency` slot, `concurrency=` kwarg on `make_async_container()`, child propagation, branch in `_get_unlocked()`.
5. **Tests**: Concurrent resolution, diamond dedup, error propagation, cancellation, generator cleanup, no-op when single factory.

### Priority 2: Semaphore Limiting

**Scope**: Bounded asyncio concurrency

1. **AsyncioSemaphoreStrategy** (`_asyncio.py`): Wraps each task with `asyncio.Semaphore(max_concurrent)`.
2. **Tests**: Verify at most N concurrent factories with N+2 independent deps.

### Priority 3: trio Support

**Scope**: trio nursery strategy

1. **TrioStrategy** (`_trio.py`): `trio.open_nursery()` + wrapper coroutines + result dict.
2. **Tests**: Mirror asyncio tests under `trio.run()`.

### Priority 4: Sync Concurrency

**Scope**: Thread pool and process pool strategies

1. **SyncConcurrencyStrategy protocol** (`_protocols.py`).
2. **ThreadPoolStrategy** (`_sync.py`): `concurrent.futures.ThreadPoolExecutor` submission.
3. **ProcessPoolStrategy** (`_sync.py`): Generator factories partitioned to run locally.
4. **Container integration** (`container.py`): Add `_concurrency` slot, `concurrency=` kwarg on `make_container()`, branch in `_get_unlocked()`.
5. **Sync resolver path** in `_resolver.py`.
6. **Tests**: Thread pool concurrency, process pool with generators, error propagation.

### Priority 5: Code Generation (Deferred — Out of Scope)

**Scope**: Optional `compile()` codegen hook on strategy protocols

This priority is **not implemented** in the current feature branch. It is documented here to ensure the Priority 1-4 design does not preclude it.

**What would change**:
- Add optional `compile(builder: FactoryBuilder, callables: FactoryBatch) -> None` method to both protocols (checked via `hasattr` or separate mixin — no breaking change to `run()`-only implementations).
- `factory_compiler.py`: When compiling a factory whose deps include concurrent-eligible siblings, check if the strategy has `compile()`. If yes, delegate code emission to the strategy. If no, emit a runtime `strategy.run(...)` call.
- Built-in codegen templates:
  - **asyncio**: `async with asyncio.TaskGroup() as tg: tg.create_task(get_X(...))` for each sibling
  - **trio**: `async with trio.open_nursery() as nursery:` + wrapper coroutine defs + result dict
  - **thread pool**: `executor.submit(get_X, ...)` + result collection
- Custom strategies can implement `compile()` to emit their own code.
- The existing `CodeBuilder` already supports all necessary constructs (function defs, `async with`, dicts, assignments).

**Why deferred**: The runtime `ConcurrencyStrategy.run()` approach delivers identical functionality with negligible overhead (one virtual dispatch per `get()` call). Codegen is a pure optimization — worth pursuing after the runtime approach is stable and validated.

**Interface guarantee**: No changes to the Priority 1-4 public interface are needed to support Priority 5 later.

## Complexity Tracking

No constitution violations to justify. The design adds one new subpackage and minimal modifications to two existing files, staying well within scope constraints.
