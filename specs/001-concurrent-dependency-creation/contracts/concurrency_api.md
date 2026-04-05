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
```

### Built-in Implementations

```python
# Async strategies
class AsyncioStrategy:
    """Concurrent dispatch via asyncio.TaskGroup (Python 3.11+)."""
    pass

class AsyncioSemaphoreStrategy:
    """Bounded concurrent dispatch via asyncio.TaskGroup + Semaphore."""
    def __init__(self, max_concurrent: int) -> None: ...

class TrioStrategy:
    """Concurrent dispatch via trio nursery. Requires trio."""
    pass

# Sync strategies
class ThreadPoolStrategy:
    """Concurrent dispatch via ThreadPoolExecutor."""
    def __init__(
        self,
        executor: concurrent.futures.ThreadPoolExecutor | None = None,
    ) -> None: ...

class ProcessPoolStrategy:
    """Concurrent dispatch via ProcessPoolExecutor.
    Generator factories run in the calling process.
    """
    def __init__(
        self,
        executor: concurrent.futures.ProcessPoolExecutor | None = None,
    ) -> None: ...
```

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

### Concurrent Resolution Guarantees

1. **Ordering**: Factories dispatched in topological order (leaves first). Within a layer, dispatch is concurrent.
2. **Deduplication**: Each `DependencyKey` resolved at most once per scope — guaranteed by topological ordering, not runtime locks.
3. **Error propagation**: First factory error cancels remaining work in the current layer; `container.get()` raises the original exception.
4. **No leaked work**: After `get()` returns (success or error), no background tasks/threads/coroutines remain.
5. **Cleanup**: Generator factories yielded during concurrent resolution are registered in `_exits` and finalized on scope exit (LIFO order).
6. **Cache consistency**: Results written to cache immediately after factory completion; subsequent layers read from cache.
7. **Lock scope**: The per-scope lock is held for the entire `get()` call (same as non-concurrent path).

### Strategy-Specific Behavior

| Strategy | Runtime | Generators | Cancellation |
|---|---|---|---|
| `AsyncioStrategy` | asyncio (3.11+) | Concurrent (in-process) | `TaskGroup` cancellation |
| `AsyncioSemaphoreStrategy` | asyncio (3.11+) | Concurrent (bounded) | `TaskGroup` cancellation |
| `TrioStrategy` | trio | Concurrent (in-process) | Nursery cancellation |
| `ThreadPoolStrategy` | threads | Concurrent (in-process) | `Future.cancel()` for pending |
| `ProcessPoolStrategy` | processes | Sequential (in-process) | `Future.cancel()` for pending |

### Future Extension: Code Generation (Priority 5)

The `ConcurrencyStrategy` protocols are designed to be forward-compatible with an optional `compile()` codegen hook. This is **not part of the initial implementation** but is documented here to constrain the design:

```python
# Future addition — no breaking changes to existing protocol
class AsyncConcurrencyStrategy(Protocol):
    async def run(self, factories: ...) -> ...: ...

    # Optional — checked via hasattr() or separate mixin
    def compile(
        self,
        builder: FactoryBuilder,
        callables: Sequence[tuple[DependencyKey, str]],  # str = compiled getter name
    ) -> None:
        """Emit concurrent dispatch code into the CodeBuilder.

        Strategies without this method fall back to runtime run() dispatch.
        Built-in and custom strategies may both provide compile().
        """
        ...
```

Codegen is feasible for all built-in strategies:
- **asyncio**: emit `async with asyncio.TaskGroup()` + `create_task()` calls
- **trio**: emit `async with trio.open_nursery()` + wrapper coroutines + result dict
- **thread pool**: emit `executor.submit()` + result collection

The existing `CodeBuilder` supports all necessary constructs (function defs, `async with`, dicts).

### Re-exports from `dishka`

The following new names are exported from `dishka.__init__`:

- `AsyncConcurrencyStrategy`
- `SyncConcurrencyStrategy`
- `AsyncioStrategy`
- `AsyncioSemaphoreStrategy`
- `TrioStrategy`
- `ThreadPoolStrategy`
- `ProcessPoolStrategy`
