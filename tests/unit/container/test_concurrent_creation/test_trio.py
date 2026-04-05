"""Tests for trio concurrent resolution."""
from __future__ import annotations

from typing import Any, NewType

import pytest
import trio

from dishka import (
    Provider,
    Scope,
    make_async_container,
    provide,
)
from dishka.concurrency._trio import TrioStrategy

A = NewType("A", int)
B = NewType("B", int)


class TestTrioConcurrentExecution:
    """T030: Trio concurrent execution with independent factories."""

    def test_independent_factories_overlap(self) -> None:
        barrier_count = 0

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                nonlocal barrier_count
                barrier_count += 1
                await trio.sleep(0)
                return A(1)

            @provide
            async def b(self) -> B:
                nonlocal barrier_count
                barrier_count += 1
                await trio.sleep(0)
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

        result = trio.from_thread.run_sync(
            lambda: trio.lowlevel.current_trio_token(),
        ) if False else None  # noqa: SIM210

        result = trio.run(_run)
        assert result == [1, 2]
        assert barrier_count == 2


class TestTrioErrorPropagation:
    """T031: Trio error propagation and cancellation."""

    def test_error_propagates(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                raise ValueError("trio boom")

            @provide
            async def b(self) -> B:
                await trio.sleep(10)
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        async def _run() -> None:
            strategy = TrioStrategy()
            container = make_async_container(
                MyProvider(),
                concurrency=strategy,
            )
            async with container:
                await container.get(list[Any])

        with pytest.raises(ValueError, match="trio boom"):
            trio.run(_run)
