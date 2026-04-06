"""Baseline benchmarks: sequential dependency resolution."""
from __future__ import annotations

import asyncio

from dishka import make_async_container, make_container
from benchmarks.conftest import (
    AsyncDeepChainProvider,
    AsyncDiamondProvider,
    AsyncShallowProvider,
    AsyncWideProvider,
    ChainF,
    DeepChainProvider,
    DiamondProvider,
    Shallow,
    ShallowProvider,
    Top,
    WideProvider,
    WideRoot,
)


# ── Sync sequential ────────────────────────────────────────────────


class TestSyncSequential:

    def test_shallow(self, benchmark):
        """Single dep, no nesting — per-call overhead floor."""
        container = make_container(ShallowProvider())

        def resolve():
            with container:
                return container.get(Shallow)

        benchmark(resolve)

    def test_deep_chain(self, benchmark):
        """6-level linear chain — recursive resolution cost."""
        container = make_container(DeepChainProvider())

        def resolve():
            with container:
                return container.get(ChainF)

        benchmark(resolve)

    def test_wide(self, benchmark):
        """Root + 10 independent leaves — best-case for concurrency."""
        container = make_container(WideProvider())

        def resolve():
            with container:
                return container.get(WideRoot)

        benchmark(resolve)

    def test_diamond(self, benchmark):
        """Shared transitive deps — realistic pattern."""
        container = make_container(DiamondProvider())

        def resolve():
            with container:
                return container.get(Top)

        benchmark(resolve)


# ── Async sequential ───────────────────────────────────────────────


class TestAsyncSequential:

    def test_shallow(self, benchmark):
        """Single async dep — asyncio.run overhead baseline."""
        async def resolve():
            container = make_async_container(
                AsyncShallowProvider(),
            )
            async with container() as scope:
                return await scope.get(Shallow)

        benchmark(lambda: asyncio.run(resolve()))

    def test_deep_chain(self, benchmark):
        """6-level async chain — recursive async resolution cost."""
        async def resolve():
            container = make_async_container(
                AsyncDeepChainProvider(),
            )
            async with container() as scope:
                return await scope.get(ChainF)

        benchmark(lambda: asyncio.run(resolve()))

    def test_wide(self, benchmark):
        """10 async leaves — sequential baseline for concurrency comparison."""
        async def resolve():
            container = make_async_container(
                AsyncWideProvider(),
            )
            async with container() as scope:
                return await scope.get(WideRoot)

        benchmark(lambda: asyncio.run(resolve()))

    def test_diamond(self, benchmark):
        """Async diamond — shared transitive deps sequentially."""
        async def resolve():
            container = make_async_container(
                AsyncDiamondProvider(),
            )
            async with container() as scope:
                return await scope.get(Top)

        benchmark(lambda: asyncio.run(resolve()))
