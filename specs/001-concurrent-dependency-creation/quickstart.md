# Quickstart: Concurrent Dependency Creation

## Async Container with asyncio

```python
import asyncio
from dishka import make_async_container, Provider, provide, Scope
from dishka import AsyncioStrategy

class MyProvider(Provider):
    scope = Scope.APP

    @provide
    async def get_db(self) -> Database:
        return await Database.connect("postgres://...")

    @provide
    async def get_cache(self) -> Cache:
        return await Cache.connect("redis://...")

    @provide
    async def get_app(self, db: Database, cache: Cache) -> App:
        return App(db=db, cache=cache)

async def main():
    container = make_async_container(
        MyProvider(),
        concurrency=AsyncioStrategy(),
    )
    async with container() as app_scope:
        # db and cache are created concurrently (independent deps)
        # app is created after both complete (depends on both)
        app = await app_scope.get(App)

asyncio.run(main())
```

## Async with Semaphore Limiting

```python
from dishka import AsyncioSemaphoreStrategy

container = make_async_container(
    MyProvider(),
    concurrency=AsyncioSemaphoreStrategy(max_concurrent=5),
)
```

## Sync Container with Thread Pool

```python
from concurrent.futures import ThreadPoolExecutor
from dishka import make_container, Provider, provide, Scope
from dishka import ThreadPoolStrategy

class MyProvider(Provider):
    scope = Scope.APP

    @provide
    def get_db(self) -> Database:
        return Database.connect("postgres://...")  # blocking I/O

    @provide
    def get_cache(self) -> Cache:
        return Cache.connect("redis://...")  # blocking I/O

    @provide
    def get_app(self, db: Database, cache: Cache) -> App:
        return App(db=db, cache=cache)

with make_container(
    MyProvider(),
    concurrency=ThreadPoolStrategy(),
) as container:
    with container() as app_scope:
        app = app_scope.get(App)  # db and cache created in parallel threads
```

## Trio Support

```python
import trio
from dishka import make_async_container, TrioStrategy

async def main():
    container = make_async_container(
        MyProvider(),
        concurrency=TrioStrategy(),
    )
    async with container() as app_scope:
        app = await app_scope.get(App)

trio.run(main)
```

## Per-Factory Executor Dispatching

```python
from dishka import make_async_container, Provider, provide, Scope
from dishka import AsyncioStrategy

class MixedProvider(Provider):
    scope = Scope.APP

    # Tag factories with executor hints
    @provide(executor="io")
    async def get_db(self) -> Database:
        return await Database.connect("postgres://...")

    @provide(executor="io")
    async def get_cache(self) -> Cache:
        return await Cache.connect("redis://...")

    @provide(executor="cpu")
    async def compute_config(self) -> Config:
        return await heavy_computation()

    # No tag — uses strategy default
    @provide
    async def get_app(
        self, db: Database, cache: Cache, config: Config,
    ) -> App:
        return App(db=db, cache=cache, config=config)

# Built-in strategies route based on executor tags
container = make_async_container(
    MixedProvider(),
    concurrency=AsyncioStrategy(),
)
```

## Custom Strategy

```python
from dishka import AsyncConcurrencyStrategy, DependencyKey
from typing import Sequence, Callable, Awaitable

class MyStrategy:
    """Custom strategy that logs factory execution."""

    async def run(
        self,
        factories: Sequence[tuple[DependencyKey, Callable[[], Awaitable[object]]]],
    ) -> Sequence[object]:
        import asyncio
        results: list[object] = []
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for key, factory in factories:
                print(f"Dispatching {key}")
                tasks.append(tg.create_task(factory()))
        return [t.result() for t in tasks]

    # compile() is optional for custom strategies
    # Without it, the container uses run() at resolution time

container = make_async_container(
    MyProvider(),
    concurrency=MyStrategy(),
)
```

## Key Points

- **Opt-in**: Pass `concurrency=` to `make_container()` or `make_async_container()`. Without it, behavior is unchanged.
- **Automatic parallelism**: The container analyzes the dependency graph and identifies which factories can run concurrently. No changes to providers needed.
- **Propagation**: Child scope containers inherit the concurrency strategy automatically.
- **Generators work**: Generator factories (resource cleanup) work with all strategies. With `ProcessPoolStrategy`, generators run in the calling process.
- **Per-factory dispatch**: Tag factories with `@provide(executor="tag")` to route them to specific executors. Strategies that don't support dispatch ignore the tag.
- **Code generation**: Built-in strategies include `compile()` for optimized code emission at container creation time. Custom strategies can omit `compile()` — the container falls back to `run()`.
