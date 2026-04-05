"""Codegen-specific tests (fallback, diamond dedup counting)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NewType

import pytest

from dishka import (
    Provider,
    Scope,
    make_async_container,
    provide,
)
from dishka.concurrency._asyncio import AsyncioStrategy
from dishka.entities.key import DependencyKey

A = NewType("A", int)
B = NewType("B", int)
C = NewType("C", int)


class TestFallbackWithoutCompile:
    """Strategy without compile() uses run() — no error."""

    @pytest.mark.asyncio()
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
                results: list[object] = [None] * len(
                    factories,
                )
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


class TestCodegenDiamondDedup:
    """Compiled code runs each factory exactly once."""

    @pytest.mark.asyncio()
    async def test_diamond_single_execution(self) -> None:
        call_counts: dict[str, int] = {}

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                call_counts["a"] = (
                    call_counts.get("a", 0) + 1
                )
                return A(1)

            @provide
            async def b(self, a: A) -> B:
                call_counts["b"] = (
                    call_counts.get("b", 0) + 1
                )
                return B(2)

            @provide
            async def c(self, a: A) -> C:
                call_counts["c"] = (
                    call_counts.get("c", 0) + 1
                )
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
        assert call_counts == {"a": 1, "b": 1, "c": 1}
