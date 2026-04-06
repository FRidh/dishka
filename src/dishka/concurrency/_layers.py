from __future__ import annotations

from collections import deque
from typing import Any

from dishka.dependency_source import Factory
from dishka.entities.key import DependencyKey
from dishka.registry import Registry


def _collect_same_scope_deps(
    factory: Factory,
    registry: Registry,
    cache: dict[Any, object],
) -> list[DependencyKey]:
    """Collect same-scope, non-cached dependency keys."""
    deps: list[DependencyKey] = []
    for dep in factory.dependencies:
        if dep.as_compilation_key() in cache:
            continue
        dep_factory = registry.get_factory(dep)
        if dep_factory is not None and dep_factory.scope == registry.scope:
            deps.append(dep)
    for dep in factory.kw_dependencies.values():
        if dep.as_compilation_key() in cache:
            continue
        dep_factory = registry.get_factory(dep)
        if dep_factory is not None and dep_factory.scope == registry.scope:
            deps.append(dep)
    return deps


def _discover_subdag(
    registry: Registry,
    root_key: DependencyKey,
    cache: dict[Any, object],
) -> tuple[
    dict[DependencyKey, Factory],
    dict[DependencyKey, list[DependencyKey]],
]:
    """BFS from root_key to discover same-scope sub-DAG."""
    factories: dict[DependencyKey, Factory] = {}
    edges: dict[DependencyKey, list[DependencyKey]] = {}
    queue: deque[DependencyKey] = deque([root_key])

    while queue:
        key = queue.popleft()
        if key in factories:
            continue
        if key.as_compilation_key() in cache:
            continue
        factory = registry.get_factory(key)
        if factory is None:
            continue
        if factory.scope != registry.scope:
            continue
        factories[key] = factory
        deps = _collect_same_scope_deps(
            factory,
            registry,
            cache,
        )
        edges[key] = deps
        queue.extend(deps)

    return factories, edges


def _peel_layers(
    factories: dict[DependencyKey, Factory],
    edges: dict[DependencyKey, list[DependencyKey]],
) -> list[list[tuple[DependencyKey, Factory]]]:
    """Kahn's algorithm: peel zero-in-degree as layers."""
    in_degree: dict[DependencyKey, int] = dict.fromkeys(
        factories,
        0,
    )
    for key, deps in edges.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[key] += 1

    remaining = set(factories)
    layers: list[list[tuple[DependencyKey, Factory]]] = []

    while remaining:
        layer_keys = [k for k in remaining if in_degree[k] == 0]
        if not layer_keys:
            break
        layers.append([(k, factories[k]) for k in layer_keys])
        for k in layer_keys:
            remaining.discard(k)
            for other in remaining:
                if k in edges.get(other, ()):
                    in_degree[other] -= 1

    return layers


def compute_topological_layers(
    registry: Registry,
    root_key: DependencyKey,
    cache: dict[Any, object],
) -> list[list[tuple[DependencyKey, Factory]]]:
    """Compute topological layers for concurrent resolution.

    BFS from root_key through Registry.  Excludes keys already
    in *cache* and keys whose factory lives in a different scope
    (cross-scope deps are resolved via parent_getter and are
    assumed to be available).

    Returns layers ordered leaves-first: layer 0 has no
    in-scope dependencies, layer 1 depends only on layer 0,
    etc.  Each layer is a list of (DependencyKey, Factory)
    pairs whose factories are independent and can be
    dispatched concurrently.
    """
    factories, edges = _discover_subdag(
        registry,
        root_key,
        cache,
    )
    if not factories:
        return []
    return _peel_layers(factories, edges)
