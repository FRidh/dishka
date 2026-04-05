"""Asyncio-specific diamond test with barrier proof of concurrency."""
from __future__ import annotations

import asyncio

import pytest

from dishka import (
    AsyncioStrategy,
    Provider,
    Scope,
    make_async_container,
    provide,
)
from .conftest import A, B, Leaf, Root


class TestDiamondDeduplication:
    """Root -> A, B -> Leaf; Leaf created once, A and B concurrent."""

    @pytest.mark.asyncio()
    async def test_leaf_created_once(self) -> None:
        call_count = 0
        barrier = asyncio.Barrier(2)

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            async def leaf(self) -> Leaf:
                nonlocal call_count
                call_count += 1
                return Leaf(99)

            @provide
            async def a(self, leaf: Leaf) -> A:
                await barrier.wait()
                return A(leaf + 1)

            @provide
            async def b(self, leaf: Leaf) -> B:
                await barrier.wait()
                return B(leaf + 2)

            @provide
            async def root(self, a: A, b: B) -> Root:
                return Root([a, b])

        strategy = AsyncioStrategy()
        container = make_async_container(
            MyProvider(),
            concurrency=strategy,
        )
        async with container() as scope:
            result = await asyncio.wait_for(
                scope.get(Root),
                timeout=5.0,
            )
        assert call_count == 1
        assert result == [100, 101]
