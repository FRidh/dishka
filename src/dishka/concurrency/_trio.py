from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from dishka.entities.key import DependencyKey


class TrioStrategy:
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
        import trio

        results: dict[int, object] = {}

        async def _wrapper(
            idx: int,
            factory: Callable[[], Awaitable[object]],
        ) -> None:
            results[idx] = await factory()

        try:
            async with trio.open_nursery() as nursery:
                for i, (_key, factory, _ex) in enumerate(
                    factories,
                ):
                    nursery.start_soon(_wrapper, i, factory)
        except BaseExceptionGroup as exc:
            if len(exc.exceptions) == 1:
                raise exc.exceptions[0] from exc.__cause__
            raise

        return [results[i] for i in range(len(factories))]
