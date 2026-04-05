from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from dishka.entities.key import DependencyKey


class AsyncioStrategy:
    async def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], Awaitable[object]]]
        ],
    ) -> Sequence[object]:
        raise NotImplementedError


class AsyncioSemaphoreStrategy:
    def __init__(self, max_concurrent: int) -> None:
        self._max_concurrent = max_concurrent

    async def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], Awaitable[object]]]
        ],
    ) -> Sequence[object]:
        raise NotImplementedError
