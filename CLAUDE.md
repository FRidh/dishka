# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Testing:**
```bash
# Run unit tests only
pytest tests/unit

# Run a single test file
pytest tests/unit/test_container.py

# Run a specific test
pytest tests/unit/test_container.py::test_name

# Run all tests via nox (including integrations)
nox -s unit
nox -s integrations_base

# Run a specific framework integration
nox -s fastapi_latest
```

**Linting and type checking:**
```bash
ruff check src/
ruff format src/
mypy src/dishka
```

**Install dev dependencies:**
```bash
pip install -e ".[dev]"
# or with uv (preferred in CI)
uv sync
```

## Architecture

Dishka is a dependency injection (DI) framework for Python. The core idea: users define `Provider` classes with factory methods, combine them into a `Container`, and request dependencies by type.

**Core concepts:**
- **Scope**: Lifetime of a dependency. Built-in scopes: `APP → REQUEST → ACTION → STEP`. Dependencies can only depend on same-scope or broader-scope objects.
- **Provider**: A class with `@provide`-decorated factory methods. Each method returns a dependency. Generators are used for resources needing cleanup.
- **Container**: The DI runtime. Created via `make_container(*providers)`. Caches resolved dependencies per scope. Async variant: `make_async_container()`.
- **Component**: Isolated namespace for providers, allowing multiple independent dependency trees in one container.
- **DependencyKey**: A `(type, component)` tuple that uniquely identifies a dependency.

**Source layout:**
- `src/dishka/entities/` — Core data types: `Scope`, `DependencyKey`, `Component`, markers
- `src/dishka/provider/` — `Provider` class and decorator implementations (`@provide`, `@alias`, `@decorate`)
- `src/dishka/dependency_source/` — Internal representations of factory, alias, decorator, context var sources
- `src/dishka/graph_builder/` — Validates and builds the dependency graph at container creation time (catches missing/cyclic deps early)
- `src/dishka/container.py` / `async_container.py` — Sync and async container implementations
- `src/dishka/integrations/` — Framework-specific wiring (FastAPI, Flask, aiohttp, Aiogram, gRPC, Celery, etc.)
- `src/dishka/_adaptix/` — Vendored internal type introspection library; excluded from linting and mypy

**How resolution works:**
1. `make_container()` calls `graph_builder` to validate and index all providers
2. `container.get(SomeType)` looks up `DependencyKey(SomeType, DEFAULT_COMPONENT)`
3. If not cached for the current scope, the factory is called with its own dependencies resolved recursively
4. Scope context managers (`with container() as request_container`) enter/exit nested scopes and handle finalization

**Integrations pattern:** Each framework integration provides a setup function + middleware/decorator that:
1. Enters a new scope (usually `REQUEST`) on each request
2. Injects dependencies into handler function parameters (detected via `FromDishka` annotation or by type)
3. Exits the scope (triggering cleanup) after the request

## Code Style

- Line length: 79 characters (enforced by ruff)
- Strict mypy (excludes `integrations/` and `_adaptix/`)
- Custom ast-grep linter rules in `linter-rules/`
- No linting on `src/dishka/_adaptix/` (vendored code)

## Active Technologies
- Python 3.11+ (uses `asyncio.TaskGroup`, `ExceptionGroup`; project minimum remains 3.10 — concurrency feature raises at construction on < 3.11) + None new — stdlib only (`asyncio`, `concurrent.futures`, `contextvars`); `trio` optional for trio strategy (001-concurrent-dependency-creation)

## Recent Changes
- 001-concurrent-dependency-creation: Added concurrent dependency creation with runtime dispatch, codegen, per-factory executor routing, and built-in strategies for asyncio, trio, and thread/process pools
