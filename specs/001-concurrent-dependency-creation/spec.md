# Feature Specification: Concurrent Dependency Creation

**Feature Branch**: `001-concurrent-dependency-creation`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "currently dishka dependencies are created sequentially. We want to support concurrent creation of dependencies..."

## Clarifications

### Session 2026-04-05

- Q: What is the canonical name for the concurrency configuration abstraction? → A: `ConcurrencyStrategy` (fits compound-noun naming style of the codebase; avoids confusion with `concurrent.futures.Executor`)
- Q: How is `ConcurrencyStrategy` passed to the container? → A: Dedicated `concurrency=` keyword argument on `make_container()` / `make_async_container()`
- Q: How should process pool strategy handle generator factories (which cannot be pickled)? → A: Generators always run in the calling process sequentially; they act as synchronization points — independent plain factories on either side of a generator boundary can still be parallelized in the pool
- Q: Does the `ConcurrencyStrategy` propagate to child scope containers (e.g. `async with container() as child`)? → A: Yes — auto-propagate; child scope inherits the same strategy (no reason to want different behaviour per scope)
- Q: Should code generation (emitting `asyncio.gather` etc. into compiled factory functions, as in FRidh:feat/async-concurrent-resolution-a and FRidh:feat/async-concurrent-resolution-b) be used as the concurrency mechanism? → A: Not for phase 1 — deferred in favour of a runtime `ConcurrencyStrategy` object. The runtime approach is simpler to implement and validate first. Codegen is feasible for all built-in strategies (asyncio, trio, thread pool) and can be added in a future phase behind the same protocol via an optional `compile()` hook (see later clarifications).
- Q: What should happen if `ConcurrencyStrategy.run()` itself raises (strategy bug, not a factory error)? → A: Propagate as-is — consistent with how the codebase handles exceptions from all other user-provided objects (factories, generators); no special wrapping.
- Q: Should the `ConcurrencyStrategy` protocol include `DependencyKey` alongside each factory callable from day one? → A: Yes — include `DependencyKey` in the protocol signature from the start so per-factory dispatch can be added to custom or built-in strategies later without a breaking change; built-in strategies ignore the key initially
- Q: What mechanism should handle diamond deduplication (ensuring each factory runs at most once)? → A: Topological sort — resolve the dependency graph layer by layer (leaves first); shared dependencies are always fully resolved before any consumer is dispatched, so duplicate factory calls cannot arise. No `_Pending` sentinel or per-key locking needed. The strategy only ever receives genuinely independent factories within each layer.
- Q: Should code generation for concurrency (e.g. emitting `asyncio.gather` into compiled factories) be reclassified from "rejected" to "deferred optimization"? → A: Yes — reclassified as deferred optimization. Code generation is out of scope for phase 1 but the `ConcurrencyStrategy` interface does not preclude it; a future codegen optimization would be an internal implementation detail behind the same protocol, requiring no interface changes. Custom strategies remain unaffected.
- Q: Is the phase 1 `ConcurrencyStrategy` protocol (with only `run()`) forward-compatible with a future optional `compile()` codegen hook? → A: Yes — phase 1 ships `run()` only. A future phase can add an optional `compile(builder, callables)` method (checked via `hasattr` or a separate mixin) that lets any strategy — built-in or custom — emit optimized code into the `CodeBuilder` at container creation time. Strategies without `compile()` fall back to runtime `strategy.run()` dispatch. This requires no breaking changes to the phase 1 protocol. Codegen applies equally to all built-in strategies (asyncio, trio, thread pool) since the `CodeBuilder` already supports the necessary constructs.
- Q: What is the implementation priority order? → A: Priority 1: async concurrency (asyncio), Priority 2: semaphore limiting, Priority 3: trio support, Priority 4: sync concurrency (thread/process pool), Priority 5: code generation with optional `compile()` hook.
- Q: Should Python version requirements vary per priority (e.g. 3.10+ for trio/sync)? → A: No — blanket 3.11+ (FR-014) applies to all priorities.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Async Concurrent Resolution (Priority: P1)

A developer uses the async container and wants multiple independent async dependencies to be created concurrently rather than one after another. They opt in by passing an executor configuration at container creation time.

**Why this priority**: Async concurrency is the primary stated goal, delivers the most value for I/O-bound dependencies, and is the foundation for all other async improvements.

**Independent Test**: Can be fully tested by creating a container with two async factories that have no dependency on each other, enabling concurrency, and verifying both are started before either completes (using synchronization primitives like events/barriers).

**Acceptance Scenarios**:

1. **Given** an async container with concurrency enabled and two factories `A` and `B` that have no dependency relationship, **When** `container.get(TypeThatDependsOnAandB)` is called, **Then** both `A` and `B` are created concurrently (provable via threading/async events showing overlapping execution).
2. **Given** an async container with concurrency enabled and factories forming a diamond: `Root → A → Leaf` and `Root → B → Leaf`, **When** `container.get(Root)` is called, **Then** `Leaf` is created exactly once (not twice), and `A` and `B` are created concurrently after `Leaf`.
3. **Given** an async container without concurrency enabled, **When** `container.get(SomeType)` is called, **Then** behavior is identical to current sequential behavior.
4. **Given** an async container with concurrency enabled and a factory that raises an exception, **When** `container.get(SomeType)` is called, **Then** the error propagates, no further factories are started, and no background tasks remain after the call returns.
5. **Given** an async container with concurrency enabled and a parent task that is cancelled during `container.get()`, **When** cancellation occurs, **Then** all in-progress factories are cancelled, no background tasks remain, and cancellation propagates cleanly.
6. **Given** an async container with concurrency enabled and async generator factories, **When** `container.get(SomeType)` is called successfully, **Then** all generators yield their value, are registered for cleanup, and finalization runs correctly on scope exit.

---

### User Story 2 - asyncio Semaphore Limiting (Priority: P2)

A developer wants to limit the number of concurrently created dependencies to avoid overwhelming external resources (e.g., database connection pool during startup). They configure a semaphore limit when enabling concurrency.

**Why this priority**: Unlimited concurrency can exhaust resources. Bounded concurrency is a common and important production requirement.

**Independent Test**: Can be tested by configuring a semaphore with limit N, providing N+2 independent factories, and verifying that at most N run simultaneously using a counter protected by a lock/event.

**Acceptance Scenarios**:

1. **Given** an async container configured with a concurrency limit of N (asyncio semaphore), **When** more than N independent dependencies need creation, **Then** at most N factories execute simultaneously at any given time.
2. **Given** an async container configured with no concurrency limit, **When** many independent dependencies need creation, **Then** all eligible factories are started without throttling.

---

### User Story 3 - Sync Container with Thread Pool (Priority: P3)

A developer uses the sync container with blocking factories (e.g., reading config from disk, initializing a database connection) and wants these to run in parallel using a thread pool executor.

**Why this priority**: Sync concurrency requires explicit thread pool opt-in. It is secondary to async but important for completeness and symmetric API design.

**Independent Test**: Can be tested by providing two independent sync factories that use a threading barrier to prove overlapping execution, running with a thread pool executor, and verifying both complete.

**Acceptance Scenarios**:

1. **Given** a sync container with a thread pool executor configured, **When** `container.get(TypeThatDependsOnAandB)` is called and `A` and `B` have no dependency relationship, **Then** both factories run concurrently in threads.
2. **Given** a sync container with a process pool executor configured, **When** `container.get(SomeType)` is called, **Then** independent plain factories run in separate processes; generator factories run sequentially in the calling process and act as synchronization points in the resolution graph — independent plain factories before and after a generator boundary can still be parallelized.
3. **Given** a sync container with thread pool concurrency and a factory that raises an exception, **When** `container.get(SomeType)` is called, **Then** the error propagates, no threads are left running, and the call returns cleanly.
4. **Given** a sync container without any executor configured, **When** `container.get(SomeType)` is called, **Then** behavior is identical to current sequential behavior.

---

### User Story 4 - trio Support (Priority: P4)

A developer uses trio as their async framework and wants concurrent dependency creation without anyio. The same concurrency opt-in API works with trio's nursery-based task group.

**Why this priority**: trio is explicitly required; anyio is explicitly forbidden. Separate implementation from asyncio task groups ensures framework compatibility.

**Independent Test**: Can be tested by running the async container under trio with concurrency enabled and verifying the same diamond and error scenarios pass using trio primitives.

**Acceptance Scenarios**:

1. **Given** an async container with concurrency enabled running under trio, **When** `container.get(SomeType)` is called with independent factories, **Then** factories run concurrently using trio's task nursery.
2. **Given** an async container with concurrency enabled running under trio and a factory that raises, **When** `container.get(SomeType)` is called, **Then** the error propagates via trio's cancellation semantics and no tasks remain.

---

### Edge Cases

- What happens when all dependencies of a type are already cached? (Should fall through to sequential path with no task overhead.)
- What happens when a diamond dependency is being concurrently resolved by two paths at the same time? (Exactly one factory call must win; the other must wait and reuse the cached result.)
- What happens if a generator factory raises during setup (before `yield`)? (Cleanup must not attempt to finalize a generator that never yielded.)
- What happens when concurrency is enabled but there is only one independent factory? (Should degrade gracefully without unnecessary task overhead.)
- What happens when a factory's dependency itself requires concurrent sub-resolution? (Recursion must not deadlock.)
- What happens with a process pool strategy when a generator factory sits between two groups of independent plain factories? (Generator resolves in the calling process first; the downstream plain factories can then be dispatched to the pool.)
- What happens on scope exit when cleanup generators raise? (All other cleanups must still run; errors must be collected or re-raised.)
- What happens if `ConcurrencyStrategy.run()` itself raises (strategy bug, not a factory error)? (The exception propagates as-is to the `container.get()` caller — no special wrapping, consistent with how all other user-provided object errors are handled.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The container MUST support an explicit opt-in `ConcurrencyStrategy` passed as a `concurrency=` keyword argument to `make_container()` / `make_async_container()`; sequential behavior is the default when the argument is omitted.
- **FR-002**: When concurrency is enabled, the system MUST resolve the dependency graph in topological order — layer by layer, leaves first. Within each layer, all factories are independent (no dependency between them) and MUST be dispatched concurrently via the `ConcurrencyStrategy`. The next layer is dispatched only after all factories in the current layer have completed.
- **FR-003**: The system MUST guarantee that each factory is called at most once per scope per dependency key. Topological ordering is the primary mechanism: shared dependencies (diamond nodes) are always fully resolved in an earlier layer before any consumer layer is dispatched, making duplicate factory calls structurally impossible.
- **FR-004**: The system MUST propagate factory errors immediately: when any factory fails during a concurrent `get()` call, no new factories may be started and the call must raise the error after all in-progress work has settled.
- **FR-005**: The system MUST ensure that after `container.get()` returns (whether successfully or with an error), no background tasks, threads, or coroutines started during that call remain running.
- **FR-006**: The system MUST support both factory and generator dependency sources with concurrent execution; generators must yield exactly once and be registered for cleanup correctly.
- **FR-007**: For async containers, the system MUST support asyncio natively using `asyncio.TaskGroup` (Python 3.11+).
- **FR-008**: For async containers, the system MUST support trio natively using trio's nursery/task group, without depending on anyio.
- **FR-009**: For sync containers, the system MUST support thread pool executors (`concurrent.futures.ThreadPoolExecutor`) as the concurrency mechanism.
- **FR-010**: For sync containers, the system MUST support process pool executors (`concurrent.futures.ProcessPoolExecutor`) as the concurrency mechanism. Generator factories MUST always run in the calling process (sequentially); only plain factories are dispatched to the pool. Generator factories act as synchronization points: independent plain factories on either side of a generator boundary may still be parallelized.
- **FR-011**: For async containers using asyncio, the system MUST support an optional semaphore to bound the number of concurrently executing factories.
- **FR-012**: The system MUST handle parent task cancellation (asyncio) and nursery cancellation (trio) gracefully: all in-progress work must be cancelled and no tasks must remain.
- **FR-013**: The `ConcurrencyStrategy` protocol MUST include the `DependencyKey` alongside each factory callable in its interface from the initial implementation, so that per-factory dispatch logic can be added to custom or built-in strategies in the future without a breaking API change. Built-in strategies MAY ignore the key initially; per-factory dispatch behavior in built-in strategies is deferred to a future iteration.
- **FR-014**: The feature MUST be compatible with Python 3.11 and above; use of `asyncio.TaskGroup` and related APIs is acceptable.
- **FR-015**: Tests MUST verify concurrent behavior using synchronization primitives (events, barriers, semaphores), not by measuring wall-clock time.

### Key Entities

- **ConcurrencyStrategy**: A user-provided object passed as a dedicated `concurrency=` keyword argument to `make_container()` / `make_async_container()` that controls whether and how concurrency is applied. Two separate protocols exist: `AsyncConcurrencyStrategy` (for async containers) and `SyncConcurrencyStrategy` (for sync containers), each exposing a single `run` method that receives a sequence of `(DependencyKey, factory_callable)` pairs and returns their results. Built-in implementations: `AsyncioStrategy` (unlimited `asyncio.gather`), `AsyncioSemaphoreStrategy(n)` (semaphore-bounded), `TrioStrategy` (trio nursery), `ThreadPoolStrategy(executor)`, `ProcessPoolStrategy(executor)`. Users may provide custom implementations of either protocol.
- **Resolution DAG**: During a `container.get()` call, the set of required factories forms a directed acyclic graph. The graph is resolved in topological order — each layer contains factories whose dependencies are all satisfied by previously resolved layers. Factories within the same layer are independent and dispatched concurrently by the `ConcurrencyStrategy`.
- **Topological Layer**: A set of factories within the resolution DAG whose dependencies are all fully resolved. All factories in a layer are dispatched concurrently; the next layer begins only after all factories in the current layer complete. This structural ordering eliminates the need for runtime deduplication sentinels or per-key locks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When concurrency is enabled and N independent async factories each take T time, total resolution time is less than N×T (demonstrable via synchronization primitives showing overlap, not by asserting a specific wall-clock duration).
- **SC-002**: No factory is ever called more than once per scope per dependency key in any scenario, including concurrent diamond-shaped dependency graphs.
- **SC-003**: Sequential (non-concurrent) behavior is entirely unchanged: all existing tests pass without modification when no concurrency configuration is provided.
- **SC-004**: After any `container.get()` call completes—successfully or with an error—zero background tasks, threads, or coroutines started during that call remain active.
- **SC-005**: Error propagation is correct: a factory failure causes `container.get()` to raise an exception, and the exception is the original factory error (not a `CancelledError` or wrapper).
- **SC-006**: Cancellation is safe: cancelling the parent task or nursery during `container.get()` leaves the container in a consistent state with no leaked resources.
- **SC-007**: The feature ships with test coverage for: asyncio concurrent resolution, asyncio semaphore limiting, trio concurrent resolution, sync thread pool resolution, diamond deduplication, error propagation, and cancellation handling.

## Priorities

Implementation priority order. Each priority builds on the previous. The `ConcurrencyStrategy` protocol introduced in priority 1 (with `run()` only) is forward-compatible with all subsequent priorities — no breaking changes required.

| Priority | Scope | Key Deliverables |
|----------|-------|-----------------|
| **1** | Async concurrency (asyncio) | `ConcurrencyStrategy` protocol with `run()`, `AsyncioStrategy` using `asyncio.TaskGroup`, topological layer resolution, `concurrency=` kwarg on `make_async_container()`, error propagation, cancellation safety |
| **2** | Semaphore limiting | `AsyncioSemaphoreStrategy(n)` bounding concurrent factory execution |
| **3** | trio support | `TrioStrategy` using trio nurseries, separate code path (no anyio) |
| **4** | Sync concurrency | `SyncConcurrencyStrategy` protocol, `ThreadPoolStrategy`, `ProcessPoolStrategy` (generators sequential in calling process), `concurrency=` kwarg on `make_container()` |
| **5** | Code generation | Optional `compile(builder, callables)` method on strategy protocol; built-in codegen for asyncio (`TaskGroup`), trio (nursery + wrapper coroutines), thread pool (`executor.submit`); strategies without `compile()` fall back to runtime `run()` dispatch; no breaking interface changes |

## Assumptions

- Concurrency configuration is specified once at container creation time and applies uniformly to all factories in that container and all child scope containers entered via `with container() as child`. The `ConcurrencyStrategy` protocol is designed to support per-factory dispatch from day one (each factory is passed alongside its `DependencyKey`), but built-in strategies ignore the key initially; per-factory dispatch in built-in strategies is deferred to a future iteration. When per-factory dispatch is introduced, two complementary approaches are anticipated: (1) a decorator argument `@provide(executor=ExecutorType)` where the executor type is resolved from the DI graph as a regular dependency, and (2) a `ConcurrencyStrategy` implementation that uses the `DependencyKey` to route specific factories to specific executors at the app-wiring layer — useful when provider code should remain executor-agnostic (e.g. library providers).
- Concurrent finalization (cleanup of generators on scope exit) is considered out of scope for the initial implementation; finalization remains sequential.
- The feature targets Python 3.11+ and may use `asyncio.TaskGroup` and `ExceptionGroup`; no backport to earlier Python versions is required.
- anyio is explicitly excluded as a dependency due to its performance overhead; asyncio and trio are supported via separate code paths.
- The existing per-scope lock mechanism remains in place for cache protection; the new concurrency layer operates at the resolution planning level (topological layer fan-out), not by replacing the cache lock.
- The `ConcurrencyStrategy` abstraction is a protocol or abstract base that users can implement for custom behavior, with built-in implementations covering all described cases.
- Diamond deduplication is achieved structurally via topological ordering: shared dependencies are always resolved in an earlier layer than their consumers, making duplicate factory calls impossible. No `_Pending` sentinel or per-key in-flight registry is required. Coordination across concurrent `container.get()` calls on the same container remains handled by the existing cache lock.
- **Rejected alternative — `_Pending` sentinel**: The PoCs placed a sentinel object + future in the cache to deduplicate concurrent resolution paths. Rejected in favour of topological ordering, which is simpler, framework-agnostic (no asyncio-specific `Future` needed), and eliminates the dedup problem structurally rather than at runtime.
- Performance impact of the concurrency infrastructure on the sequential path is zero—no overhead is introduced when concurrency is not configured.
- **Deferred optimization — code generation**: Two PoCs (FRidh:feat/async-concurrent-resolution-a, FRidh:feat/async-concurrent-resolution-b) explored emitting `asyncio.gather` directly into compiled factory functions at container creation time. This is **deferred** (not used in phase 1) because the runtime `ConcurrencyStrategy` approach delivers the same functionality with negligible overhead (one virtual dispatch per `get()` call) and is simpler to implement and validate first. **Future phase**: codegen can be added for **all built-in strategies** (asyncio via `TaskGroup`, trio via nursery + result dict + wrapper coroutines, thread pool via executor submit) — the existing `CodeBuilder` already supports the necessary constructs (function definitions, `async with` blocks, dicts). The codegen complexity is comparable across strategies. An optional `compile(builder, callables)` method can be added to the `ConcurrencyStrategy` protocol without breaking the phase 1 interface: strategies without `compile()` fall back to runtime `strategy.run()` dispatch (checked via `hasattr` or a separate mixin). This allows both built-in and custom strategies to provide codegen optimizations. Phase 1's `run()`-only protocol is fully forward-compatible.
