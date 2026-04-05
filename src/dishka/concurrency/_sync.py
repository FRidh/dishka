from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import (
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

    def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], object]]
        ],
    ) -> Sequence[object]:
        raise NotImplementedError


class ProcessPoolStrategy:
    def __init__(
        self,
        executor: ProcessPoolExecutor | None = None,
    ) -> None:
        self._executor = executor

    def run(
        self,
        factories: Sequence[
            tuple[DependencyKey, Callable[[], object]]
        ],
    ) -> Sequence[object]:
        raise NotImplementedError
