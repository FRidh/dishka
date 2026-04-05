from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from dishka.entities.key import DependencyKey


class TrioStrategy:
    async def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], Awaitable[object]]]
        ],
    ) -> Sequence[object]:
        raise NotImplementedError
