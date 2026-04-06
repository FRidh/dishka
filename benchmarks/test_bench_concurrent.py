"""Benchmarks: concurrent dependency resolution strategies."""
from __future__ import annotations

import asyncio

from dishka import (
    AsyncioSemaphoreStrategy,
    AsyncioStrategy,
    make_async_container,
    make_container,
)
from dishka.concurrency._sync import ThreadPoolStrategy
from benchmarks.conftest import (
    AsyncDiamondProvider,
    AsyncWideProvider,
    AsyncWideSlowProvider,
    DiamondProvider,
    Top,
    WideProvider,
    WideRoot,
)


# ── Asyncio strategy ───────────────────────────────────────────────


class TestAsyncioStrategy:

    def test_wide_trivial(self, benchmark):
        """Wide graph, trivial factories — measures overhead."""
        strategy = AsyncioStrategy()

        async def resolve():
            container = make_async_container(
                AsyncWideProvider(),
                concurrency=strategy,
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark(lambda: asyncio.run(resolve()))

    def test_diamond_trivial(self, benchmark):
        """Diamond graph, trivial factories."""
        strategy = AsyncioStrategy()

        async def resolve():
            container = make_async_container(
                AsyncDiamondProvider(),
                concurrency=strategy,
            )
            async with container() as scope:
                return await scope.get(Top)

        benchmark(lambda: asyncio.run(resolve()))

    def test_wide_simulated_io(self, benchmark):
        """Wide graph with 10ms I/O per leaf — shows concurrency benefit."""
        strategy = AsyncioStrategy()

        async def resolve():
            container = make_async_container(
                AsyncWideSlowProvider(),
                concurrency=strategy,
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark.pedantic(
            lambda: asyncio.run(resolve()),
            rounds=10,
            iterations=1,
        )


# ── Asyncio semaphore strategy ─────────────────────────────────────


class TestAsyncioSemaphoreStrategy:

    def test_wide_trivial(self, benchmark):
        """Wide graph with semaphore(4) — bounded task scheduling overhead."""
        strategy = AsyncioSemaphoreStrategy(max_concurrent=4)

        async def resolve():
            container = make_async_container(
                AsyncWideProvider(),
                concurrency=strategy,
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark(lambda: asyncio.run(resolve()))

    def test_wide_simulated_io(self, benchmark):
        """Semaphore-throttled with I/O — bounded concurrency."""
        strategy = AsyncioSemaphoreStrategy(max_concurrent=4)

        async def resolve():
            container = make_async_container(
                AsyncWideSlowProvider(),
                concurrency=strategy,
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark.pedantic(
            lambda: asyncio.run(resolve()),
            rounds=10,
            iterations=1,
        )


# ── Async sequential baseline for comparison ───────────────────────


class TestAsyncSequentialBaseline:
    """Sequential async resolution — compare with concurrent."""

    def test_wide_simulated_io_sequential(self, benchmark):
        """Same slow providers, no concurrency — should be ~10x slower."""
        async def resolve():
            container = make_async_container(
                AsyncWideSlowProvider(),
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark.pedantic(
            lambda: asyncio.run(resolve()),
            rounds=10,
            iterations=1,
        )


# ── ThreadPool strategy ────────────────────────────────────────────


class TestThreadPoolStrategy:

    def test_wide_trivial(self, benchmark):
        """Wide graph, trivial factories — measures thread overhead."""
        strategy = ThreadPoolStrategy()
        container = make_container(
            WideProvider(),
            concurrency=strategy,
        )

        def resolve():
            with container:
                return container.get(WideRoot)

        benchmark(resolve)

    def test_diamond_trivial(self, benchmark):
        """Diamond graph via thread pool — thread overhead on small graph."""
        strategy = ThreadPoolStrategy()
        container = make_container(
            DiamondProvider(),
            concurrency=strategy,
        )

        def resolve():
            with container:
                return container.get(Top)

        benchmark(resolve)
