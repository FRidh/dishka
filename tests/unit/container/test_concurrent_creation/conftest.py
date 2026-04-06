"""Shared fixtures for concurrent creation tests."""
from __future__ import annotations

from enum import StrEnum, auto
from typing import NewType

import pytest

from dishka import (
    AsyncioSemaphoreStrategy,
    AsyncioStrategy,
)
from dishka.concurrency._sync import (
    ThreadPoolStrategy,
)
from dishka.concurrency._trio import TrioStrategy

# ── shared type aliases ──────────────────────────────────────────────
A = NewType("A", int)
B = NewType("B", int)
C = NewType("C", int)
D = NewType("D", int)
Leaf = NewType("Leaf", int)
Root = NewType("Root", list)


# ── strategy identifiers ────────────────────────────────────────────


class AsyncStrategy(StrEnum):
    ASYNCIO = auto()
    SEMAPHORE = auto()
    TRIO = auto()


class SyncStrategy(StrEnum):
    THREADPOOL = auto()


def make_async_strategy(name: AsyncStrategy) -> object:
    match name:
        case AsyncStrategy.ASYNCIO:
            return AsyncioStrategy()
        case AsyncStrategy.SEMAPHORE:
            return AsyncioSemaphoreStrategy(max_concurrent=4)
        case AsyncStrategy.TRIO:
            return TrioStrategy()


def make_sync_strategy(name: SyncStrategy) -> object:
    match name:
        case SyncStrategy.THREADPOOL:
            return ThreadPoolStrategy()


@pytest.fixture(params=AsyncStrategy)
def async_strategy_name(
    request: pytest.FixtureRequest,
) -> AsyncStrategy:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(params=SyncStrategy)
def sync_strategy_name(
    request: pytest.FixtureRequest,
) -> SyncStrategy:
    return request.param  # type: ignore[no-any-return]
