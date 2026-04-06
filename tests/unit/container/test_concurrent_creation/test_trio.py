"""Trio-specific tests (barrier proof of concurrency)."""
from __future__ import annotations

from typing import Any

import trio

from dishka import (
    Provider,
    Scope,
    make_async_container,
    provide,
)
from dishka.concurrency._trio import TrioStrategy
from .conftest import A, B


class TestTrioConcurrentExecution:
    """Trio concurrent execution with independent factories."""

    def test_independent_factories_overlap(self) -> None:
        barrier_count = 0

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                nonlocal barrier_count
                barrier_count += 1
                await trio.lowlevel.checkpoint()
                return A(1)

            @provide
            async def b(self) -> B:
                nonlocal barrier_count
                barrier_count += 1
                await trio.lowlevel.checkpoint()
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        async def _run() -> list[Any]:
            strategy = TrioStrategy()
            container = make_async_container(
                MyProvider(),
                concurrency=strategy,
            )
            async with container:
                return await container.get(list[Any])

        result = trio.run(_run)
        assert result == [1, 2]
        assert barrier_count == 2
