"""Benchmarks: topological layer computation overhead."""
from __future__ import annotations

from typing import NewType

import pytest

from dishka import Provider, Scope, make_async_container, provide
from dishka.concurrency._layers import compute_topological_layers
from dishka.entities.component import DEFAULT_COMPONENT
from dishka.entities.key import DependencyKey


def _make_leaf_factory(lt, i):
    """Return a no-dep factory function with proper annotations."""
    def factory(self) -> lt:
        return lt(i)
    factory.__annotations__ = {"return": lt}
    return factory


def _make_root_factory(leaf_types, root_type):
    """Return a multi-dep root factory with proper annotations."""
    param_names = [f"l{i}" for i in range(len(leaf_types))]

    def factory(self, **kwargs) -> root_type:
        return root_type(list(kwargs.values()))

    # Build annotations without **kwargs — use named params
    annotations = {
        name: lt for name, lt in zip(param_names, leaf_types)
    }
    annotations["return"] = root_type

    # Build a proper function signature via exec to avoid **kwargs
    params = ", ".join(
        f"{name}: leaf_types[{i}]"
        for i, name in enumerate(param_names)
    )
    code = (
        f"def root_factory(self, {params}) -> root_type:\n"
        f"    return root_type([{', '.join(param_names)}])\n"
    )
    ns = {"leaf_types": leaf_types, "root_type": root_type}
    exec(code, ns)  # noqa: S102
    return ns["root_factory"]


def _make_chain_factory(prev_type, cur_type):
    """Return a single-dep factory function with annotations."""
    def factory(self, dep: prev_type) -> cur_type:
        return cur_type(dep)
    factory.__annotations__ = {"dep": prev_type, "return": cur_type}
    return factory


def _make_wide_provider(n: int):
    """Create a provider with n independent leaves + 1 root."""
    leaf_types = [NewType(f"L{i}", int) for i in range(n)]
    root_type = NewType("Root", list)

    class P(Provider):
        scope = Scope.APP

    for i, lt in enumerate(leaf_types):
        factory = _make_leaf_factory(lt, i)
        setattr(P, f"leaf_{i}", provide(factory))

    root_factory = _make_root_factory(leaf_types, root_type)
    setattr(P, "root", provide(root_factory))

    return P(), root_type


def _make_chain_provider(depth: int):
    """Create a provider with a linear chain of given depth."""
    types = [NewType(f"N{i}", int) for i in range(depth)]

    class P(Provider):
        scope = Scope.APP

    first_factory = _make_leaf_factory(types[0], 0)
    setattr(P, "node_0", provide(first_factory))

    for i in range(1, depth):
        factory = _make_chain_factory(types[i - 1], types[i])
        setattr(P, f"node_{i}", provide(factory))

    return P(), types[-1]


class TestLayerComputationWide:

    @pytest.mark.parametrize("n", [5, 10, 20, 50])
    def test_wide_graph(self, benchmark, n):
        """N independent leaves + root — BFS + Kahn's on wide DAG."""
        provider, root_type = _make_wide_provider(n)
        container = make_async_container(provider)
        registry = container.registry
        root_key = DependencyKey(root_type, DEFAULT_COMPONENT)

        def compute():
            return compute_topological_layers(
                registry, root_key, {},
            )

        result = benchmark(compute)
        assert len(result) == 2  # leaves layer + root layer


class TestLayerComputationChain:

    @pytest.mark.parametrize("depth", [5, 10, 20, 50])
    def test_chain_graph(self, benchmark, depth):
        """Linear chain of N nodes — worst case for layer count."""
        provider, tip_type = _make_chain_provider(depth)
        container = make_async_container(provider)
        registry = container.registry
        root_key = DependencyKey(tip_type, DEFAULT_COMPONENT)

        def compute():
            return compute_topological_layers(
                registry, root_key, {},
            )

        result = benchmark(compute)
        assert len(result) == depth
