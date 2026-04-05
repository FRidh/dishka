# Research: Concurrent Dependency Creation

**Feature**: 001-concurrent-dependency-creation
**Date**: 2026-04-05

## R-001: Python Version Handling (3.10 vs 3.11+)

**Decision**: Keep minimum Python version at 3.10. The concurrency feature is importable on 3.10 but `AsyncioStrategy` raises `RuntimeError` at container creation if `asyncio.TaskGroup` is unavailable.

**Rationale**: The project already uses conditional dependencies (`exceptiongroup>=1.1.3; python_version<'3.11'` in pyproject.toml). The same pattern applies here — the concurrency module is pure Python with no 3.11-only imports at module level. `asyncio.TaskGroup` is imported inside `AsyncioStrategy.run()` or guarded by a version check. `TrioStrategy` works on 3.10+ (trio has its own nursery). `ThreadPoolStrategy` and `ProcessPoolStrategy` use `concurrent.futures` (available since 3.2). Bumping the minimum to 3.11 would be a MAJOR version change per the constitution — disproportionate for a single optional feature.

**Alternatives considered**:
- Bump minimum to 3.11: Rejected — breaking change per constitution, penalizes users on 3.10 who don't need concurrency.
- Backport `TaskGroup` via `exceptiongroup` + custom impl: Rejected — unnecessary complexity; the `exceptiongroup` package provides `ExceptionGroup` but not `TaskGroup`.

## R-002: Topological Layer Computation from Registry

**Decision**: Implement a `compute_topological_layers(registry, root_key)` function that builds the sub-DAG for a `get()` call and returns layers (list of lists of `DependencyKey`).

**Rationale**: `Registry.get_factory(key)` returns a `Factory` with `.dependencies` (positional) and `.kw_dependencies` (keyword) — both are sequences/mappings of `DependencyKey`. This is sufficient to build the full dependency sub-graph for any root key. The algorithm:

1. Starting from root key, BFS to discover all required factories in this scope (stop at cross-scope boundaries — those are resolved via parent getter and are already cached).
2. Compute in-degree for each node (factory) based on same-scope dependencies.
3. Kahn's algorithm: peel off zero-in-degree nodes as layers.
4. Each layer = set of factories that can run concurrently.

Cross-scope dependencies are treated as already-resolved (they go through `parent_getter`) and don't appear as nodes in the sub-DAG. Dependencies already in the cache are also excluded.

**Alternatives considered**:
- Pre-compute layers at container creation time for all possible root keys: Rejected — combinatorial explosion; layers depend on which keys are already cached at call time.
- Store layers in `Registry`: Rejected — layers are call-time state (depend on current cache contents).

## R-003: Integration with Compiled Factories

**Decision**: The concurrent resolution path does NOT use compiled factories in the initial implementation. It calls `Factory.source` directly with resolved arguments from the cache. Code generation for concurrency is deferred to Priority 5.

**Rationale**: Compiled factories (from `factory_compiler.py`) inline same-scope dependencies into a single call chain. This is structurally incompatible with layer-by-layer dispatch — the compiled function recursively resolves its own dependencies, defeating concurrency. The concurrent path instead:

1. Computes topological layers (R-002).
2. For each layer, dispatches factories concurrently via the `ConcurrencyStrategy`.
3. Each factory invocation: reads dependencies from cache (guaranteed present by topological ordering), calls `Factory.source(*args, **kwargs)`, handles generator protocol if applicable, writes result to cache, appends to `_exits` if generator.
4. After all layers complete, the root value is in the cache — return it.

The non-concurrent path (no `concurrency=` kwarg) continues to use compiled factories with zero overhead. The concurrent path pays the cost of topological computation + dictionary lookups instead of inlined calls — this is acceptable because the concurrency benefit (parallel I/O) far exceeds the lookup overhead.

**Alternatives considered**:
- Modify the compiler to emit concurrent code (Priority 5 — deferred): Feasible for all built-in strategies (asyncio via `TaskGroup`, trio via nursery + wrapper coroutines, thread pool via `executor.submit`) — the existing `CodeBuilder` supports the necessary constructs. Deferred because the runtime `ConcurrencyStrategy` approach is simpler to implement and validate first, with negligible performance difference (one virtual dispatch per `get()` call). A future optional `compile(builder, callables)` method on the strategy protocol would enable this without breaking the phase 1 interface — strategies without `compile()` fall back to runtime `run()` dispatch.
- Use compiled factories but break them apart: Rejected — compiled code is a string-eval'd closure with inlined deps; decomposing it would require re-architecting the compiler.

## R-004: Generator Factories in Concurrent Context

**Decision**: Generator factories participate in concurrent dispatch normally. The concurrent resolver handles the generator protocol (advance to yield, register cleanup) identically to the compiled factory path, but as explicit Python code rather than generated code.

**Rationale**: From `factory_compiler.py`, generator handling is:
- `GENERATOR`: `gen = source(*args); solved = next(gen); exits.append((gen, None))`
- `ASYNC_GENERATOR`: `gen = source(*args); solved = await anext(gen); exits.append((None, gen))`

The concurrent resolver reproduces this logic. Within a single layer, multiple generators can be advanced concurrently (their `next()`/`anext()` calls are independent). The `exits.append()` call is safe because:
- In async: all tasks in a `TaskGroup` run on the same event loop thread — `list.append` is not concurrent.
- In sync threads: `list.append` is atomic in CPython (GIL). For extra safety, a lock can guard `_exits`.

Cleanup order: generators are appended to `_exits` in layer order (leaves first, root last). On scope exit, they're popped LIFO (root first, leaves last) — this is correct: root resources should be released before their dependencies.

**Alternatives considered**:
- Exclude generators from concurrent dispatch (resolve sequentially): Rejected — unnecessarily limits concurrency; generators are common in dishka for resource management.
- Special "synchronization point" handling for generators: Only needed for `ProcessPoolStrategy` (generators can't be pickled). For all other strategies, generators are dispatched normally.

## R-005: Process Pool + Generator Synchronization Points

**Decision**: `ProcessPoolStrategy` dispatches only non-generator factories (`FactoryType.FACTORY`) to the process pool. Generator factories (`FactoryType.GENERATOR`) run in the calling process. The topological layer computation identifies generator factories and splits layers accordingly.

**Rationale**: Per the spec: "Generator factories MUST always run in the calling process (sequentially); only plain factories are dispatched to the pool. Generator factories act as synchronization points." The implementation:

1. Compute topological layers normally.
2. Within each layer, partition into: `pool_eligible` (plain factories) and `local_only` (generators).
3. Dispatch `pool_eligible` to the process pool concurrently.
4. Run `local_only` sequentially in the calling process.
5. Both groups within a layer can run concurrently with each other (generators don't depend on pool factories in the same layer, by definition of topological layers).

Actually, since generators in the same layer are independent of each other AND of the pool factories (all their deps are resolved in earlier layers), generators can run concurrently with pool factories — they just run in the main process while pool factories run in worker processes.

**Alternatives considered**:
- Run generators in worker processes via dill/cloudpickle: Rejected — adds dependency, fragile, and generators need access to the container's `_exits` list.
- Split layers further to serialize generators: Over-constraining — generators in the same layer are independent and can overlap with pool work.

## R-006: Cache and Lock Interaction

**Decision**: The concurrent resolution path acquires the existing per-scope lock for the entire `get()` call (same as today). Within the locked section, topological layers are computed and dispatched. The lock prevents concurrent `get()` calls from interfering with each other.

**Rationale**: The existing lock serializes `get()` calls per scope. This is preserved — the concurrent feature parallelizes *within* a single `get()` call (multiple factories in one layer), not *across* multiple `get()` calls. This is correct because:
- Cache writes within a `get()` are ordered by topological layers — no races.
- Two concurrent `get()` calls could both try to write the same cache key — the lock prevents this.
- The lock scope is the same as today: acquired at `get()` entry, released at `get()` exit.

For async, this means `asyncio.Lock` serializes `get()` calls. Within a single `get()`, the `TaskGroup` dispatches concurrent factories — this works because `asyncio.Lock` is reentrant within the same task (the lock holder's task spawns child tasks in the `TaskGroup`, and those child tasks don't acquire the lock — they just write to the cache directly).

**Alternatives considered**:
- Fine-grained per-key locks: Rejected — topological ordering makes them unnecessary (no concurrent writes to the same key within a `get()` call), and per-key locks add complexity for cross-`get()` races that the existing scope lock already handles.
- No locking (rely on topological ordering alone): Rejected — doesn't protect against concurrent `get()` calls from different tasks/threads.

## R-007: Error Handling and Cancellation

**Decision**: Use structured concurrency primitives (`asyncio.TaskGroup`, trio nursery, `concurrent.futures` `as_completed` + cancel) for error propagation and cancellation. The `ConcurrencyStrategy.run()` method is responsible for collecting results and propagating errors.

**Rationale**:
- `asyncio.TaskGroup`: Automatically cancels remaining tasks when one raises. The exception propagates as an `ExceptionGroup` — the resolver unwraps single-exception groups to preserve the original error type.
- trio nursery: Same semantics — cancels sibling tasks on error.
- `ThreadPoolExecutor`: `executor.submit()` + `as_completed()` — on first error, cancel remaining futures and propagate.
- `ProcessPoolExecutor`: Same as thread pool.

For parent cancellation: `asyncio.TaskGroup` and trio nurseries handle this natively — cancelling the parent task cancels all children. For thread pools, `Future.cancel()` prevents pending submissions but can't interrupt running threads — this is a known limitation of `concurrent.futures`.

On error, factories that have already completed (including generators that yielded) remain registered in `_exits` — they will be cleaned up on scope exit, which is correct behavior.

**Alternatives considered**:
- Custom error aggregation: Rejected — structured concurrency primitives already handle this correctly.
- Wrapping errors in a dishka-specific exception type: Rejected — spec says "propagate as-is."
