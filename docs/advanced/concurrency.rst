.. _concurrency:

Concurrent dependency creation
****************************************

When to use
===========================

If your dependency factories perform I/O (connecting to databases,
fetching remote configs, initializing HTTP clients), they may spend
most of their time waiting. By default the container creates
dependencies one at a time. With a **concurrency strategy** it can
run independent factories in parallel, reducing total startup time.

Concurrency is **opt-in**. Without the ``concurrency`` argument,
container behaviour is identical to before — fully sequential.

.. note::
    Concurrent creation requires **Python 3.11+** (for
    ``asyncio.TaskGroup`` and ``ExceptionGroup``). On older versions
    the container raises at construction time.


Enabling concurrency
===========================

Pass a strategy to ``make_container`` or ``make_async_container``:

.. code-block:: python

    from dishka import make_async_container, AsyncioStrategy

    container = make_async_container(
        provider,
        concurrency=AsyncioStrategy(),
    )

For a synchronous container:

.. code-block:: python

    from dishka import make_container, ThreadPoolStrategy

    container = make_container(
        provider,
        concurrency=ThreadPoolStrategy(),
    )

Child scope containers inherit the strategy automatically — you
do not need to pass it again when entering a nested scope.


Choosing a strategy
===========================

+------------------------------------+-------------------------------+
| Use case                           | Strategy                      |
+====================================+===============================+
| Async app (asyncio)                | ``AsyncioStrategy()``         |
+------------------------------------+-------------------------------+
| Async app, bounded parallelism     | ``AsyncioSemaphoreStrategy(`` |
|                                    | ``max_concurrent=N)``         |
+------------------------------------+-------------------------------+
| Async app (trio)                   | ``TrioStrategy()``            |
+------------------------------------+-------------------------------+
| Sync app, I/O-bound factories      | ``ThreadPoolStrategy()``      |
+------------------------------------+-------------------------------+
| Sync app, CPU-bound picklable work | ``ProcessPoolStrategy()``     |
+------------------------------------+-------------------------------+


Built-in strategies
===========================

AsyncioStrategy
---------------------------

Unlimited concurrency via ``asyncio.TaskGroup``. Each factory in a
layer becomes its own task.

.. code-block:: python

    from dishka import make_async_container, AsyncioStrategy

    container = make_async_container(
        provider,
        concurrency=AsyncioStrategy(),
    )


AsyncioSemaphoreStrategy
---------------------------

Same as ``AsyncioStrategy`` but limits how many factories run at
the same time using an ``asyncio.Semaphore``.

.. code-block:: python

    from dishka import (
        make_async_container,
        AsyncioSemaphoreStrategy,
    )

    container = make_async_container(
        provider,
        concurrency=AsyncioSemaphoreStrategy(max_concurrent=5),
    )


TrioStrategy
---------------------------

For applications using `trio <https://trio.readthedocs.io>`_.
Uses ``trio.open_nursery()`` to run factories concurrently.

.. code-block:: python

    from dishka import make_async_container, TrioStrategy

    container = make_async_container(
        provider,
        concurrency=TrioStrategy(),
    )


ThreadPoolStrategy
---------------------------

Submits factories to a ``concurrent.futures.ThreadPoolExecutor``.
You can supply your own executor or let the strategy create one
per resolution call.

.. code-block:: python

    from dishka import make_container, ThreadPoolStrategy

    container = make_container(
        provider,
        concurrency=ThreadPoolStrategy(),
    )

    # With a shared executor:
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=4)
    container = make_container(
        provider,
        concurrency=ThreadPoolStrategy(executor=executor),
    )


ProcessPoolStrategy
---------------------------

Uses a ``ProcessPoolExecutor``. Factories that are closures (and
therefore cannot be pickled) automatically fall back to a thread
pool. Generator factories always run in the calling process.

.. code-block:: python

    from dishka import make_container, ProcessPoolStrategy

    container = make_container(
        provider,
        concurrency=ProcessPoolStrategy(),
    )


Custom strategies
===========================

Implement the ``AsyncConcurrencyStrategy`` or
``SyncConcurrencyStrategy`` protocol. The ``run`` method receives
a sequence of ``(DependencyKey, factory_callable, executor_tag)``
tuples and must return results **in the same order**.

.. code-block:: python

    from collections.abc import Awaitable, Callable, Sequence
    from dishka import DependencyKey

    class LoggingStrategy:
        async def run(
            self,
            factories: Sequence[
                tuple[
                    DependencyKey,
                    Callable[[], Awaitable[object]],
                    str | None,
                ]
            ],
        ) -> Sequence[object]:
            import asyncio

            async def _call(key, fn):
                print(f"Creating {key}")
                return await fn()

            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(_call(k, fn))
                    for k, fn, _tag in factories
                ]
            return [t.result() for t in tasks]

Built-in strategies also provide an optional ``compile()`` method
that emits optimised code at container creation time. Custom
strategies can omit it — the container falls back to ``run()``.


Per-factory executor dispatching
====================================

Tag individual factories with ``executor=`` on ``@provide``:

.. code-block:: python

    from dishka import Provider, provide, Scope

    class MyProvider(Provider):
        scope = Scope.APP

        @provide(executor="io")
        async def get_db(self) -> Database:
            return await Database.connect(...)

        @provide(executor="cpu")
        async def compute_config(self) -> Config:
            return await heavy_computation()

        @provide
        async def get_app(
            self, db: Database, config: Config,
        ) -> App:
            return App(db, config)

The tag is passed to the strategy as the third element of each
tuple. Built-in strategies receive it but currently treat all tags
the same. Custom strategies can use the tag to route factories to
different executors.


How it works: topological layers
====================================

When you request a dependency the container builds a sub-graph of
same-scope factories needed to satisfy it. It then groups them
into **topological layers** using Kahn's algorithm:

::

    Layer 0:  [A]  [B]       ← no in-scope deps, run concurrently
    Layer 1:  [C(A, B)]      ← depends on layer 0, waits
    Layer 2:  [root(C)]      ← depends on layer 1, waits

Layers execute sequentially. Factories within one layer execute
concurrently via the strategy. Shared dependencies (diamonds) are
fully resolved before any consumer layer is dispatched, so no
factory is called more than once.


Interaction with scopes and locks
====================================

``concurrency`` and ``lock_factory`` solve different problems:

* ``lock_factory`` protects the dependency **cache** when multiple
  threads or tasks enter the *same* scope concurrently (e.g. many
  requests hitting the APP-scope container at once).
* ``concurrency`` parallelises factory **creation** within a
  single resolution call.

They are orthogonal and can be used together.
