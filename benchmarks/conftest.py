"""Shared dependency graphs for benchmarks."""
from __future__ import annotations

import asyncio
from typing import NewType

from dishka import Provider, Scope, provide

# ── Type aliases for graph nodes ───────────────────────────────────

# Shallow graph
Shallow = NewType("Shallow", int)

# Deep chain: F → E → D → C → B → A
ChainA = NewType("ChainA", int)
ChainB = NewType("ChainB", int)
ChainC = NewType("ChainC", int)
ChainD = NewType("ChainD", int)
ChainE = NewType("ChainE", int)
ChainF = NewType("ChainF", int)

# Wide graph: Root depends on Leaf0..Leaf9
Leaf0 = NewType("Leaf0", int)
Leaf1 = NewType("Leaf1", int)
Leaf2 = NewType("Leaf2", int)
Leaf3 = NewType("Leaf3", int)
Leaf4 = NewType("Leaf4", int)
Leaf5 = NewType("Leaf5", int)
Leaf6 = NewType("Leaf6", int)
Leaf7 = NewType("Leaf7", int)
Leaf8 = NewType("Leaf8", int)
Leaf9 = NewType("Leaf9", int)
WideRoot = NewType("WideRoot", list)

# Diamond graph: Top → Left, Right → Bottom
Bottom = NewType("Bottom", int)
Left = NewType("Left", int)
Right = NewType("Right", int)
Top = NewType("Top", list)


# ── Sync providers ─────────────────────────────────────────────────

class ShallowProvider(Provider):
    scope = Scope.APP

    @provide
    def shallow(self) -> Shallow:
        return Shallow(1)


class DeepChainProvider(Provider):
    scope = Scope.APP

    @provide
    def a(self) -> ChainA:
        return ChainA(1)

    @provide
    def b(self, a: ChainA) -> ChainB:
        return ChainB(a)

    @provide
    def c(self, b: ChainB) -> ChainC:
        return ChainC(b)

    @provide
    def d(self, c: ChainC) -> ChainD:
        return ChainD(c)

    @provide
    def e(self, d: ChainD) -> ChainE:
        return ChainE(d)

    @provide
    def f(self, e: ChainE) -> ChainF:
        return ChainF(e)


class WideProvider(Provider):
    scope = Scope.APP

    @provide
    def leaf0(self) -> Leaf0:
        return Leaf0(0)

    @provide
    def leaf1(self) -> Leaf1:
        return Leaf1(1)

    @provide
    def leaf2(self) -> Leaf2:
        return Leaf2(2)

    @provide
    def leaf3(self) -> Leaf3:
        return Leaf3(3)

    @provide
    def leaf4(self) -> Leaf4:
        return Leaf4(4)

    @provide
    def leaf5(self) -> Leaf5:
        return Leaf5(5)

    @provide
    def leaf6(self) -> Leaf6:
        return Leaf6(6)

    @provide
    def leaf7(self) -> Leaf7:
        return Leaf7(7)

    @provide
    def leaf8(self) -> Leaf8:
        return Leaf8(8)

    @provide
    def leaf9(self) -> Leaf9:
        return Leaf9(9)

    @provide
    def root(
        self,
        l0: Leaf0, l1: Leaf1, l2: Leaf2, l3: Leaf3, l4: Leaf4,
        l5: Leaf5, l6: Leaf6, l7: Leaf7, l8: Leaf8, l9: Leaf9,
    ) -> WideRoot:
        return WideRoot([l0, l1, l2, l3, l4, l5, l6, l7, l8, l9])


class DiamondProvider(Provider):
    scope = Scope.APP

    @provide
    def bottom(self) -> Bottom:
        return Bottom(1)

    @provide
    def left(self, b: Bottom) -> Left:
        return Left(b)

    @provide
    def right(self, b: Bottom) -> Right:
        return Right(b)

    @provide
    def top(self, l: Left, r: Right) -> Top:
        return Top([l, r])


# ── Async providers ────────────────────────────────────────────────

class AsyncShallowProvider(Provider):
    scope = Scope.APP

    @provide
    async def shallow(self) -> Shallow:
        return Shallow(1)


class AsyncDeepChainProvider(Provider):
    scope = Scope.APP

    @provide
    async def a(self) -> ChainA:
        return ChainA(1)

    @provide
    async def b(self, a: ChainA) -> ChainB:
        return ChainB(a)

    @provide
    async def c(self, b: ChainB) -> ChainC:
        return ChainC(b)

    @provide
    async def d(self, c: ChainC) -> ChainD:
        return ChainD(c)

    @provide
    async def e(self, d: ChainD) -> ChainE:
        return ChainE(d)

    @provide
    async def f(self, e: ChainE) -> ChainF:
        return ChainF(e)


class AsyncWideProvider(Provider):
    scope = Scope.APP

    @provide
    async def leaf0(self) -> Leaf0:
        return Leaf0(0)

    @provide
    async def leaf1(self) -> Leaf1:
        return Leaf1(1)

    @provide
    async def leaf2(self) -> Leaf2:
        return Leaf2(2)

    @provide
    async def leaf3(self) -> Leaf3:
        return Leaf3(3)

    @provide
    async def leaf4(self) -> Leaf4:
        return Leaf4(4)

    @provide
    async def leaf5(self) -> Leaf5:
        return Leaf5(5)

    @provide
    async def leaf6(self) -> Leaf6:
        return Leaf6(6)

    @provide
    async def leaf7(self) -> Leaf7:
        return Leaf7(7)

    @provide
    async def leaf8(self) -> Leaf8:
        return Leaf8(8)

    @provide
    async def leaf9(self) -> Leaf9:
        return Leaf9(9)

    @provide
    async def root(
        self,
        l0: Leaf0, l1: Leaf1, l2: Leaf2, l3: Leaf3, l4: Leaf4,
        l5: Leaf5, l6: Leaf6, l7: Leaf7, l8: Leaf8, l9: Leaf9,
    ) -> WideRoot:
        return WideRoot([l0, l1, l2, l3, l4, l5, l6, l7, l8, l9])


class AsyncDiamondProvider(Provider):
    scope = Scope.APP

    @provide
    async def bottom(self) -> Bottom:
        return Bottom(1)

    @provide
    async def left(self, b: Bottom) -> Left:
        return Left(b)

    @provide
    async def right(self, b: Bottom) -> Right:
        return Right(b)

    @provide
    async def top(self, l: Left, r: Right) -> Top:
        return Top([l, r])


# ── Async providers with simulated I/O ─────────────────────────────

SIMULATED_IO_DELAY = 0.01  # 10ms


class AsyncWideSlowProvider(Provider):
    """Wide graph where each leaf has simulated I/O delay."""
    scope = Scope.APP

    @provide
    async def leaf0(self) -> Leaf0:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf0(0)

    @provide
    async def leaf1(self) -> Leaf1:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf1(1)

    @provide
    async def leaf2(self) -> Leaf2:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf2(2)

    @provide
    async def leaf3(self) -> Leaf3:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf3(3)

    @provide
    async def leaf4(self) -> Leaf4:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf4(4)

    @provide
    async def leaf5(self) -> Leaf5:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf5(5)

    @provide
    async def leaf6(self) -> Leaf6:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf6(6)

    @provide
    async def leaf7(self) -> Leaf7:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf7(7)

    @provide
    async def leaf8(self) -> Leaf8:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf8(8)

    @provide
    async def leaf9(self) -> Leaf9:
        await asyncio.sleep(SIMULATED_IO_DELAY)
        return Leaf9(9)

    @provide
    async def root(
        self,
        l0: Leaf0, l1: Leaf1, l2: Leaf2, l3: Leaf3, l4: Leaf4,
        l5: Leaf5, l6: Leaf6, l7: Leaf7, l8: Leaf8, l9: Leaf9,
    ) -> WideRoot:
        return WideRoot([l0, l1, l2, l3, l4, l5, l6, l7, l8, l9])
