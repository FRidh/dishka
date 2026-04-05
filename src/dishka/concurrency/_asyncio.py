from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from dishka.code_tools.code_builder import CodeBuilder
from dishka.container_objects import CompiledFactory
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

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory]
        ],
    ) -> CompiledFactory:
        return _compile_asyncio_layer(compiled_factories)


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

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory]
        ],
    ) -> CompiledFactory:
        return _compile_asyncio_semaphore_layer(
            compiled_factories, self._max_concurrent,
        )


def _compile_asyncio_layer(
    compiled_factories: Sequence[
        tuple[DependencyKey, CompiledFactory]
    ],
) -> CompiledFactory:
    """Emit a compiled function that dispatches factories
    concurrently via asyncio.TaskGroup."""
    builder = CodeBuilder(is_async=True)
    tg_name = builder.global_(asyncio.TaskGroup, "TaskGroup")
    eg_name = builder.global_(ExceptionGroup, "ExceptionGroup")

    factory_names: list[str] = []
    for i, (_dk, compiled) in enumerate(compiled_factories):
        name = builder.global_(compiled, f"factory_{i}")
        factory_names.append(name)

    args = [
        "getter", "exits", "cache",
        "context", "container", "has",
    ]
    with builder.def_("_concurrent_layer", args):
        with builder.try_():
            with builder.with_(
                builder.call(tg_name),
                "tg",
                is_async=True,
            ):
                for i, name in enumerate(factory_names):
                    builder.statement(
                        f"tg.create_task({name}("
                        f"getter, exits, cache, "
                        f"context, container, has))",
                    )
        with builder.except_(BaseException, as_="exc"):
            with builder.if_(
                f"isinstance(exc, {eg_name})"
                f" and len(exc.exceptions) == 1",
            ):
                builder.statement(
                    "raise exc.exceptions[0]"
                    " from exc.__cause__",
                )
            builder.raise_()

    result = builder.compile("<concurrent_asyncio_layer>")
    return result["_concurrent_layer"]


def _compile_asyncio_semaphore_layer(
    compiled_factories: Sequence[
        tuple[DependencyKey, CompiledFactory]
    ],
    max_concurrent: int,
) -> CompiledFactory:
    """Emit a compiled function that dispatches factories
    concurrently via asyncio.TaskGroup + Semaphore."""
    builder = CodeBuilder(is_async=True)
    tg_name = builder.global_(asyncio.TaskGroup, "TaskGroup")
    sem_cls = builder.global_(asyncio.Semaphore, "Semaphore")
    max_c = builder.global_(max_concurrent, "max_concurrent")

    factory_names: list[str] = []
    for i, (_dk, compiled) in enumerate(compiled_factories):
        name = builder.global_(compiled, f"factory_{i}")
        factory_names.append(name)

    args = [
        "getter", "exits", "cache",
        "context", "container", "has",
    ]
    with builder.def_("_concurrent_layer", args):
        builder.assign_local(
            "sem", builder.call(sem_cls, max_c),
        )
        with builder.with_(
            builder.call(tg_name),
            "tg",
            is_async=True,
        ):
            for i, name in enumerate(factory_names):
                # Emit a wrapper coroutine per factory
                wrapper = f"_wrap_{i}"
                with builder.def_(wrapper, []):
                    with builder.with_(
                        "sem", is_async=True,
                    ):
                        builder.statement(
                            f"await {name}("
                            f"getter, exits, cache, "
                            f"context, container, has)",
                        )
                builder.statement(
                    f"tg.create_task({wrapper}())",
                )

    result = builder.compile(
        "<concurrent_asyncio_semaphore_layer>",
    )
    return result["_concurrent_layer"]
