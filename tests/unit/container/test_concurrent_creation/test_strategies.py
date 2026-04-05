"""Integration tests across all concurrency strategies.

Each test runs against every strategy to ensure consistent behavior.
Async strategies (asyncio, semaphore, trio) use make_async_container.
Sync strategies (threadpool, processpool) use make_container.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import trio as _trio

from dishka import (
    Provider,
    Scope,
    make_async_container,
    make_container,
    provide,
)
from .conftest import (
    A,
    AsyncStrategy,
    B,
    Leaf,
    Root,
    SyncStrategy,
    make_async_strategy,
    make_sync_strategy,
)

# ── helpers ──────────────────────────────────────────────────────────


async def _resolve_async(
    provider: Provider,
    target: type,
    strategy: object,
) -> object:
    container = make_async_container(
        provider,
        concurrency=strategy,
    )
    async with container:
        return await container.get(target)


def _resolve_sync(
    provider: Provider,
    target: type,
    strategy: object,
) -> object:
    container = make_container(
        provider,
        concurrency=strategy,
    )
    with container:
        return container.get(target)


async def _resolve_async_expecting_error(
    provider: Provider,
    target: type,
    strategy: object,
    error_cls: type[BaseException],
    match: str,
) -> None:
    container = make_async_container(
        provider,
        concurrency=strategy,
    )
    with pytest.raises(error_cls, match=match):
        async with container:
            await container.get(target)


def _resolve_sync_expecting_error(
    provider: Provider,
    target: type,
    strategy: object,
    error_cls: type[BaseException],
    match: str,
) -> None:
    container = make_container(
        provider,
        concurrency=strategy,
    )
    with container, pytest.raises(error_cls, match=match):
        container.get(target)


def _is_trio(name: AsyncStrategy) -> bool:
    return name is AsyncStrategy.TRIO


# ── async strategy tests ─────────────────────────────────────────────


class TestAsyncHappyPath:
    """Basic resolution works for all async strategies."""

    @pytest.mark.asyncio()
    async def test_resolve(
        self, async_strategy_name: AsyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                return A(1)

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_async_strategy(async_strategy_name)
        if _is_trio(async_strategy_name):
            result = _trio.run(
                _resolve_async, P(), Root, strategy,
            )
        else:
            result = await _resolve_async(
                P(), Root, strategy,
            )
        assert result == [1, 2]


class TestAsyncErrorPropagation:
    """Factory errors propagate for all async strategies."""

    @pytest.mark.asyncio()
    async def test_error(
        self, async_strategy_name: AsyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                raise ValueError("boom")

            @provide
            async def b(self) -> B:
                return B(2)

            @provide
            async def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_async_strategy(async_strategy_name)
        if _is_trio(async_strategy_name):

            async def _run() -> None:
                await _resolve_async_expecting_error(
                    P(), Root, strategy,
                    ValueError, "boom",
                )

            _trio.run(_run)
        else:
            await _resolve_async_expecting_error(
                P(), Root, strategy,
                ValueError, "boom",
            )


class TestAsyncDiamond:
    """Diamond dedup works for all async strategies."""

    @pytest.mark.asyncio()
    async def test_leaf_created_once(
        self, async_strategy_name: AsyncStrategy,
    ) -> None:
        call_count = 0

        class P(Provider):
            scope = Scope.APP

            @provide
            async def leaf(self) -> Leaf:
                nonlocal call_count
                call_count += 1
                return Leaf(99)

            @provide
            async def a(self, leaf: Leaf) -> A:
                return A(leaf + 1)

            @provide
            async def b(self, leaf: Leaf) -> B:
                return B(leaf + 2)

            @provide
            async def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_async_strategy(async_strategy_name)
        if _is_trio(async_strategy_name):
            result = _trio.run(
                _resolve_async, P(), Root, strategy,
            )
        else:
            result = await _resolve_async(
                P(), Root, strategy,
            )
        assert call_count == 1
        assert result == [100, 101]


class TestAsyncGeneratorCleanup:
    """Generator factories finalize for all async strategies."""

    @pytest.mark.asyncio()
    async def test_cleanup(
        self, async_strategy_name: AsyncStrategy,
    ) -> None:
        cleanup_called = False

        class P(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> AsyncIterator[A]:
                nonlocal cleanup_called
                yield A(42)
                cleanup_called = True

        strategy = make_async_strategy(async_strategy_name)
        if _is_trio(async_strategy_name):

            async def _run() -> None:
                nonlocal cleanup_called
                container = make_async_container(
                    P(), concurrency=strategy,
                )
                async with container:
                    r = await container.get(A)
                    assert r == 42
                    assert not cleanup_called
                assert cleanup_called

            _trio.run(_run)
        else:
            container = make_async_container(
                P(), concurrency=strategy,
            )
            async with container:
                r = await container.get(A)
                assert r == 42
                assert not cleanup_called
            assert cleanup_called


class TestAsyncCodegenParity:
    """Codegen path produces same results for all async strategies."""

    @pytest.mark.asyncio()
    async def test_codegen_results(
        self, async_strategy_name: AsyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            async def a(self) -> A:
                return A(10)

            @provide
            async def b(self) -> B:
                return B(20)

            @provide
            async def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_async_strategy(async_strategy_name)
        if _is_trio(async_strategy_name):
            result = _trio.run(
                _resolve_async, P(), Root, strategy,
            )
        else:
            result = await _resolve_async(
                P(), Root, strategy,
            )
        assert result == [10, 20]


# ── sync strategy tests ──────────────────────────────────────────────


class TestSyncHappyPath:
    """Basic resolution works for all sync strategies."""

    def test_resolve(
        self, sync_strategy_name: SyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                return A(1)

            @provide
            def b(self) -> B:
                return B(2)

            @provide
            def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_sync_strategy(sync_strategy_name)
        result = _resolve_sync(P(), Root, strategy)
        assert result == [1, 2]


class TestSyncErrorPropagation:
    """Factory errors propagate for all sync strategies."""

    def test_error(
        self, sync_strategy_name: SyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                raise ValueError("sync boom")

            @provide
            def b(self) -> B:
                return B(2)

            @provide
            def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_sync_strategy(sync_strategy_name)
        _resolve_sync_expecting_error(
            P(), Root, strategy,
            ValueError, "sync boom",
        )


class TestSyncDiamond:
    """Diamond dedup works for all sync strategies."""

    def test_leaf_created_once(
        self, sync_strategy_name: SyncStrategy,
    ) -> None:
        call_count = 0

        class P(Provider):
            scope = Scope.APP

            @provide
            def leaf(self) -> Leaf:
                nonlocal call_count
                call_count += 1
                return Leaf(99)

            @provide
            def a(self, leaf: Leaf) -> A:
                return A(leaf + 1)

            @provide
            def b(self, leaf: Leaf) -> B:
                return B(leaf + 2)

            @provide
            def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_sync_strategy(sync_strategy_name)
        result = _resolve_sync(P(), Root, strategy)
        assert call_count == 1
        assert result == [100, 101]


class TestSyncGeneratorCleanup:
    """Generator factories finalize for all sync strategies."""

    def test_cleanup(
        self, sync_strategy_name: SyncStrategy,
    ) -> None:
        cleanup_called = False

        class P(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> Iterator[A]:
                nonlocal cleanup_called
                yield A(42)
                cleanup_called = True

        strategy = make_sync_strategy(sync_strategy_name)
        container = make_container(
            P(), concurrency=strategy,
        )
        with container:
            r = container.get(A)
            assert r == 42
            assert not cleanup_called
        assert cleanup_called


class TestSyncCodegenParity:
    """Codegen path produces same results for all sync strategies."""

    def test_codegen_results(
        self, sync_strategy_name: SyncStrategy,
    ) -> None:
        class P(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                return A(10)

            @provide
            def b(self) -> B:
                return B(20)

            @provide
            def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = make_sync_strategy(sync_strategy_name)
        result = _resolve_sync(P(), Root, strategy)
        assert result == [10, 20]
