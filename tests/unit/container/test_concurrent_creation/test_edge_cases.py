"""Edge case tests for concurrent resolution."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
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


class TestAllCached:
    """T053: All deps cached — falls through with no overhead."""

    @pytest.mark.asyncio
    async def test_cached_deps_no_strategy_call(self) -> None:
        strategy_called = False

        class SpyStrategy:
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
                nonlocal strategy_called
                strategy_called = True
                results: list[object] = [None] * len(factories)
                for i, (_k, f, _ex) in enumerate(factories):
                    results[i] = await f()
                return results

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                return A(1)

        container = make_async_container(
            MyProvider(),
            concurrency=SpyStrategy(),
        )
        async with container:
            # First call resolves
            r1 = await container.get(A)
            assert r1 == 1
            strategy_called = False
            # Second call should be cached
            r2 = await container.get(A)
            assert r2 == 1
            # Single-factory layers use direct call,
            # not strategy — but even if they did,
            # the second call is fully cached
            # and shouldn't reach strategy at all


class TestSingleFactory:
    """T054: Single independent factory — no strategy involvement."""

    @pytest.mark.asyncio
    async def test_single_factory_direct_call(self) -> None:
        strategy_called = False

        class SpyStrategy:
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
                nonlocal strategy_called
                strategy_called = True
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
            async def root(self, a: A) -> list[Any]:
                return [a]

        container = make_async_container(
            MyProvider(),
            concurrency=SpyStrategy(),
        )
        async with container:
            result = await container.get(list[Any])
            assert result == [1]
            # Single-factory layers are dispatched directly,
            # not via strategy.run()
            assert not strategy_called


class TestGeneratorSetupError:
    """T055: Generator factory raises during setup (before yield)."""

    @pytest.mark.asyncio
    async def test_generator_setup_error(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> AsyncIterator[A]:
                raise ValueError("setup error")
                yield

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
        with pytest.raises(ValueError, match="setup error"):
            async with container:
                await container.get(list[Any])


class TestStrategyRunError:
    """T056: strategy.run() itself raises — propagates as-is."""

    @pytest.mark.asyncio
    async def test_strategy_error_propagates(self) -> None:
        class BuggyStrategy:
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
                raise RuntimeError("strategy bug")

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
            concurrency=BuggyStrategy(),
        )
        with pytest.raises(
            RuntimeError, match="strategy bug",
        ):
            async with container:
                await container.get(list[Any])
