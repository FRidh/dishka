"""Sync-specific tests (barrier proof, sequential fallback)."""
from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

from dishka import (
    Provider,
    Scope,
    make_container,
    provide,
)
from dishka.concurrency._sync import (
    ThreadPoolStrategy,
    _compile_threadpool_layer,
)
from dishka.container_objects import CompiledFactory
from dishka.entities.key import DependencyKey
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


class TrackingCompilableSyncStrategy:
    """Compilable strategy that records executor tags
    during compile()."""

    def __init__(self) -> None:
        self.compiled_tags: list[
            tuple[DependencyKey, str | None]
        ] = []

    def run(
        self,
        factories: Sequence[
            tuple[
                DependencyKey,
                Callable[[], object],
                str | None,
            ]
        ],
    ) -> Sequence[object]:
        results: list[object] = [None] * len(factories)
        for i, (_k, f, _ex) in enumerate(factories):
            results[i] = f()
        return results

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory, str | None]
        ],
    ) -> CompiledFactory:
        for dk, _cf, executor in compiled_factories:
            self.compiled_tags.append((dk, executor))
        return _compile_threadpool_layer(
            compiled_factories, None,
        )


class TestSyncCompilePathReceivesExecutorTags:
    """compile() receives per-factory executor tags (sync)."""

    def test_tags_passed_to_compile(self) -> None:
        strategy = TrackingCompilableSyncStrategy()

        class MyProvider(Provider):
            scope = Scope.APP

            @provide(executor="fast")
            def a(self) -> A:
                return A(1)

            @provide(executor="slow")
            def b(self) -> B:
                return B(2)

            @provide
            def root(self, a: A, b: B) -> list[Any]:
                return [a, b]

        container = make_container(
            MyProvider(),
            concurrency=strategy,
        )
        with container:
            result = container.get(list[Any])

        assert result == [1, 2]
        tags = {
            (dk.type_hint, ex)
            for dk, ex in strategy.compiled_tags
        }
        assert (A, "fast") in tags
        assert (B, "slow") in tags


class TestSyncCompilePathDefaultTags:
    """compile() receives None for factories without
    executor (sync)."""

    def test_no_tag_passes_none(self) -> None:
        strategy = TrackingCompilableSyncStrategy()

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

        container = make_container(
            MyProvider(),
            concurrency=strategy,
        )
        with container:
            result = container.get(list[Any])

        assert result == [1, 2]
        for _dk, ex in strategy.compiled_tags:
            assert ex is None
