from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from dishka.entities.key import DependencyKey


@runtime_checkable
class AsyncConcurrencyStrategy(Protocol):
    async def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], Awaitable[object]]]
        ],
    ) -> Sequence[object]: ...


@runtime_checkable
class SyncConcurrencyStrategy(Protocol):
    def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], object]]
        ],
    ) -> Sequence[object]: ...
