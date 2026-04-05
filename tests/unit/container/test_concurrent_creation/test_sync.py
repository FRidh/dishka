"""Tests for sync concurrent resolution with thread/process pools."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any, NewType

import pytest

from dishka import (
    Provider,
    Scope,
    make_container,
    provide,
)
from dishka.concurrency._sync import (
    ProcessPoolStrategy,
    ThreadPoolStrategy,
)

A = NewType("A", int)
B = NewType("B", int)


class TestThreadPoolConcurrent:
    """T023: Thread pool concurrent execution with barrier proof."""

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


class TestProcessPool:
    """T024: Process pool runs plain factories in pool."""

    def test_plain_factories_in_pool(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                return A(10)

            @provide
            def b(self) -> B:
                return B(20)

            @provide
            def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        strategy = ProcessPoolStrategy()
        container = make_container(
            MyProvider(),
            concurrency=strategy,
        )
        with container:
            result = container.get(list[Any])
        assert result == [10, 20]

    def test_generator_runs_locally(self) -> None:
        """Generator factories must run in calling process."""
        cleanup_called = False

        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> Iterator[A]:
                nonlocal cleanup_called
                yield A(42)
                cleanup_called = True

        strategy = ProcessPoolStrategy()
        container = make_container(
            MyProvider(),
            concurrency=strategy,
        )
        with container:
            result = container.get(A)
            assert result == 42
        assert cleanup_called


class TestThreadPoolErrorPropagation:
    """T025: Factory raises, no threads left running."""

    def test_error_propagates(self) -> None:
        class MyProvider(Provider):
            scope = Scope.APP

            @provide
            def a(self) -> A:
                raise ValueError("thread boom")

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
            with pytest.raises(ValueError, match="thread boom"):
                container.get(list[Any])


class TestSequentialWithoutExecutor:
    """T026: No executor => identical sequential behavior."""

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
