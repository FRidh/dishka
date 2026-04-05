"""Sync-specific tests (barrier proof, sequential fallback)."""
from __future__ import annotations

import threading
from typing import Any

from dishka import (
    Provider,
    Scope,
    make_container,
    provide,
)
from dishka.concurrency._sync import ThreadPoolStrategy
from .conftest import A, B


class TestThreadPoolConcurrent:
    """Thread pool concurrent execution with barrier proof."""

    def test_independent_factories_overlap(self) -> None:
        barrier = threading.Barrier(2, timeout=5)

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                barrier.wait()
                return A(1)

            @provide
            def b(self) -> B:
                barrier.wait()
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


class TestSequentialWithoutExecutor:
    """No executor => identical sequential behavior."""

    def test_sequential_no_concurrency(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                return A(1)

            @provide
            def root(self, a: A) -> list[Any]:
                return [a]

        container = make_container(MyProvider())
        with container:
            result = container.get(list[Any])
        assert result == [1]
