# Public API Contract: Concurrency

**Feature**: 001-concurrent-dependency-creation
**Date**: 2026-04-05

## New Public Symbols

### Protocols

```python
from typing import Protocol, Sequence, Awaitable, Callable, TypeVar

T = TypeVar("T")

class AsyncConcurrencyStrategy(Protocol):
    """Protocol for async concurrent factory dispatch."""

    async def run(
        self,
        factories: Sequence[tuple[DependencyKey, Callable[[], Awaitable[object]]]],
    ) -> Sequence[object]:
        """Execute factories concurrently, return results in input order.

        Each tuple is (dependency_key, async_callable). The callable takes
        no arguments (dependencies are pre-bound) and returns the resolved
        value.

        Must raise the original exception if any factory fails.
        Must cancel remaining factories on first failure.
        Must not leave background tasks running after return.
        """
        ...

    # Optional — checked via hasattr() at container creation time
    def compile(
        self,
        builder: CodeBuilder,
        callables: Sequence[tuple[DependencyKey, Callable]],
    ) -> None:
        """Emit concurrent dispatch code into the CodeBuilder.

        Symmetric with run(): receives same (key, callable) pairs plus
        the CodeBuilder. Strategies without this method fall back to
        runtime run() dispatch.

        All built-in strategies implement compile().
        Custom strategies may omit it.
        """
        ...


class SyncConcurrencyStrategy(Protocol):
    """Protocol for sync concurrent factory dispatch."""

    def run(
        self,
        factories: Sequence[tuple[DependencyKey, Callable[[], object]]],
    ) -> Sequence[object]:
        """Execute factories concurrently, return results in input order.

        Same contract as AsyncConcurrencyStrategy but synchronous.
        """
        ...

    # Optional — checked via hasattr() at container creation time
    def compile(
        self,
        builder: CodeBuilder,
        callables: Sequence[tuple[DependencyKey, Callable]],
    ) -> None:
        """Emit concurrent dispatch code into the CodeBuilder.

        Same contract as AsyncConcurrencyStrategy.compile().
        """
        ...
```

### Built-in Implementations

```python
# Async strategies — all ship with run() and compile()
class AsyncioStrategy:
    """Concurrent dispatch via asyncio.TaskGroup (Python 3.11+)."""
    async def run(self, factories: ...) -> ...: ...
    def compile(self, builder: ..., callables: ...) -> None: ...

class AsyncioSemaphoreStrategy:
    """Bounded concurrent dispatch via asyncio.TaskGroup + Semaphore."""
    def __init__(self, max_concurrent: int) -> None: ...
    async def run(self, factories: ...) -> ...: ...
    def compile(self, builder: ..., callables: ...) -> None: ...

class TrioStrategy:
    """Concurrent dispatch via trio nursery. Requires trio."""
    async def run(self, factories: ...) -> ...: ...
    def compile(self, builder: ..., callables: ...) -> None: ...

# Sync strategies — all ship with run() and compile()
class ThreadPoolStrategy:
    """Concurrent dispatch via ThreadPoolExecutor."""
    def __init__(
        self,
        executor: concurrent.futures.ThreadPoolExecutor | None = None,
    ) -> None: ...
    def run(self, factories: ...) -> ...: ...
    def compile(self, builder: ..., callables: ...) -> None: ...

class ProcessPoolStrategy:
    """Concurrent dispatch via ProcessPoolExecutor.
    Generator factories run in the calling process.
    """
    def __init__(
        self,
        executor: concurrent.futures.ProcessPoolExecutor | None = None,
    ) -> None: ...
    def run(self, factories: ...) -> ...: ...
    def compile(self, builder: ..., callables: ...) -> None: ...
```

### Per-Factory Executor Dispatching

```python
# On @provide decorator — new optional kwarg
@provide(executor="db_pool")
async def get_db(self) -> Database: ...

@provide(executor="cpu_pool")
def compute_heavy(self) -> Result: ...

# No executor tag — uses strategy default
@provide
async def get_cache(self) -> Cache: ...
```

The `executor` tag is a static string stored on the `Factory` metadata. Strategies receive it alongside the `DependencyKey` and factory callable. Built-in strategies route factories based on tags; strategies that don't support per-factory dispatch ignore the tag (no error).

### Modified Function Signatures

```python
# container.py
def make_container(
    *providers: BaseProvider,
    scopes: type[BaseScope] = Scope,
    context: dict[Any, Any] | None = None,
    lock_factory: Callable[[], AbstractContextManager[Any]] | None = Lock,
    skip_validation: bool = False,
    start_scope: BaseScope | None = None,
    validation_settings: ValidationSettings = DEFAULT_VALIDATION,
    concurrency: SyncConcurrencyStrategy | None = None,  # NEW
) -> Container: ...

# async_container.py
def make_async_container(
    *providers: BaseProvider,
    scopes: type[BaseScope] = Scope,
    context: dict[Any, Any] | None = None,
    lock_factory: Callable[[], AbstractAsyncContextManager[Any]] | None = Lock,
    skip_validation: bool = False,
    start_scope: BaseScope | None = None,
    validation_settings: ValidationSettings = DEFAULT_VALIDATION,
    concurrency: AsyncConcurrencyStrategy | None = None,  # NEW
) -> AsyncContainer: ...
```

## Behavioral Contract

### Backward Compatibility

- Omitting `concurrency=` produces identical behavior to current release — zero overhead.
- All existing tests pass without modification.
- No existing public symbols are renamed, removed, or have signature changes.
- `@provide(executor=...)` on factories without concurrency enabled has no effect (tag is stored but ignored).

### Concurrent Resolution Guarantees

1. **Ordering**: Factories dispatched in topological order (leaves first). Within a layer, dispatch is concurrent.
2. **Deduplication**: Each `DependencyKey` resolved at most once per scope — guaranteed by topological ordering, not runtime locks.
3. **Error propagation**: First factory error cancels remaining work in the current layer; `container.get()` raises the original exception.
4. **No leaked work**: After `get()` returns (success or error), no background tasks/threads/coroutines remain.
5. **Cleanup**: Generator factories yielded during concurrent resolution are registered in `_exits` and finalized on scope exit (LIFO order).
6. **Cache consistency**: Results written to cache immediately after factory completion; subsequent layers read from cache.
7. **Lock scope**: The per-scope lock is held for the entire `get()` call (same as non-concurrent path).

### Strategy-Specific Behavior

| Strategy | Runtime | Generators | Cancellation | compile() |
|---|---|---|---|---|
| `AsyncioStrategy` | asyncio (3.11+) | Concurrent (in-process) | `TaskGroup` cancellation | Emits `async with TaskGroup()` + `create_task()` |
| `AsyncioSemaphoreStrategy` | asyncio (3.11+) | Concurrent (bounded) | `TaskGroup` cancellation | Emits `TaskGroup` + `Semaphore` acquire/release |
| `TrioStrategy` | trio | Concurrent (in-process) | Nursery cancellation | Emits `async with trio.open_nursery()` + wrapper coroutines |
| `ThreadPoolStrategy` | threads | Concurrent (in-process) | `Future.cancel()` for pending | Emits `executor.submit()` + result collection |
| `ProcessPoolStrategy` | processes | Sequential (in-process) | `Future.cancel()` for pending | Emits `executor.submit()` (plain) + sequential (generators) |

### Per-Factory Dispatch Behavior

| Scenario | Behavior |
|---|---|
| Factory has `executor="tag"`, strategy supports dispatch | Factory routed to executor matching tag |
| Factory has no executor tag | Uses strategy's default dispatch |
| Strategy doesn't support per-factory dispatch | Tags ignored, all factories use default |
| Both tag and strategy-level `DependencyKey` routing apply | Strategy decides precedence (built-in: explicit tag wins) |

### Code Generation Behavior

| Scenario | Behavior |
|---|---|
| Strategy has `compile()` method | Container uses compiled concurrent code at resolution time |
| Strategy has only `run()` method | Container falls back to runtime `strategy.run()` dispatch |
| Single-factory layer | Direct call, no strategy involvement (no overhead) |
| Detection | `hasattr(strategy, 'compile')` checked once at container creation |

### Re-exports from `dishka`

The following new names are exported from `dishka.__init__`:

- `AsyncConcurrencyStrategy`
- `SyncConcurrencyStrategy`
- `AsyncioStrategy`
- `AsyncioSemaphoreStrategy`
- `TrioStrategy`
- `ThreadPoolStrategy`
- `ProcessPoolStrategy`
