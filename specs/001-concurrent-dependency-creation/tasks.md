# Tasks: Concurrent Dependency Creation

**Input**: Design documents from `/specs/001-concurrent-dependency-creation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/concurrency_api.md

**Tests**: Tests are REQUIRED per constitution principle III (Test-First, NON-NEGOTIABLE) and SC-007. All user stories have explicit acceptance scenarios with synchronization-based verification.

**Organization**: Tasks grouped by user story (P1–P6) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create directory structure and foundational type definitions

- [ ] T001 Create concurrency package directory at src/dishka/concurrency/__init__.py
- [ ] T002 [P] Create entities/concurrency.py with AsyncConcurrencyStrategy and SyncConcurrencyStrategy protocols, ExecutorTag type, and re-exports in src/dishka/entities/concurrency.py
- [ ] T003 [P] Create test directory at tests/unit/container/test_concurrency/__init__.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on — topological layer computation, Factory/provider extensions, container wiring, and public re-exports

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Add `executor: str | None = None` field to Factory dataclass in src/dishka/dependency_source/factory.py
- [ ] T005 Add `executor` kwarg to `@provide` decorator and propagate to Factory in src/dishka/provider/make_factory.py
- [ ] T006 Implement `compute_topological_layers()` function (BFS + Kahn's algorithm) — new internal module or within graph_builder. Input: registry, root_key, cache, scope. Output: list of layers (each layer = list of (DependencyKey, Factory) pairs). Exclude cached and cross-scope keys. Place in src/dishka/concurrency/_layers.py
- [ ] T007 Add `concurrency` kwarg to `make_async_container()` in src/dishka/async_container.py — store strategy on AsyncContainer, propagate to child scopes
- [ ] T008 Add `concurrency` kwarg to `make_container()` in src/dishka/container.py — store strategy on Container, propagate to child scopes
- [ ] T009 Add new public symbols to src/dishka/__init__.py: AsyncConcurrencyStrategy, SyncConcurrencyStrategy, AsyncioStrategy, AsyncioSemaphoreStrategy, TrioStrategy, ThreadPoolStrategy, ProcessPoolStrategy
- [ ] T010 Write unit test for `compute_topological_layers()` covering: linear chain, diamond, already-cached exclusion, single-node graph in tests/unit/container/test_concurrency/test_layers.py

**Checkpoint**: Foundation ready — topological layers computed correctly, Factory carries executor tag, container accepts concurrency kwarg

---

## Phase 3: User Story 1 — Async Concurrent Resolution (Priority: P1) 🎯 MVP

**Goal**: Independent async factories dispatched concurrently via `AsyncioStrategy` using `asyncio.TaskGroup`

**Independent Test**: Two async factories with no shared dependency, barrier proving overlapping execution, diamond deduplication

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T011 [P] [US1] Test concurrent execution of two independent async factories using asyncio barrier/event in tests/unit/container/test_concurrency/test_asyncio.py — covers acceptance scenario 1
- [ ] T012 [P] [US1] Test diamond deduplication: Root → A, B → Leaf; verify Leaf created once, A and B concurrent in tests/unit/container/test_concurrency/test_diamond.py — covers acceptance scenario 2
- [ ] T013 [P] [US1] Test sequential behavior when concurrency is not configured (no regression) in tests/unit/container/test_concurrency/test_asyncio.py — covers acceptance scenario 3
- [ ] T014 [P] [US1] Test error propagation: factory raises, no further factories started, no background tasks remain in tests/unit/container/test_concurrency/test_asyncio.py — covers acceptance scenario 4
- [ ] T015 [P] [US1] Test cancellation safety: parent task cancelled during get(), all in-progress factories cancelled in tests/unit/container/test_concurrency/test_asyncio.py — covers acceptance scenario 5
- [ ] T016 [P] [US1] Test async generator factories: yield value, register cleanup, finalize on scope exit in tests/unit/container/test_concurrency/test_asyncio.py — covers acceptance scenario 6

### Implementation for User Story 1

- [ ] T017 [US1] Implement `AsyncioStrategy` with `run()` method using `asyncio.TaskGroup` in src/dishka/concurrency/_asyncio.py — unwrap single-exception ExceptionGroups to preserve original error type
- [ ] T018 [US1] Integrate concurrent resolution path into `AsyncContainer._get_unlocked()` in src/dishka/async_container.py — when `_concurrency` is set: compute layers, dispatch each layer via strategy.run(), write results to cache, register generators in _exits
- [ ] T019 [US1] Handle edge case: single-factory layers skip strategy (direct call, no overhead) in the concurrent resolution path in src/dishka/async_container.py

**Checkpoint**: Async concurrent resolution works end-to-end with asyncio. Diamond dedup, error propagation, cancellation, and generator cleanup all verified.

---

## Phase 4: User Story 2 — asyncio Semaphore Limiting (Priority: P2)

**Goal**: Bound concurrent factory execution with `AsyncioSemaphoreStrategy(max_concurrent=N)`

**Independent Test**: N+2 independent factories, verify at most N run simultaneously using counter + lock

### Tests for User Story 2

- [ ] T020 [P] [US2] Test semaphore limiting: configure limit N, provide N+2 factories, verify at most N concurrent via counter/lock in tests/unit/container/test_concurrency/test_semaphore.py — covers acceptance scenario 1
- [ ] T021 [P] [US2] Test no throttling when no limit configured (AsyncioStrategy) in tests/unit/container/test_concurrency/test_semaphore.py — covers acceptance scenario 2

### Implementation for User Story 2

- [ ] T022 [US2] Implement `AsyncioSemaphoreStrategy` with `run()` method wrapping each task with `asyncio.Semaphore` in src/dishka/concurrency/_asyncio.py

**Checkpoint**: Semaphore-bounded concurrency works. At most N factories run simultaneously.

---

## Phase 5: User Story 3 — Sync Container with Thread Pool (Priority: P3)

**Goal**: Sync container dispatches independent factories to a thread pool

**Independent Test**: Two independent sync factories with threading barrier proving overlapping execution

### Tests for User Story 3

- [ ] T023 [P] [US3] Test thread pool concurrent execution with barrier-based overlap proof in tests/unit/container/test_concurrency/test_sync.py — covers acceptance scenario 1
- [ ] T024 [P] [US3] Test process pool: plain factories in pool, generator factories sequential in calling process in tests/unit/container/test_concurrency/test_sync.py — covers acceptance scenario 2
- [ ] T025 [P] [US3] Test thread pool error propagation: factory raises, no threads left running in tests/unit/container/test_concurrency/test_sync.py — covers acceptance scenario 3
- [ ] T026 [P] [US3] Test sequential behavior without executor configured (no regression) in tests/unit/container/test_concurrency/test_sync.py — covers acceptance scenario 4

### Implementation for User Story 3

- [ ] T027 [US3] Implement `ThreadPoolStrategy` with `run()` method using `concurrent.futures.ThreadPoolExecutor` in src/dishka/concurrency/_sync.py
- [ ] T028 [US3] Implement `ProcessPoolStrategy` with `run()` method using `concurrent.futures.ProcessPoolExecutor` in src/dishka/concurrency/_sync.py — partition generators to run locally, plain factories to pool
- [ ] T029 [US3] Integrate concurrent resolution path into `Container._get_unlocked()` in src/dishka/container.py — when `_concurrency` is set: compute layers, dispatch via strategy.run(), write results to cache, register generators in _exits

**Checkpoint**: Sync concurrent resolution works with both thread pool and process pool. Generator synchronization points verified.

---

## Phase 6: User Story 4 — trio Support (Priority: P4)

**Goal**: Concurrent dependency creation under trio using trio nurseries, no anyio dependency

**Independent Test**: Async container under trio with concurrency enabled, diamond and error scenarios using trio primitives

### Tests for User Story 4

- [ ] T030 [P] [US4] Test trio concurrent execution with independent factories using trio event/barrier in tests/unit/container/test_concurrency/test_trio.py — covers acceptance scenario 1
- [ ] T031 [P] [US4] Test trio error propagation: factory raises, cancellation via trio semantics, no tasks remain in tests/unit/container/test_concurrency/test_trio.py — covers acceptance scenario 2

### Implementation for User Story 4

- [ ] T032 [US4] Implement `TrioStrategy` with `run()` method using `trio.open_nursery()` in src/dishka/concurrency/_trio.py — wrapper coroutines collect results into dict by index

**Checkpoint**: trio concurrent resolution works. Error propagation and cancellation verified via trio semantics.

---

## Phase 7: User Story 5 — Per-Factory Executor Dispatching (Priority: P5)

**Goal**: Tag factories with `@provide(executor="tag")` and route to specific executors within a strategy

**Independent Test**: Strategy that tracks dispatch targets, factories with different tags, verify each routed correctly

### Tests for User Story 5

- [ ] T033 [P] [US5] Test tag-based dispatch: two factories with different executor tags routed to matching executors in tests/unit/container/test_concurrency/test_dispatch.py — covers acceptance scenario 1
- [ ] T034 [P] [US5] Test default dispatch: factory with no executor tag uses strategy default in tests/unit/container/test_concurrency/test_dispatch.py — covers acceptance scenario 2
- [ ] T035 [P] [US5] Test non-dispatch strategy: executor tags ignored, no error in tests/unit/container/test_concurrency/test_dispatch.py — covers acceptance scenario 3
- [ ] T036 [P] [US5] Test precedence: explicit tag wins over strategy-level DependencyKey routing in tests/unit/container/test_concurrency/test_dispatch.py — covers acceptance scenario 4

### Implementation for User Story 5

- [ ] T037 [US5] Extend strategy `run()` signatures to pass executor tag (or Factory metadata) alongside DependencyKey and callable in the concurrent resolution path in src/dishka/async_container.py and src/dishka/container.py
- [ ] T038 [US5] Implement per-factory dispatch logic in `AsyncioStrategy.run()` and `AsyncioSemaphoreStrategy.run()` in src/dishka/concurrency/_asyncio.py — route based on Factory.executor tag
- [ ] T039 [P] [US5] Implement per-factory dispatch logic in `TrioStrategy.run()` in src/dishka/concurrency/_trio.py
- [ ] T040 [P] [US5] Implement per-factory dispatch logic in `ThreadPoolStrategy.run()` and `ProcessPoolStrategy.run()` in src/dishka/concurrency/_sync.py

**Checkpoint**: Per-factory executor dispatching works across all built-in strategies. Tag-based and default routing verified.

---

## Phase 8: User Story 6 — Code Generation for Concurrent Resolution (Priority: P6)

**Goal**: Built-in strategies emit optimized code at container creation time via `compile()`, eliminating runtime dispatch overhead

**Independent Test**: Compare resolution results (values, ordering, errors) between `run()` and `compile()` paths across multiple graph shapes

### Tests for User Story 6

- [ ] T041 [P] [US6] Test codegen/runtime parity for AsyncioStrategy: same results, ordering, error behavior in tests/unit/container/test_concurrency/test_codegen.py — covers acceptance scenarios 1, 3
- [ ] T042 [P] [US6] Test fallback: strategy without compile() uses run() at resolution time, no error in tests/unit/container/test_concurrency/test_codegen.py — covers acceptance scenarios 2, 6
- [ ] T043 [P] [US6] Test codegen/runtime parity for TrioStrategy in tests/unit/container/test_concurrency/test_codegen.py — covers acceptance scenario 4
- [ ] T044 [P] [US6] Test codegen/runtime parity for ThreadPoolStrategy in tests/unit/container/test_concurrency/test_codegen.py — covers acceptance scenario 5
- [ ] T045 [P] [US6] Test codegen diamond deduplication: compiled code runs each factory exactly once in tests/unit/container/test_concurrency/test_codegen.py — covers acceptance scenario 7

### Implementation for User Story 6

- [ ] T046 [US6] Implement `compile()` on `AsyncioStrategy` — emit `async with TaskGroup()` + `create_task()` code into CodeBuilder in src/dishka/concurrency/_asyncio.py
- [ ] T047 [US6] Implement `compile()` on `AsyncioSemaphoreStrategy` — emit `TaskGroup` + `Semaphore` acquire/release in src/dishka/concurrency/_asyncio.py
- [ ] T048 [P] [US6] Implement `compile()` on `TrioStrategy` — emit `async with trio.open_nursery()` + wrapper coroutines in src/dishka/concurrency/_trio.py
- [ ] T049 [P] [US6] Implement `compile()` on `ThreadPoolStrategy` — emit `executor.submit()` + result collection in src/dishka/concurrency/_sync.py
- [ ] T050 [P] [US6] Implement `compile()` on `ProcessPoolStrategy` — emit `executor.submit()` for plain factories + sequential for generators in src/dishka/concurrency/_sync.py
- [ ] T051 [US6] Integrate compile() hook into factory compilation pipeline: detect `hasattr(strategy, 'compile')` at container creation time, call `strategy.compile(builder, callables)` for concurrent layers, else emit runtime `strategy.run()` calls — modify src/dishka/code_tools/factory_compiler.py and src/dishka/registry.py
- [ ] T052 [US6] Ensure single-factory layers emit direct calls (no strategy involvement) in the codegen path in src/dishka/code_tools/factory_compiler.py

**Checkpoint**: All built-in strategies have compile() implementations. Codegen/runtime parity verified. Fallback for custom strategies works.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, edge cases, and cleanup

- [ ] T053 [P] Test edge case: all dependencies cached — falls through without task overhead in tests/unit/container/test_concurrency/test_asyncio.py
- [ ] T054 [P] Test edge case: single independent factory — no unnecessary strategy involvement in tests/unit/container/test_concurrency/test_asyncio.py
- [ ] T055 [P] Test edge case: generator factory raises during setup (before yield) — cleanup must not finalize in tests/unit/container/test_concurrency/test_asyncio.py
- [ ] T056 [P] Test edge case: strategy.run() itself raises (strategy bug) — propagates as-is in tests/unit/container/test_concurrency/test_asyncio.py
- [ ] T057 [P] Test edge case: unrecognized executor tag — built-in strategy raises clear error in tests/unit/container/test_concurrency/test_dispatch.py
- [ ] T058 Run `ruff check src/dishka/concurrency/ src/dishka/entities/concurrency.py` and `ruff format` — fix any lint issues
- [ ] T059 Run `mypy src/dishka/concurrency/ src/dishka/entities/concurrency.py` — fix any type errors
- [ ] T060 Run full test suite: `pytest tests/unit` — verify no regressions (SC-003)
- [ ] T061 Run quickstart.md validation: create a test script from quickstart.md examples, verify they work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phase 3–8)**: All depend on Phase 2 completion
  - US1 (P1): No dependencies on other stories
  - US2 (P2): Depends on US1 (extends AsyncioStrategy)
  - US3 (P3): No dependency on US1/US2 (sync path is independent)
  - US4 (P4): No dependency on US1/US2/US3 (trio path is independent)
  - US5 (P5): Depends on US1, US3, US4 (extends all strategies with dispatch)
  - US6 (P6): Depends on US1, US2, US3, US4, US5 (codegen for all strategies)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Foundation only — **MVP scope**
- **US2 (P2)**: US1 (AsyncioSemaphoreStrategy extends AsyncioStrategy patterns)
- **US3 (P3)**: Foundation only (independent sync path) — can parallel with US1/US2
- **US4 (P4)**: Foundation only (independent trio path) — can parallel with US1/US2/US3
- **US5 (P5)**: US1 + US3 + US4 (dispatch extends all strategies)
- **US6 (P6)**: US1 + US2 + US3 + US4 + US5 (codegen for all strategies that now have dispatch)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Foundation types before strategy implementations
- Strategy run() before container integration
- Core implementation before edge cases

### Parallel Opportunities

- Phase 1: T002 and T003 can run in parallel
- Phase 2: T004 and T005 can run in parallel, T007 and T008 can run in parallel
- Phase 3: All tests (T011–T016) can run in parallel; implementation is sequential
- Phase 4: US3 can run in parallel with US1/US2 (different files, independent path)
- Phase 5: US4 can run in parallel with US1/US2/US3 (different files, independent path)
- Phase 7: T038/T039/T040 can partially parallel (different strategy files)
- Phase 8: T046/T047 sequential (same file), T048/T049/T050 can parallel (different files)
- Phase 9: All edge case tests can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests together (they should all fail initially):
Task: "Test concurrent execution in tests/unit/container/test_concurrency/test_asyncio.py"
Task: "Test diamond deduplication in tests/unit/container/test_concurrency/test_diamond.py"
Task: "Test error propagation in tests/unit/container/test_concurrency/test_asyncio.py"
Task: "Test cancellation safety in tests/unit/container/test_concurrency/test_asyncio.py"
Task: "Test generator factories in tests/unit/container/test_concurrency/test_asyncio.py"
```

## Parallel Example: Independent Story Streams

```bash
# After Foundation is complete, these can run concurrently:
Stream A: US1 (async/asyncio) → US2 (semaphore) → US5 (dispatch) → US6 (codegen)
Stream B: US3 (sync thread/process pool) — independent of Stream A
Stream C: US4 (trio) — independent of Stream A and B
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (AsyncioStrategy + concurrent resolution)
4. **STOP and VALIDATE**: All US1 tests pass, no regressions in existing tests
5. Working async concurrent resolution — demo-ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → Async concurrency works → MVP!
3. US2 → Semaphore limiting → Production-ready async
4. US3 → Sync concurrency → Full sync/async parity
5. US4 → Trio support → Framework coverage complete
6. US5 → Per-factory dispatch → Fine-grained control
7. US6 → Codegen → Performance-optimized
8. Polish → Edge cases, lint, types, full validation

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (asyncio) → US2 (semaphore)
   - Developer B: US3 (sync pools)
   - Developer C: US4 (trio)
3. After streams converge: US5 (dispatch) → US6 (codegen) → Polish

---

## Notes

- [P] tasks = different files, no dependencies on in-progress tasks
- [Story] label maps task to specific user story for traceability
- Tests use synchronization primitives (events, barriers, semaphores) — NO wall-clock assertions (FR-015)
- Line length: 79 characters (ruff enforced)
- mypy strict on all new code
- Python 3.11+ for asyncio.TaskGroup; 3.10 remains project minimum (RuntimeError at construction on < 3.11)
- No anyio dependency — separate asyncio and trio code paths
