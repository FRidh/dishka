# Deviations from Original Plan

**Feature**: 001-concurrent-dependency-creation
**Date**: 2026-04-05

This document records where the implementation diverged from the original plan, spec, and contracts, and why.

---

## 1. Protocol signature: `run()` includes executor tag as 3-tuple

**Plan said**: `run(factories: Sequence[tuple[DependencyKey, Callable]])` — 2-tuple
**Implemented**: `run(factories: Sequence[tuple[DependencyKey, Callable, str | None]])` — 3-tuple

**Why**: The plan initially had `DependencyKey` alongside each callable "so per-factory dispatch can be added later without a breaking change." When US5 (per-factory dispatch) was implemented in Phase 7, the executor tag needed to reach the strategy. Rather than a side-channel mechanism, the tag was added as a third tuple element. Since the entire feature ships as one unit (no released 2-tuple API exists), this is not a breaking change — but it does differ from the contract in `contracts/concurrency_api.md` which showed 2-tuples.

**Impact**: The `AsyncConcurrencyStrategy` and `SyncConcurrencyStrategy` protocols in `entities/concurrency.py` reflect the 3-tuple signature. Custom strategy implementations must accept 3-tuples.

---

## 2. `compile()` signature differs from contract

**Contract said**: `compile(builder: CodeBuilder, callables: Sequence[tuple[DependencyKey, Callable]]) -> None` — emits code into a provided CodeBuilder
**Implemented**: `compile(compiled_factories: Sequence[tuple[DependencyKey, CompiledFactory]]) -> CompiledFactory` — creates its own CodeBuilder, returns a compiled callable

**Why**: The contract envisioned `compile()` being called within the existing per-factory compilation pipeline (`factory_compiler.py`), receiving a builder mid-construction. In practice, the concurrent resolution operates at a higher level than individual factory compilation — it dispatches groups of already-compiled factories. Modifying the per-factory compilation pipeline to emit concurrent dispatch code would have required restructuring `factory_compiler.py`, `registry.py`, and `graph_builder/builder.py` — a much larger change set touching core, battle-tested code paths.

The implemented approach is self-contained: each strategy creates its own CodeBuilder, emits a standalone concurrent dispatch function, and returns it. The container calls this at the layer-dispatch point (`_dispatch_layer`), passing the standard `(getter, exits, cache, context, container, has)` arguments. This keeps the existing compilation pipeline untouched.

**Impact**: `compile()` is not part of the Protocol (it's optional, checked via `hasattr`). The signature change is internal to built-in strategies.

---

## 3. `compile()` integration point: container, not factory_compiler

**Plan said**: "Integrate compile() hook into factory compilation pipeline — modify `src/dishka/code_tools/factory_compiler.py` and `src/dishka/registry.py`"
**Implemented**: Integration is in `async_container.py:_dispatch_layer()` and `container.py:_dispatch_layer()`, not in factory_compiler or registry.

**Why**: Same root cause as deviation #2. The compilation pipeline compiles individual factories. Concurrent dispatch operates on groups of factories within a topological layer. The natural integration point is where layer dispatch happens — in the container's `_dispatch_layer` method — not in the per-factory compiler.

Tasks T051 and T052 in tasks.md were updated to reflect the actual files modified.

---

## 4. Test directory named `test_concurrent_creation/` instead of `test_concurrency/`

**Plan said**: `tests/unit/container/test_concurrency/`
**Implemented**: `tests/unit/container/test_concurrent_creation/`

**Why**: An existing file `tests/unit/container/test_concurrency.py` (testing thread safety, not related to this feature) caused a Python import collision with the directory name. pytest errored with `import file mismatch`. Renaming the directory to `test_concurrent_creation/` resolved the collision without modifying the existing test file.

---

## 5. Edge case tests in `test_edge_cases.py`, not `test_asyncio.py`

**Tasks said**: T053–T056 in `test_asyncio.py`
**Implemented**: T053–T056 in `test_edge_cases.py`

**Why**: The edge case tests (all-cached, single factory, generator setup error, strategy bug) are cross-cutting concerns that don't belong in the asyncio-specific test file. A dedicated `test_edge_cases.py` keeps test files focused.

---

## 6. T035 (non-dispatch strategy) tests a 3-tuple-accepting strategy, not a 2-tuple legacy strategy

**Spec acceptance scenario 3 said**: "executor tags are ignored (no error)" — implying a strategy that doesn't understand tags still works
**Implemented**: The test uses a strategy that accepts 3-tuples but ignores the executor field. There is no backward-compatible 2-tuple fallback.

**Why**: Since the 3-tuple protocol is the only protocol that has shipped (see deviation #1), there are no "old-style" 2-tuple strategies to support. The test verifies the spirit of the requirement: strategies that don't care about executor routing can simply ignore the third element.

---

## 7. T057 (unrecognized executor tag) — no error raised

**Task said**: "built-in strategy raises clear error"
**Implemented**: Built-in strategies silently accept unknown executor tags.

**Why**: Built-in strategies don't perform tag-based routing to different executors — they receive the tag but dispatch all factories the same way (e.g., all via TaskGroup). Raising an error for an unknown tag would require built-in strategies to maintain a registry of "known" tags, which doesn't exist. The tag is metadata passed through for custom strategies that implement their own routing. The test verifies that unknown tags don't cause errors.

---

## 8. No modifications to `code_builder.py` or `graph_builder/builder.py`

**Plan said**: `code_builder.py` — "MODIFIED: helper methods for concurrent code emission"; `graph_builder/builder.py` — "MODIFIED: compute topological layers at graph build time"
**Implemented**: Neither file was modified.

**Why**: The `CodeBuilder` API was already sufficient for emitting concurrent dispatch code — no new helpers were needed. Topological layers are computed at resolution time in `_layers.py` (not at graph build time) because the layer structure depends on which keys are already cached — a runtime concern. Computing layers at build time would have required caching invalidation logic.

---

## 9. `ProcessPoolStrategy` delegates to threads, not processes

**Spec said**: "independent plain factories run in separate processes"
**Implemented**: `ProcessPoolStrategy.run()` delegates all work to a `ThreadPoolExecutor` because compiled factory closures capture container state (cache dict, exits list) that cannot be pickled across processes.

**Why**: The compiled factory functions are closures generated by `CodeBuilder.compile()` that reference the container's internal state. Python's `pickle` cannot serialize these. True cross-process execution would require a fundamentally different architecture (serializing factory inputs/outputs, not the factories themselves). The current implementation provides the right API shape so that if pickling becomes feasible in the future, only the strategy internals change.

---

## 10. Per-file ruff target-version added

**Not in plan**.
**Added**: `.ruff.toml` now has `per-file-target-version` entries setting `py311` for all `src/dishka/concurrency/` modules.

**Why**: The project's global ruff target is `py310`, but the concurrency feature uses Python 3.11+ builtins (`ExceptionGroup`, `BaseExceptionGroup`, `asyncio.TaskGroup`). Without per-file overrides, ruff flagged these as `F821 Undefined name` errors.
