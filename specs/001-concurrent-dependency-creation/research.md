# Research: Concurrent Dependency Creation

**Feature**: 001-concurrent-dependency-creation
**Date**: 2026-04-05

## R-001: Python Version Handling (3.10 vs 3.11+)

**Decision**: Keep minimum Python version at 3.10. The concurrency feature is importable on 3.10 but `AsyncioStrategy` raises `RuntimeError` at container creation if `asyncio.TaskGroup` is unavailable.

**Rationale**: The project already uses conditional dependencies (`exceptiongroup>=1.1.3; python_version<'3.11'` in pyproject.toml). The same pattern applies here — the concurrency module is pure Python with no 3.11-only imports at module level. `asyncio.TaskGroup` is imported inside `AsyncioStrategy.run()` or guarded by a version check. `TrioStrategy` works on 3.10+ (trio has its own nursery). `ThreadPoolStrategy` and `ProcessPoolStrategy` use `concurrent.futures` (available since 3.2). Bumping the minimum to 3.11 would be a MAJOR version change per the constitution — disproportionate for a single optional feature.

**Alternatives considered**:
- Bump minimum to 3.11: Rejected — breaking change per constitution, penalizes users on 3.10 who don't need concurrency.
- Backport `TaskGroup` via `exceptiongroup` + custom impl: Rejected — unnecessary complexity; the `exceptiongroup` package provides `ExceptionGroup` but not `TaskGroup`.

## R-002: Topological Layer Computation

**Decision**: Implement a `compute_topological_layers(registry, root_key)` function that builds the sub-DAG for a `get()` call and returns layers (list of lists of `DependencyKey`).

**Rationale**: `Registry.get_factory(key)` returns a `Factory` with `.dependencies` (positional) and `.kw_dependencies` (keyword) — both are sequences/mappings of `DependencyKey`. This is sufficient to build the full dependency sub-graph for any root key. The algorithm:

1. Starting from root key, BFS to discover all required factories in this scope (stop at cross-scope boundaries — those are resolved via parent getter and are already cached).
2. Compute in-degree for each node (factory) based on same-scope dependencies.
3. Kahn's algorithm: peel off zero-in-degree nodes as layers.
4. Each layer = set of factories that can run concurrently.

Cross-scope dependencies are treated as already-resolved (they go through `parent_getter`) and don't appear as nodes in the sub-DAG. Dependencies already in the cache are also excluded.

**Alternatives considered**:
- Pre-compute layers at container creation time for all possible root keys: Rejected — combinatorial explosion; layers depend on which keys are already cached at call time.
- `graphlib.TopologicalSorter` (stdlib 3.9+): Viable — provides `get_ready()`/`done()` group-based iteration. Evaluate during implementation.

## R-003: Integration with Compiled Factories

**Decision**: Two resolution paths coexist:
1. **Runtime path** (`run()`): Does NOT use compiled factories. Computes topological layers at `get()` time, dispatches each layer via `strategy.run()`, calls `Factory.source` directly with resolved args from cache.
2. **Codegen path** (`compile()`): Extends the existing factory compiler to emit concurrent code. At container creation time, `strategy.compile(builder, callables)` emits specialized resolution code (e.g., `async with TaskGroup()`) into the compiled factory. The compiled factory handles both sequential and concurrent layers.

**Rationale**: Compiled factories inline same-scope dependencies into a single call chain. This is structurally incompatible with layer-by-layer runtime dispatch. The runtime path bypasses compiled factories and resolves directly from the registry. The codegen path modifies the compiler to emit concurrent constructs, preserving the performance benefits of compiled code.

Both paths produce identical results. The codegen path eliminates per-`get()` virtual dispatch overhead. Strategies without `compile()` fall back to the runtime path.

**Key insight from codebase exploration**: `CodeBuilder` already supports `async with`, `await`, function definitions, and dicts via its API. It can emit `TaskGroup`, nursery, and executor patterns as raw code strings via `statement()`. Helper methods can be added for readability.

**Alternatives considered**:
- Runtime path only (defer codegen): Rejected by user — codegen must ship as part of this feature.
- Codegen only (no runtime path): Rejected — custom strategies need a simple `run()` interface; not all strategies can or want to emit code.

## R-004: Generator Factories in Concurrent Context

**Decision**: Generator factories participate in concurrent dispatch normally. The concurrent resolver handles the generator protocol (advance to yield, register cleanup) identically to the compiled factory path.

**Rationale**: Generator handling is:
- `GENERATOR`: `gen = source(*args); solved = next(gen); exits.append((gen, None))`
- `ASYNC_GENERATOR`: `gen = source(*args); solved = await anext(gen); exits.append((None, gen))`

Within a single layer, multiple generators can be advanced concurrently (their `next()`/`anext()` calls are independent). `_exits.append()` is safe because:
- In async: all tasks in a `TaskGroup` run on the same event loop thread — `list.append` is not concurrent.
- In sync threads: `list.append` is atomic in CPython (GIL). For extra safety, a lock can guard `_exits`.

**Exception**: `ProcessPoolStrategy` — generators cannot be pickled and must run in the calling process (see R-005).

## R-005: Process Pool + Generator Synchronization Points

**Decision**: `ProcessPoolStrategy` dispatches only non-generator factories to the process pool. Generator factories run in the calling process. Both groups within a layer can execute concurrently (generators in main process, plain factories in pool workers).

**Rationale**: Per the spec: "Generator factories MUST always run in the calling process (sequentially); only plain factories are dispatched to the pool."

Implementation:
1. Compute topological layers normally.
2. Within each layer, partition into: `pool_eligible` (plain factories) and `local_only` (generators).
3. Dispatch `pool_eligible` to the process pool.
4. Run `local_only` in the calling process.
5. Since both groups' dependencies are already resolved (topological ordering), they can overlap.

## R-006: Cache and Lock Interaction

**Decision**: The concurrent resolution path acquires the existing per-scope lock for the entire `get()` call. Within the locked section, topological layers are computed and dispatched. This is identical to today's locking behavior.

**Rationale**: The existing lock serializes `get()` calls per scope. The concurrent feature parallelizes *within* a single `get()` call (multiple factories in one layer), not *across* multiple `get()` calls.

- Cache writes within a `get()` are ordered by topological layers — no races.
- Two concurrent `get()` calls are serialized by the scope lock.
- For async, `asyncio.Lock` serializes `get()` calls. The `TaskGroup` within a single locked `get()` works because child tasks write to disjoint cache keys (topological layer guarantee).

## R-007: Error Handling and Cancellation

**Decision**: Use structured concurrency primitives for error propagation and cancellation. The `ConcurrencyStrategy.run()` and generated code handle this via `asyncio.TaskGroup`, trio nursery, or `concurrent.futures` cancel semantics.

**Rationale**:
- `asyncio.TaskGroup`: Cancels remaining tasks when one raises. Exception propagates as `ExceptionGroup` — resolver unwraps single-exception groups to preserve original error type.
- trio nursery: Same semantics — cancels sibling tasks on error.
- `ThreadPoolExecutor`/`ProcessPoolExecutor`: `as_completed()` + cancel remaining futures on first error.

On error, factories already completed (including yielded generators) remain in `_exits` — cleaned up on scope exit (correct behavior).

For parent cancellation: `TaskGroup` and trio nurseries handle natively. Thread/process pools: `Future.cancel()` prevents pending submissions but can't interrupt running work — known `concurrent.futures` limitation.

## R-008: Executor Tag Storage and Propagation

**Decision**: Add an optional `executor: str | None` field to `Factory` (in `dependency_source/factory.py`). Surface it to the strategy alongside `DependencyKey` and the factory callable.

**Rationale**: `DependencyKey` is a `NamedTuple` used as dict keys throughout the codebase — adding fields would break hashing/equality semantics. Storing the tag on `Factory` follows the pattern of other factory metadata (`scope`, `cache`, `when_override`).

**Propagation path**: `@provide(executor="tag")` → `Factory.executor` → graph builder includes in layer data → strategy receives `(DependencyKey, Callable, str | None)` tuples or a separate metadata mapping.

**Signature impact**: The `run()` and `compile()` signatures in the spec use `Sequence[tuple[DependencyKey, Callable]]`. Adding the executor tag as a third tuple element is a minor signature change. Alternatively, pass a `dict[DependencyKey, str | None]` mapping alongside the callables list. Final signature determined during implementation.

## R-009: compile() Hook Detection and Fallback

**Decision**: Use `hasattr(strategy, 'compile')` at container creation time. No separate mixin or protocol.

**Rationale**: Simplest approach, matches Python duck-typing conventions. Check happens once at build time, not per `get()`. The compiler either uses `strategy.compile()` to emit concurrent code or emits runtime calls to `strategy.run()`.

**Flow**:
1. `make_container(concurrency=strategy)` → graph builder receives strategy
2. Registry compilation: if `hasattr(strategy, 'compile')` → compiler calls `strategy.compile(builder, callables)` for each concurrent layer
3. Else → compiler emits `await strategy.run(callables)` / `strategy.run(callables)` for each layer
4. Single-factory layers always skip the strategy (direct call, no overhead)
