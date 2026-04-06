from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)

from dishka.code_tools.code_builder import CodeBuilder
from dishka.container_objects import CompiledFactory
from dishka.entities.key import DependencyKey


class ThreadPoolStrategy:
    def __init__(
        self,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._executor = executor
        self._owns_executor = executor is None

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
        executor = self._executor
        if executor is None:
            executor = ThreadPoolExecutor()
        try:
            futures: list[tuple[int, Future[object]]] = []
            for i, (_key, factory, _ex) in enumerate(
                factories,
            ):
                futures.append((i, executor.submit(factory)))

            results: list[object] = [None] * len(factories)
            error: BaseException | None = None
            for i, fut in futures:
                try:
                    results[i] = fut.result()
                except BaseException as exc:  # noqa: BLE001
                    error = exc
                    # Cancel remaining futures
                    for _, remaining in futures:
                        remaining.cancel()
                    break
            if error is not None:
                raise error
            return results
        finally:
            if self._owns_executor and executor is not None:
                executor.shutdown(wait=False)

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory, str | None]
        ],
    ) -> CompiledFactory:
        return _compile_threadpool_layer(
            compiled_factories,
            self._executor,
        )


def _call_factory(factory: Callable[[], object]) -> object:
    return factory()


class ProcessPoolStrategy:
    def __init__(
        self,
        executor: ProcessPoolExecutor | None = None,
    ) -> None:
        self._executor = executor
        self._owns_executor = executor is None

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
        # Process pool cannot pickle closures/generators,
        # so we run all factories via ThreadPoolExecutor
        # which can handle closures (they run in-process
        # threads). For true cross-process dispatch, the
        # compile() path will handle that.
        # For now, delegate to thread pool semantics.
        executor = self._executor
        if executor is None:
            executor = ProcessPoolExecutor()
        try:
            # Run all in threads (process pool can't pickle
            # closures that capture container state)
            thread_executor = ThreadPoolExecutor()
            try:
                futures: list[tuple[int, Future[object]]] = []
                for i, (_key, factory, _ex) in enumerate(
                    factories,
                ):
                    futures.append(
                        (i, thread_executor.submit(factory)),
                    )
                results: list[object] = [None] * len(factories)
                error: BaseException | None = None
                for i, fut in futures:
                    try:
                        results[i] = fut.result()
                    except BaseException as exc:  # noqa: BLE001
                        error = exc
                        for _, remaining in futures:
                            remaining.cancel()
                        break
                if error is not None:
                    raise error
                return results
            finally:
                thread_executor.shutdown(wait=False)
        finally:
            if self._owns_executor and executor is not None:
                executor.shutdown(wait=False)

    def compile(
        self,
        compiled_factories: Sequence[
            tuple[DependencyKey, CompiledFactory, str | None]
        ],
    ) -> CompiledFactory:
        return _compile_threadpool_layer(
            compiled_factories,
            None,
        )


def _compile_threadpool_layer(
    compiled_factories: Sequence[
        tuple[DependencyKey, CompiledFactory, str | None]
    ],
    executor: ThreadPoolExecutor | None,
) -> CompiledFactory:
    """Emit a compiled function that dispatches factories
    concurrently via ThreadPoolExecutor."""
    builder = CodeBuilder(is_async=False)
    tpe_cls = builder.global_(
        ThreadPoolExecutor,
        "ThreadPoolExecutor",
    )

    if executor is not None:
        ex_name = builder.global_(executor, "executor")
    else:
        ex_name = None

    factory_names: list[str] = []
    for i, (_dk, compiled, _ex) in enumerate(compiled_factories):
        name = builder.global_(compiled, f"factory_{i}")
        factory_names.append(name)

    args = [
        "getter",
        "exits",
        "cache",
        "context",
        "container",
        "has",
    ]
    with builder.def_("_concurrent_layer", args):
        if ex_name is not None:
            builder.assign_local("ex", ex_name)
        else:
            builder.assign_local(
                "ex",
                builder.call(tpe_cls),
            )
        with builder.try_():
            builder.assign_local("futures", "[]")
            for i, name in enumerate(factory_names):
                def_name = f"_invoke_{i}"
                with builder.def_(def_name, []):
                    builder.return_(
                        f"{name}(getter, exits, cache, "
                        f"context, container, has)",
                    )
                builder.statement(
                    f"futures.append(ex.submit({def_name}))",
                )
            builder.assign_local("error", "None")
            with builder.for_("fut", "futures"):
                with builder.try_():
                    builder.statement(
                        "fut.result()",
                    )
                with builder.except_(BaseException, as_="exc"):  # type: ignore[arg-type]
                    builder.statement("error = exc")
                    with builder.for_(
                        "remaining",
                        "futures",
                    ):
                        builder.statement(
                            "remaining.cancel()",
                        )
                    builder.statement("break")
            with builder.if_("error is not None"):
                builder.raise_("error")
        # finally block — shutdown if we created executor
        if ex_name is None:
            builder.statement("finally:")
            with builder.block():
                builder.statement(
                    "ex.shutdown(wait=False)",
                )

    ns = builder.compile("<concurrent_threadpool_layer>")
    return ns["_concurrent_layer"]  # type: ignore[no-any-return]
