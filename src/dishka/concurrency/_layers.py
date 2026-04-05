from __future__ import annotations

from collections import deque
from collections.abc import Set
from typing import Any

from dishka.dependency_source import Factory
from dishka.entities.key import DependencyKey
from dishka.registry import Registry


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
    in-scope dependencies, layer 1 depends only on layer 0, etc.
    Each layer is a list of (DependencyKey, Factory) pairs whose
    factories are independent and can be dispatched concurrently.
    """
    # --- discover the sub-DAG reachable from root_key -----------
    factories: dict[DependencyKey, Factory] = {}
    # edges: key -> set of same-scope dependency keys
    edges: dict[DependencyKey, list[DependencyKey]] = {}
    queue: deque[DependencyKey] = deque()

    def _enqueue(key: DependencyKey) -> None:
        if key in factories:
            return
        comp_key = key.as_compilation_key()
        if comp_key in cache:
            return
        factory = registry.get_factory(key)
        if factory is None:
            # cross-scope or context var — not our problem
            return
        if factory.scope != registry.scope:
            return
        factories[key] = factory
        deps: list[DependencyKey] = []
        for dep in factory.dependencies:
            dep_comp = dep.as_compilation_key()
            if dep_comp not in cache:
                dep_factory = registry.get_factory(dep)
                if (
                    dep_factory is not None
                    and dep_factory.scope == registry.scope
                ):
                    deps.append(dep)
        for dep in factory.kw_dependencies.values():
            dep_comp = dep.as_compilation_key()
            if dep_comp not in cache:
                dep_factory = registry.get_factory(dep)
                if (
                    dep_factory is not None
                    and dep_factory.scope == registry.scope
                ):
                    deps.append(dep)
        edges[key] = deps
        for dep in deps:
            queue.append(dep)

    _enqueue(root_key)
    while queue:
        _enqueue(queue.popleft())

    if not factories:
        return []

    # --- Kahn's algorithm: peel zero-in-degree nodes as layers --
    in_degree: dict[DependencyKey, int] = {
        k: 0 for k in factories
    }
    for key, deps in edges.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[key] += 1

    remaining: Set[DependencyKey] = set(factories)
    layers: list[list[tuple[DependencyKey, Factory]]] = []

    while remaining:
        layer_keys = [
            k for k in remaining if in_degree[k] == 0
        ]
        if not layer_keys:
            break  # cycle — should not happen in valid graph
        layer = [
            (k, factories[k]) for k in layer_keys
        ]
        layers.append(layer)
        for k in layer_keys:
            remaining.discard(k)
            # decrement in-degree for dependents
            for other in remaining:
                if k in edges.get(other, ()):
                    in_degree[other] -= 1

    return layers
