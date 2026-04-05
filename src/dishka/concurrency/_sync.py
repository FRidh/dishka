from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)

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
            tuple[DependencyKey, Callable[[], object]]
        ],
    ) -> Sequence[object]:
        executor = self._executor
        if executor is None:
            executor = ThreadPoolExecutor()
        try:
            futures: list[tuple[int, Future[object]]] = []
            for i, (_key, factory) in enumerate(factories):
                futures.append((i, executor.submit(factory)))

            results: list[object] = [None] * len(factories)
            error: BaseException | None = None
            for i, fut in futures:
                try:
                    results[i] = fut.result()
                except BaseException as exc:
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
            tuple[DependencyKey, Callable[[], object]]
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
                for i, (_key, factory) in enumerate(factories):
                    futures.append(
                        (i, thread_executor.submit(factory)),
                    )
                results: list[object] = [None] * len(factories)
                error: BaseException | None = None
                for i, fut in futures:
                    try:
                        results[i] = fut.result()
                    except BaseException as exc:
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
