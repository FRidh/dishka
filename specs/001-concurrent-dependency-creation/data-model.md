# Data Model: Concurrent Dependency Creation

**Feature**: 001-concurrent-dependency-creation
**Date**: 2026-04-05

## New Entities

### AsyncConcurrencyStrategy (Protocol)

A runtime protocol for async concurrent factory dispatch.

| Field/Method | Type | Description |
|---|---|---|
| `run(factories)` | `async (Sequence[tuple[DependencyKey, Callable[[], Awaitable[T]]]]) -> Sequence[T]` | Dispatch multiple async factory callables concurrently, return results in same order |
| `compile(builder, callables)` | `(CodeBuilder, Sequence[tuple[DependencyKey, Callable]]) -> None` | **Optional** codegen hook; emit optimized concurrent code into `CodeBuilder`. Strategies without this method fall back to runtime `run()` dispatch (checked via `hasattr`). All built-in strategies implement this. |

**Implementations**:
- `AsyncioStrategy` — uses `asyncio.TaskGroup` (Python 3.11+), unlimited concurrency. Ships with `run()` and `compile()`.
- `AsyncioSemaphoreStrategy(max_concurrent: int)` — wraps each task with `asyncio.Semaphore`. Ships with `run()` and `compile()`.
- `TrioStrategy` — uses `trio.open_nursery()`, requires trio installed. Ships with `run()` and `compile()`.

**Validation rules**: `AsyncioStrategy` raises `RuntimeError` at construction if Python < 3.11.

### SyncConcurrencyStrategy (Protocol)

A runtime protocol for sync concurrent factory dispatch.

| Field/Method | Type | Description |
|---|---|---|
| `run(factories)` | `(Sequence[tuple[DependencyKey, Callable[[], T]]]) -> Sequence[T]` | Dispatch multiple sync factory callables concurrently, return results in same order |
| `compile(builder, callables)` | `(CodeBuilder, Sequence[tuple[DependencyKey, Callable]]) -> None` | **Optional** codegen hook; emit optimized concurrent code into `CodeBuilder`. Strategies without this method fall back to runtime `run()` dispatch (checked via `hasattr`). All built-in strategies implement this. |

**Implementations**:
- `ThreadPoolStrategy(executor: ThreadPoolExecutor | None = None)` — uses `concurrent.futures.ThreadPoolExecutor`. Ships with `run()` and `compile()`.
- `ProcessPoolStrategy(executor: ProcessPoolExecutor | None = None)` — uses `concurrent.futures.ProcessPoolExecutor`. Ships with `run()` and `compile()`.

**Validation rules**: If no executor provided, a default one is created. Process pool strategy partitions generators to run locally.

### ExecutorTag

Public enum/string type for per-factory executor routing.

| Usage | Description |
|---|---|
| `@provide(executor="tag")` | String tag on factory, stored as `Factory.executor` |
| `@provide(executor=ExecutorTag.X)` | Enum-based tag (convenience, same effect) |

Built-in strategies use the tag to route factories to different executors. Strategies that don't support per-factory dispatch ignore the tag.

### TopologicalLayer

Internal (not public). Represents one layer of the resolution DAG.

| Field | Type | Description |
|---|---|---|
| `factories` | `list[tuple[DependencyKey, Factory]]` | Factories in this layer (all independent) |

### ConcurrentResolver

Internal. Orchestrates layer-by-layer resolution for a single `get()` call.

| Field | Type | Description |
|---|---|---|
| `registry` | `Registry` | The scope's registry for factory lookup |
| `strategy` | `AsyncConcurrencyStrategy | SyncConcurrencyStrategy` | The dispatch strategy |
| `cache` | `dict[Any, object]` | The scope's dependency cache |
| `exits` | `list[Exit]` | The scope's cleanup list |
| `parent_getter` | `Callable` | Getter for cross-scope dependencies |
| `context` | `dict` | Context vars |

**Methods**:
- `resolve(root_key) -> object` / `async resolve(root_key) -> object` — compute layers, dispatch, return root value
- `_compute_layers(root_key) -> list[TopologicalLayer]` — BFS + Kahn's algorithm
- `_invoke_factory(factory, cache) -> object` — call a single factory with args from cache, handle generator protocol

## Modified Entities

### Factory (dependency_source/factory.py)

| Change | Description |
|---|---|
| New field: `executor` | `str | None = None` — optional executor tag from `@provide(executor=...)`. Used by strategies for per-factory dispatch. |

### @provide (provider/make_factory.py)

| Change | Description |
|---|---|
| New kwarg: `executor` | `str | None = None` — static tag stored on the Factory, used by strategies for per-factory routing |

### Container (container.py)

| Change | Description |
|---|---|
| New slot: `_concurrency` | `SyncConcurrencyStrategy | None` — stored from `make_container(concurrency=...)` |
| Modified: `_get_unlocked()` | If `_concurrency` is set, delegates to `ConcurrentResolver` instead of calling compiled factory |
| Propagation | Child containers created via `__call__()` inherit `_concurrency` from parent |

### AsyncContainer (async_container.py)

| Change | Description |
|---|---|
| New slot: `_concurrency` | `AsyncConcurrencyStrategy | None` — stored from `make_async_container(concurrency=...)` |
| Modified: `_get_unlocked()` | If `_concurrency` is set, delegates to `ConcurrentResolver` instead of calling compiled factory |
| Propagation | Child containers created via `__call__()` inherit `_concurrency` from parent |

### make_container() / make_async_container()

| Change | Description |
|---|---|
| New kwarg: `concurrency` | `SyncConcurrencyStrategy | None = None` / `AsyncConcurrencyStrategy | None = None` |
| Validation | Type-check that sync container gets sync strategy and async gets async strategy |

### Registry (registry.py)

| Change | Description |
|---|---|
| Modified compilation | If strategy has `compile()`, compiler uses it to emit concurrent layer code. Otherwise emits runtime `strategy.run()` calls. |

### CodeBuilder (code_tools/code_builder.py)

| Change | Description |
|---|---|
| New helpers | Optional helper methods for emitting `TaskGroup`, nursery, and executor patterns (may use raw `statement()` instead) |

### FactoryCompiler (code_tools/factory_compiler.py)

| Change | Description |
|---|---|
| Modified compilation | Aware of topological layers and concurrency strategy. Emits concurrent code via `strategy.compile()` or runtime `strategy.run()` calls for each layer. |

## Entity Relationships

```
make_container(concurrency=strategy)
  └── Container
        ├── _concurrency: SyncConcurrencyStrategy?
        ├── _cache: dict
        ├── _exits: list[Exit]
        └── get(key)
              ├── [no concurrency] → compiled factory path (unchanged)
              └── [concurrency]
                    ├── [strategy has compile()] → compiled concurrent code
                    │     └── pre-compiled at container creation time
                    │           └── strategy.compile(builder, callables)
                    └── [strategy has run() only] → ConcurrentResolver
                          ├── _compute_layers(key) → list[TopologicalLayer]
                          │     └── Registry.get_factory(dep) → Factory
                          │           ├── .dependencies → list[DependencyKey]
                          │           ├── .kw_dependencies → dict[str, DependencyKey]
                          │           └── .executor → str | None
                          └── for each layer:
                                └── strategy.run([(key, callable), ...])
                                      └── _invoke_factory(factory, cache)
                                            ├── reads deps from cache
                                            ├── calls factory.source(*args)
                                            ├── handles generator yield
                                            └── writes result to cache
```

## State Transitions

```
Container.get(key) with concurrency enabled:

1. LOCK_ACQUIRED
   ├── Check cache → if hit, return cached value
   └── Continue to resolution

2a. [compile() path — pre-compiled at creation time]
    └── Execute compiled concurrent code (TaskGroup, nursery, etc.)

2b. [run() path — computed at get() time]
    ├── COMPUTING_LAYERS
    │   ├── BFS from root key through Registry
    │   ├── Exclude cached keys and cross-scope keys
    │   └── Kahn's algorithm → ordered layers
    └── DISPATCHING_LAYERS (for each layer)
        ├── Build factory callables (closure over cache reads)
        ├── strategy.run([(key, callable), ...])
        │   └── Per-factory dispatch: strategy reads Factory.executor tag
        ├── Write results to cache
        └── Register generators in _exits

3. COMPLETE
   ├── Root value is in cache
   ├── Release lock
   └── Return root value

Error at any step → cancel remaining work, propagate error, lock released
```
