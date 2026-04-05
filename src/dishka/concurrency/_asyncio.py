from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from dishka.entities.key import DependencyKey


class AsyncioStrategy:
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
        results: list[object] = [None] * len(factories)

        try:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for i, (_key, factory, _ex) in enumerate(
                    factories,
                ):
                    tasks.append(
                        (i, tg.create_task(factory())),
                    )
        except BaseException as exc:
            # Unwrap single-exception ExceptionGroup to
            # preserve original error type (per spec).
            if (
                isinstance(exc, ExceptionGroup)
                and len(exc.exceptions) == 1
            ):
                raise exc.exceptions[0] from exc.__cause__
            raise

        for i, task in tasks:
            results[i] = task.result()
        return results


class AsyncioSemaphoreStrategy:
    def __init__(self, max_concurrent: int) -> None:
        self._max_concurrent = max_concurrent

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
        sem = asyncio.Semaphore(self._max_concurrent)
        results: list[object] = [None] * len(factories)

        async def _wrapped(
            idx: int,
            factory: Callable[[], Awaitable[object]],
        ) -> None:
            async with sem:
                results[idx] = await factory()

        async with asyncio.TaskGroup() as tg:
            for i, (_key, factory, _ex) in enumerate(
                factories,
            ):
                tg.create_task(_wrapped(i, factory))

        return results
