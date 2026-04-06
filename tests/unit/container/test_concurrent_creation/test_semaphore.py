"""Semaphore-specific tests (throttling, no-throttling comparison)."""
from __future__ import annotations

import asyncio
from typing import Any, NewType

import pytest

from dishka import (
    AsyncioSemaphoreStrategy,
    AsyncioStrategy,
    Provider,
    Scope,
    make_async_container,
    provide,
)

A = NewType("A", int)
B = NewType("B", int)
C = NewType("C", int)
D = NewType("D", int)


class TestSemaphoreLimiting:
    """At most N factories run simultaneously."""

    @pytest.mark.asyncio()
    async def test_at_most_n_concurrent(self) -> None:
        max_concurrent = 2
        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def _tracked_factory(val: int) -> int:
            nonlocal peak, current
            async with lock:
                current += 1
                peak = max(peak, current)
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1
            return val

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                return A(await _tracked_factory(1))

            @provide
            async def b(self) -> B:
                return B(await _tracked_factory(2))

            @provide
            async def c(self) -> C:
                return C(await _tracked_factory(3))

            @provide
            async def d(self) -> D:
                return D(await _tracked_factory(4))

            @provide
            async def root(
                self, a: A, b: B, c: C, d: D,
            ) -> list[Any]:
                return [a, b, c, d]

        strategy = AsyncioSemaphoreStrategy(
            max_concurrent=max_concurrent,
        )
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])
        assert set(result) == {1, 2, 3, 4}
        assert peak <= max_concurrent


class TestNoThrottling:
    """AsyncioStrategy has no throttling (all concurrent)."""

    @pytest.mark.asyncio()
    async def test_all_concurrent_without_limit(self) -> None:
        barrier = asyncio.Barrier(4)

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                await barrier.wait()
                return A(1)

            @provide
            async def b(self) -> B:
                await barrier.wait()
                return B(2)

            @provide
            async def c(self) -> C:
                await barrier.wait()
                return C(3)

            @provide
            async def d(self) -> D:
                await barrier.wait()
                return D(4)

            @provide
            async def root(
                self, a: A, b: B, c: C, d: D,
            ) -> list[Any]:
                return [a, b, c, d]

        strategy = AsyncioStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await asyncio.wait_for(
                container.get(list[Any]),
                timeout=5.0,
            )
        assert set(result) == {1, 2, 3, 4}
