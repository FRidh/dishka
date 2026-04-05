"""Tests for compute_topological_layers()."""
from __future__ import annotations

from typing import Any

import pytest

from dishka.concurrency._layers import compute_topological_layers
from dishka.dependency_source.factory import Factory
from dishka.entities.component import DEFAULT_COMPONENT
from dishka.entities.factory_type import FactoryType
from dishka.entities.key import DependencyKey
from dishka.entities.scope import Scope
from dishka.registry import Registry


def _key(name: str) -> DependencyKey:
    """Create a DependencyKey from a string tag."""
    return DependencyKey(name, DEFAULT_COMPONENT)


def _factory(
    provides: DependencyKey,
    deps: list[DependencyKey] | None = None,
) -> Factory:
    return Factory(
        dependencies=deps or [],
        kw_dependencies={},
        source=lambda: provides.type_hint,
        provides=provides,
        scope=Scope.APP,
        type_=FactoryType.FACTORY,
        is_to_bind=False,
        cache=True,
        when_override=None,
        when_active=None,
        when_component=None,
        when_dependencies=[],
    )


def _make_registry(
    factories: dict[DependencyKey, Factory],
) -> Registry:
    reg = Registry(
        Scope.APP,
        has_fallback=False,
        container_key=_key("__container__"),
    )
    for key, factory in factories.items():
        reg.add_factory(factory, key)
    return reg


class TestLinearChain:
    """A -> B -> C  (C is a leaf)."""

    def test_layers(self) -> None:
        c = _key("C")
        b = _key("B")
        a = _key("A")
        reg = _make_registry({
            c: _factory(c),
            b: _factory(b, [c]),
            a: _factory(a, [b]),
        })
        layers = compute_topological_layers(reg, a, {})
        assert len(layers) == 3
        keys_per_layer = [
            {k for k, _f in layer} for layer in layers
        ]
        assert keys_per_layer[0] == {c}
        assert keys_per_layer[1] == {b}
        assert keys_per_layer[2] == {a}


class TestDiamond:
    """Root -> A, B -> Leaf."""

    def test_layers(self) -> None:
        leaf = _key("Leaf")
        a = _key("A")
        b = _key("B")
        root = _key("Root")
        reg = _make_registry({
            leaf: _factory(leaf),
            a: _factory(a, [leaf]),
            b: _factory(b, [leaf]),
            root: _factory(root, [a, b]),
        })
        layers = compute_topological_layers(reg, root, {})
        assert len(layers) == 3
        keys_per_layer = [
            {k for k, _f in layer} for layer in layers
        ]
        assert keys_per_layer[0] == {leaf}
        assert keys_per_layer[1] == {a, b}
        assert keys_per_layer[2] == {root}


class TestCachedExclusion:
    """Dependencies already in cache are excluded."""

    def test_cached_dep_excluded(self) -> None:
        leaf = _key("Leaf")
        root = _key("Root")
        reg = _make_registry({
            leaf: _factory(leaf),
            root: _factory(root, [leaf]),
        })
        cache: dict[Any, object] = {
            leaf.as_compilation_key(): "cached_leaf",
        }
        layers = compute_topological_layers(reg, root, cache)
        assert len(layers) == 1
        keys = {k for k, _f in layers[0]}
        assert keys == {root}

    def test_all_cached(self) -> None:
        root = _key("Root")
        reg = _make_registry({
            root: _factory(root),
        })
        cache: dict[Any, object] = {
            root.as_compilation_key(): "cached",
        }
        layers = compute_topological_layers(reg, root, cache)
        assert layers == []


class TestSingleNode:
    """A single factory with no deps."""

    def test_single_layer(self) -> None:
        root = _key("Root")
        reg = _make_registry({
            root: _factory(root),
        })
        layers = compute_topological_layers(reg, root, {})
        assert len(layers) == 1
        assert len(layers[0]) == 1
        assert layers[0][0][0] == root
