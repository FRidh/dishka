"""Tests for per-factory executor dispatching."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NewType

import pytest

from dishka import (
    AsyncioStrategy,
    Provider,
    Scope,
    make_async_container,
    provide,
)
from dishka.entities.key import DependencyKey

A = NewType("A", int)
B = NewType("B", int)
C = NewType("C", int)


class TrackingStrategy:
    """Strategy that records which executor tag each factory had."""

    def __init__(self) -> None:
        self.dispatched: list[tuple[DependencyKey, str | None]] = []

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
        results: list[object] = [None] * len(factories)
        for i, (key, factory, executor) in enumerate(factories):
            self.dispatched.append((key, executor))
            results[i] = await factory()
        return results


class TestTagBasedDispatch:
    """T033: Factories with different executor tags routed correctly."""

    @pytest.mark.asyncio
    async def test_different_tags_dispatched(self) -> None:
        strategy = TrackingStrategy()

        class MyProvider(Provider):
            scope = Scope.APP

            @provide(executor="fast")
            async def a(self) -> A:
                return A(1)

            @provide(executor="slow")
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]
        # Both A and B are in the same layer (independent)
        tags = {
            (dk.type_hint, ex)
            for dk, ex in strategy.dispatched
        }
        assert (A, "fast") in tags
        assert (B, "slow") in tags


class TestDefaultDispatch:
    """T034: Factory with no executor tag uses None (default)."""

    @pytest.mark.asyncio
    async def test_no_tag_uses_default(self) -> None:
        strategy = TrackingStrategy()

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

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]
        # Both should have executor=None
        for _dk, ex in strategy.dispatched:
            assert ex is None


class TestNonDispatchStrategy:
    """T035: Strategy that ignores executor tags still works."""

    @pytest.mark.asyncio
    async def test_executor_tags_ignored(self) -> None:
        """Strategy receives executor tags but ignores them."""

        class IgnoringStrategy:
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
                results: list[object] = [None] * len(factories)
                for i, (_key, factory, _executor) in enumerate(
                    factories,
                ):
                    results[i] = await factory()
                return results

        class MyProvider(Provider):
            scope = Scope.APP

            @provide(executor="fast")
            async def a(self) -> A:
                return A(1)

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        strategy = IgnoringStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]


class TestTagPrecedence:
    """T036: Explicit tag wins over strategy-level routing."""

    @pytest.mark.asyncio
    async def test_explicit_tag_precedence(self) -> None:
        strategy = TrackingStrategy()

        class MyProvider(Provider):
            scope = Scope.APP

            @provide(executor="explicit")
            async def a(self) -> A:
                return A(1)

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]
        tags = {
            dk.type_hint: ex
            for dk, ex in strategy.dispatched
        }
        assert tags[A] == "explicit"
        assert tags[B] is None


class TestUnrecognizedExecutorTag:
    """T057: Unrecognized executor tag — built-in strategy works."""

    @pytest.mark.asyncio
    async def test_unknown_tag_no_error(self) -> None:
        """Built-in strategies accept unknown tags without error."""
        class MyProvider(Provider):
            scope = Scope.APP

            @provide(executor="nonexistent_pool")
            async def a(self) -> A:
                return A(1)

            @provide(executor="also_unknown")
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
        async with container:
            result = await container.get(list[Any])

        assert result == [1, 2]
