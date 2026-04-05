"""Tests for async concurrent resolution with AsyncioStrategy."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from dishka import (
    AsyncContainer,
    AsyncioStrategy,
    Provider,
    Scope,
    make_async_container,
    provide,
)


@pytest.fixture()
def strategy() -> AsyncioStrategy:
    return AsyncioStrategy()


class TestConcurrentExecution:
    """T011: Two independent async factories execute concurrently."""

    @pytest.mark.asyncio()
    async def test_independent_factories_overlap(
        self, strategy: AsyncioStrategy,
    ) -> None:
        barrier = asyncio.Barrier(2)

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> int:
                await barrier.wait()
                return 1

            @provide
            async def b(self) -> str:
                await barrier.wait()
                return "hello"

            @provide
            async def root(self, a: int, b: str) -> list[Any]:
                return [a, b]

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container() as scope:
            result = await asyncio.wait_for(
                scope.get(list[Any]),
                timeout=5.0,
            )
        assert result == [1, "hello"]


class TestSequentialWithoutConcurrency:
    """T013: No concurrency config => identical sequential behavior."""

    @pytest.mark.asyncio()
    async def test_sequential_no_concurrency(self) -> None:
        call_order: list[str] = []

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> int:
                call_order.append("a")
                return 1

            @provide
            async def b(self) -> str:
                call_order.append("b")
                return "hello"

            @provide
            async def root(self, a: int, b: str) -> list[Any]:
                call_order.append("root")
                return [a, b]

        container = make_async_container(MyProvider())
        async with container() as scope:
            result = await scope.get(list[Any])
        assert result == [1, "hello"]
        assert "root" in call_order


class TestErrorPropagation:
    """T014: Factory error propagates, no background tasks remain."""

    @pytest.mark.asyncio()
    async def test_factory_error_propagates(
        self, strategy: AsyncioStrategy,
    ) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> int:
                raise ValueError("boom")

            @provide
            async def b(self) -> str:
                await asyncio.sleep(10)
                return "hello"

            @provide
            async def root(self, a: int, b: str) -> list[Any]:
                return [a, b]

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container() as scope:
            with pytest.raises(ValueError, match="boom"):
                await scope.get(list[Any])


class TestCancellationSafety:
    """T015: Parent task cancellation cancels in-progress factories."""

    @pytest.mark.asyncio()
    async def test_cancellation_propagates(
        self, strategy: AsyncioStrategy,
    ) -> None:
        started = asyncio.Event()

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> int:
                started.set()
                await asyncio.sleep(100)
                return 1

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container() as scope:
            task = asyncio.create_task(scope.get(int))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


class TestAsyncGeneratorFactories:
    """T016: Generator factories yield, register cleanup, finalize."""

    @pytest.mark.asyncio()
    async def test_generator_cleanup(
        self, strategy: AsyncioStrategy,
    ) -> None:
        cleanup_called = False

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> AsyncIterator[int]:
                nonlocal cleanup_called
                yield 42
                cleanup_called = True

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(int)
            assert result == 42
            assert not cleanup_called
        assert cleanup_called
