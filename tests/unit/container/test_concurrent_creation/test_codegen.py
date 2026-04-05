"""Tests for code generation in concurrent resolution."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NewType

import pytest

from dishka import (
    Provider,
    Scope,
    make_async_container,
    make_container,
    provide,
)
from dishka.concurrency._asyncio import AsyncioStrategy
from dishka.concurrency._sync import ThreadPoolStrategy
from dishka.entities.key import DependencyKey

A = NewType("A", int)
B = NewType("B", int)
C = NewType("C", int)
D = NewType("D", int)


class TestAsyncioCodegenParity:
    """T041: Codegen/runtime parity for AsyncioStrategy."""

    @pytest.mark.asyncio
    async def test_runtime_and_codegen_same_results(
        self,
    ) -> None:
        call_order: list[str] = []

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                call_order.append("a")
                return A(1)

            @provide
            async def b(self) -> B:
                call_order.append("b")
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        # Run with runtime strategy
        strategy = AsyncioStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result_runtime = await container.get(list[Any])

        assert result_runtime == [1, 2]

    @pytest.mark.asyncio
    async def test_error_parity(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                raise ValueError("codegen boom")

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        strategy = AsyncioStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        with pytest.raises(ValueError, match="codegen boom"):
            async with container:
                await container.get(list[Any])


class TestFallbackWithoutCompile:
    """T042: Strategy without compile() uses run() — no error."""

    @pytest.mark.asyncio
    async def test_fallback_to_run(self) -> None:
        run_called = False

        class NoCompileStrategy:
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
                nonlocal run_called
                run_called = True
                results: list[object] = [None] * len(factories)
                for i, (_k, f, _ex) in enumerate(factories):
                    results[i] = await f()
                return results

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                return A(1)

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        strategy = NoCompileStrategy()
        assert not hasattr(strategy, "compile")
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]
        assert run_called


class TestThreadPoolCodegenParity:
    """T044: Codegen/runtime parity for ThreadPoolStrategy."""

    def test_runtime_results(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                return A(1)

            @provide
            def b(self) -> B:
                return B(2)

            @provide
            def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        strategy = ThreadPoolStrategy()
        container = make_container(
            MyProvider(),
            concurrency=strategy,
        )
        with container:
            result = container.get(list[Any])

        assert result == [1, 2]


class TestCodegenDiamondDedup:
    """T045: Compiled code runs each factory exactly once."""

    @pytest.mark.asyncio
    async def test_diamond_single_execution(self) -> None:
        call_counts: dict[str, int] = {}

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                call_counts["a"] = call_counts.get("a", 0) + 1
                return A(1)

            @provide
            async def b(self, a: A) -> B:
                call_counts["b"] = call_counts.get("b", 0) + 1
                return B(2)

            @provide
            async def c(self, a: A) -> C:
                call_counts["c"] = call_counts.get("c", 0) + 1
                return C(3)

            @provide
            async def root(
                self, b: B, c: C,
            ) -> list[Any]:
                return [b, c]

        strategy = AsyncioStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [2, 3]
        # Each factory called exactly once
        assert call_counts == {"a": 1, "b": 1, "c": 1}
