from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from dishka.container_objects import CompiledFactory
from dishka.entities.key import DependencyKey


@runtime_checkable
class AsyncConcurrencyStrategy(Protocol):
    async def run(
        self,
        factories: Sequence[
            tuple[
                DependencyKey,
                Callable[[], Awaitable[object]],
                str | None,
            ]
        ],
    ) -> Sequence[object]: ...


@runtime_checkable
class CompilableAsyncStrategy(AsyncConcurrencyStrategy, Protocol):
    """Async strategy that also supports codegen via compile()."""

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory, str | None]
        ],
    ) -> CompiledFactory: ...


@runtime_checkable
class SyncConcurrencyStrategy(Protocol):
    def run(
        self,
        factories: Sequence[
            tuple[
                DependencyKey,
                Callable[[], object],
                str | None,
            ]
        ],
    ) -> Sequence[object]: ...


@runtime_checkable
class CompilableSyncStrategy(SyncConcurrencyStrategy, Protocol):
    """Sync strategy that also supports codegen via compile()."""

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory, str | None]
        ],
    ) -> CompiledFactory: ...
