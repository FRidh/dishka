from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from dishka.code_tools.code_builder import CodeBuilder
from dishka.container_objects import CompiledFactory
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

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory]
        ],
    ) -> CompiledFactory:
        import trio

        builder = CodeBuilder(is_async=True)
        open_nursery = builder.global_(
            trio.open_nursery, "open_nursery",
        )
        beg_name = builder.global_(
            BaseExceptionGroup, "BaseExceptionGroup",
        )

        factory_names: list[str] = []
        for i, (_dk, compiled) in enumerate(
            compiled_factories,
        ):
            name = builder.global_(compiled, f"factory_{i}")
            factory_names.append(name)

        args = [
            "getter", "exits", "cache",
            "context", "container", "has",
        ]
        with builder.def_("_concurrent_layer", args):
            with builder.try_():
                with builder.with_(
                    builder.call(open_nursery),
                    "nursery",
                    is_async=True,
                ):
                    for i, name in enumerate(factory_names):
                        wrapper = f"_wrap_{i}"
                        with builder.def_(wrapper, []):
                            builder.statement(
                                f"await {name}("
                                f"getter, exits, cache, "
                                f"context, container, "
                                f"has)",
                            )
                        builder.statement(
                            f"nursery.start_soon({wrapper})",
                        )
            with builder.except_(
                BaseExceptionGroup, as_="exc",
            ):
                with builder.if_(
                    "len(exc.exceptions) == 1",
                ):
                    builder.statement(
                        "raise exc.exceptions[0]"
                        " from exc.__cause__",
                    )
                builder.raise_()

        result = builder.compile(
            "<concurrent_trio_layer>",
        )
        return result["_concurrent_layer"]
