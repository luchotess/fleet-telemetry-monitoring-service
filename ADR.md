# ADR: Fleet Telemetry Monitoring Service Architecture

## Architecture Review Questions

### 1. What Were The Most Important Decisions?

The three most important decisions were:

- **PostgreSQL over SQLite:** the system needs concurrent writes, atomic zone increments, row-level locking, and correct aggregate state. SQLite would be easier to run, but it would not exercise the concurrency and transaction semantics this challenge is meant to test.
- **Vehicle token handshake:** telemetry ingestion accepts authoritative vehicle events, so the backend needs a minimal identity boundary. The 1-hour JWT session binds telemetry to a known vehicle and prevents simple `vehicle_id` spoofing without introducing full production device identity.
- **Per-vehicle rate limiting over the 1 Hz window:** each vehicle is expected to send 10 events per 10 seconds. Allowing 15 requests per 10 seconds supports jitter and small bursts while still protecting the API from runaway clients.

### 2. What Requirements Were Unclear, And What Did We Assume?

The spec intentionally leaves several production boundaries open. The implementation makes these assumptions:

- **Observability:** no full metrics, tracing, alerting, or centralized logging stack is required for the take-home. Domain event logs, API responses, tests, and Docker logs provide enough visibility for evaluation.
- **Authentication:** vehicle authentication is useful for ingestion, so a lightweight handshake was added. Frontend user authentication is assumed out of scope because the dashboard is a local evaluator-facing tool.
- **Infrastructure stack:** no cloud services, managed queues, external brokers, Redis, or API gateways are assumed. Docker Compose is enough to make Postgres, backend, frontend, simulator, and tests reproducible.
- **Stale telemetry:** because stale telemetry is caused by missing events, it is evaluated during dashboard/API reads rather than by a scheduler or stream timeout.

### 3. What Changes If Scale Grows Significantly?

For this ADR, **significant scale** means moving from 50 vehicles at 1 Hz, or about 50 telemetry events per second, to thousands of vehicles, hundreds or thousands of sustained events per second, multiple backend replicas, or stronger durability requirements for asynchronous processing.

At that point, the architecture should change to:

- Put a queue or stream between ingestion and processing, such as Kafka, Kinesis, Redis Streams, RabbitMQ, or SQS.
- Partition processing by `vehicle_id` so per-vehicle ordering and fault transitions remain tractable.
- Add a transactional outbox so database commits and event publication cannot diverge.
- Replace process-local rate limiting with distributed rate limiting.
- Split current state from historical telemetry storage.
- Add materialized read models or Redis-backed aggregates for dashboard reads.
- Add dead-letter queues, retry policies, metrics, tracing, structured logs, and alerting.

### 4. What Was Deliberately Left Out?

The implementation deliberately leaves out:

- **Frontend authentication:** unnecessary for this project scope; production would use SSO/OIDC or a comparable user auth layer.
- **Full observability:** metrics, tracing, dashboards, alerting, and centralized logs are valuable production concerns but not needed to prove the telemetry workflow.
- **Kafka/external event architecture:** in-process domain events demonstrate boundaries; Kafka belongs to the future scale path.
- **Queue-based ingestion:** documented as the next scale step, but avoided to keep the implementation focused and runnable.
- **Production device identity:** mTLS, certificate rotation, and OAuth-style flows are out of scope for this vertical slice.

## Decisions

### Backend Framework

**Decision:** Use FastAPI for the backend REST API.

**Rationale:** FastAPI fits a validation-heavy API because it supports Python type hints, Pydantic models, generated OpenAPI docs, and async-capable request handling. This keeps the ingestion and dashboard endpoints compact while still production-minded.

**Alternatives considered:**

- Django REST Framework: mature and batteries-included, but heavier than needed for this vertical slice.
- Flask: simple, but requires more manual validation, OpenAPI, and async setup.

**Consequences:** The backend stays small and typed, with strong request validation and API documentation. The project still needs explicit transaction and dependency management.

### Database

**Decision:** Use PostgreSQL instead of SQLite.

**Rationale:** The requirements include concurrent writes, atomic zone increments, safe aggregate state, and transactional fault handling. PostgreSQL provides row-level locking, transactional isolation, and production-like concurrency behavior. `SELECT ... FOR UPDATE` is directly useful when updating vehicle state and handling fault transitions.

**Alternatives considered:**

- SQLite: simpler setup, but less appropriate for concurrent write-heavy ingestion and row-level locking semantics.
- In-memory store: insufficient persistence and concurrency guarantees.
- Time-series database: useful at larger scale, but unnecessary for this scope.

**Consequences:** PostgreSQL adds setup complexity, handled through Docker Compose. In exchange, the concurrency model is realistic and correct for the requested behaviors.

### Runtime

**Decision:** Use Docker Compose to run Postgres, backend, frontend, and optional simulator/test services.

**Rationale:** Compose reduces evaluator environment drift and makes PostgreSQL practical without requiring manual local installation. It gives a single reproducible run path.

**Alternatives considered:**

- Local-only setup: fewer config files, but more machine-specific setup.
- Cloud-hosted database: unnecessary for local evaluation and harder to reproduce.

**Consequences:** Slightly more configuration, but simpler setup and repeatable tests.

### ORM And Migrations

**Decision:** Use SQLAlchemy 2.x for database access and Alembic for migrations.

**Rationale:** SQLAlchemy provides explicit control over sessions, transactions, locking, and SQL expressions. Alembic gives repeatable schema creation and seeded reference data.

**Alternatives considered:**

- Raw SQL only: maximum control, but more repetitive application code.
- Django ORM: capable, but tied to a heavier framework.
- SQLModel: convenient, but less explicit for this transaction-focused implementation.

**Consequences:** More boilerplate than a lighter ORM, but better control over transactional logic and row locks.

### Auth And Session Model

**Decision:** Implement `POST /auth/vehicle-token`. Vehicles request a 1-hour JWT using `vehicle_id`. The backend issues the token only if the vehicle exists and has no active unexpired telemetry session.

**Rationale:** The original challenge does not require auth, but a minimal handshake creates a realistic ingestion boundary. It prevents arbitrary `vehicle_id` spoofing and gives the backend a session model for active telemetry senders.

**Alternatives considered:**

- No authentication: simplest, but allows spoofed telemetry.
- Static API key: easy, but does not bind telemetry to a vehicle identity.
- OAuth/device identity: too much infrastructure for this scope.
- mTLS: strong production option, but overbuilt.

**Consequences:** Adds modest implementation complexity. Every telemetry request must carry a valid Bearer token, and the token `vehicle_id` must match the payload `vehicle_id`.

### Ingestion Model

**Decision:** Persist every valid authenticated telemetry event. Update current vehicle state only when the incoming timestamp is newer than the stored latest timestamp.

**Rationale:** Telemetry can arrive out of order due to network delays, retries, or concurrent ingestion. Historical events should not be discarded, but older events must not overwrite current state.

**Alternatives considered:**

- Reject out-of-order telemetry: simpler current state handling, but loses valid history.
- Last write wins by processing time: easy, but corrupts current state when delayed events arrive.

**Consequences:** The system preserves authoritative history while protecting current vehicle state from stale writes.

### Fault Transaction

**Decision:** When a vehicle transitions to `fault`, lock the vehicle row, persist telemetry/anomalies, cancel the active mission if present, create a maintenance record, update vehicle state, and commit all writes in one transaction.

**Rationale:** The requirement explicitly calls for atomic mission cancellation and maintenance creation on fault transition. A row lock prevents concurrent updates from racing on the same vehicle state.

**Alternatives considered:**

- Separate independent writes: simpler, but can leave partial fault handling.
- Eventual consistency through async workers: scalable, but weaker for the requested invariant.
- Application-level locks: fragile across processes and unnecessary with PostgreSQL row locks.

**Consequences:** Fault transitions remain strongly consistent. Concurrent writes for the same vehicle may block briefly, which is acceptable at this scale.

### Zone Counter

**Decision:** Use a hardcoded `ZONES` constant and a `zone_counts` table. When `zone_entered` is non-null, increment with an atomic SQL update:

```sql
UPDATE zone_counts
SET entry_count = entry_count + 1
WHERE zone_id = :zone_id;
```

**Rationale:** Multiple vehicles can enter the same zone at the same time. Application-level read-modify-write can lose increments under concurrency. Atomic database updates preserve every counted entry.

**Alternatives considered:**

- Application-level counter: vulnerable to lost updates and process-local state.
- Recompute counts from telemetry history: accurate, but too expensive for dashboard reads.
- External counter store: useful at larger scale, but unnecessary here.

**Consequences:** Zone counting is simple and concurrency-safe. Recomputing from history can remain a validation/debug strategy.

### Anomaly Detection

**Decision:** Use deterministic rule-based anomaly detection.

**Implemented anomalies:**

- `GPS_JUMP`: previous telemetry exists and implied movement exceeds 12 m/s.
- `STATUS_SPEED_CONFLICT`: status is `idle` or `charging`, and `speed_mps > 0.5`.
- `REPEATED_FAULT_CODES`: same error code appears at least 3 times within 5 minutes for a vehicle.
- `BATTERY_DRAIN_SPIKE`: battery drops by more than 10 percentage points within 60 seconds.
- `STALE_TELEMETRY`: latest telemetry timestamp is older than 10 seconds.

**Rationale:** Deterministic rules are easier to inspect, test, explain, and validate than ML for this scope. The chosen rules cover impossible movement, state/motion conflicts, persistent diagnostics, abnormal battery behavior, and missing telemetry.

Low battery is classified separately as `LOW_BATTERY_WARNING` when `battery_pct < 15`. Low battery is an expected operational condition requiring attention, not necessarily abnormal behavior.

**Alternatives considered:**

- ML anomaly detection: overbuilt, opaque, and hard to evaluate.
- Only threshold checks: simpler, but misses repeated fault patterns and movement conflicts.
- External stream processor: useful at scale, but unnecessary for 50 vehicles.

**Consequences:** The anomaly model is transparent and testable. It is intentionally limited to known deterministic cases.

### Stale Telemetry Strategy

**Decision:** Evaluate `STALE_TELEMETRY` through a freshness evaluation service during dashboard/API reads, not strictly during ingestion.

**Rationale:** Most anomalies are triggered by telemetry arriving. Stale telemetry is caused by missing telemetry, so there is no new event to trigger the rule. For the scope of this project, freshness can be computed from `current_time - vehicle.latest_timestamp`. Persist one stale anomaly per stale episode to avoid duplicates.

**Alternatives considered:**

- Background scheduler: more production-like, but more moving parts.
- Stream-processing timeout: better at scale, but requires queue/stream infrastructure.
- Durable workflow timer: reliable, but overbuilt.

**Consequences:** The implementation stays lightweight. `STALE_TELEMETRY` is explicitly the one time/freshness-based anomaly rather than an ingestion-event-based anomaly.

### Domain Events

**Decision:** Use lightweight internal domain events with an in-process publisher/subscriber. Emit events after successful database commit.

**Events:**

- `TelemetryReceived`
- `VehicleStateUpdated`
- `VehicleFaulted`
- `MissionCancelled`
- `MaintenanceRecordCreated`
- `ZoneEntered`
- `ZoneEntryCountIncremented`
- `AnomalyDetected`
- `WarningRaised`
- `TelemetryBecameStale`

**Rationale:** Domain events separate ingestion behavior from follow-up concerns such as logs, derived state, metrics, or future pub/sub integration. Publishing only after commit prevents handlers from observing rolled-back changes.

**Alternatives considered:**

- No event abstraction: simpler, but tightly couples side effects to request handling.
- External broker immediately: more scalable, but unnecessary for this slice.
- Transactional outbox immediately: robust, but more implementation overhead than needed here.

**Consequences:** The domain model is easier to extend. In-process events are not durable, so external pub/sub and a transactional outbox belong to the future scale path.

### Rate Limiting

**Decision:** Add simple per-vehicle API-level rate limiting: 15 telemetry requests per 10 seconds per vehicle.

**Rationale:** Each vehicle is expected to emit at 1 Hz, or 10 requests per 10 seconds. A threshold of 15 allows normal jitter and small bursts while protecting against runaway clients.

**Alternatives considered:**

- No rate limiting: simplest, but leaves the API vulnerable to accidental floods.
- Strict 1 request per second: too brittle for jitter and retries.
- Redis/API Gateway rate limiting: production-grade, but unnecessary for this scale.

**Consequences:** The API has basic protection. The limiter is process-local and not distributed.

### Dashboard Polling

**Decision:** Use polling every 1-2 seconds instead of WebSockets.

**Rationale:** The fleet is small, the dashboard does not need sub-second latency, and polling is simple to debug and recover. Connection recovery is straightforward because each poll fetches current derived state.

**Alternatives considered:**

- WebSockets: lower latency, but more lifecycle and reconnection complexity.
- Server-Sent Events: simpler than WebSockets, but still unnecessary for this scope.

**Consequences:** The dashboard is slightly less real-time than push, but simpler and reliable enough for the vertical slice.

### Frontend Stack

**Decision:** Use React, TypeScript, Vite, RizzUI, Tailwind CSS, and Recharts.

**Rationale:** React and TypeScript fit an operational dashboard. Vite gives a fast development loop. RizzUI provides Tailwind-based UI primitives for cards, tables, badges, filters, alerts, and metrics. Recharts covers the required status, zone, anomaly, and freshness charts.

**Alternatives considered:**

- Plain HTML/CSS: less dependency weight, but slower to build a polished dashboard.
- Material UI: mature, but heavier and visually opinionated.
- shadcn/ui: strong option, but would introduce another component pattern.
- No charts: simpler, but weaker dashboard value.

**Consequences:** The frontend gets usable dashboard quality with limited custom UI code. Some custom layout CSS is still needed for spacing, density, and chart legibility.

### API Shape

**Decision:** Expose REST endpoints:

- `POST /auth/vehicle-token`
- `POST /telemetry`
- `GET /vehicles`
- `GET /fleet/state`
- `GET /zones/counts`
- `GET /anomalies`
- `GET /warnings`

**Rationale:** REST directly matches the prompt and maps cleanly to authentication, ingestion, dashboard state, zone counters, anomaly queries, and warning queries.

**Alternatives considered:**

- GraphQL: flexible, but unnecessary for this fixed dashboard/API surface.
- gRPC: efficient, but less evaluator-friendly for browser/dashboard workflows.

**Consequences:** The API is simple to inspect, test, and call from the dashboard or IntelliJ HTTP client.

### Simulator

**Decision:** Provide a simulator that requests tokens and emits telemetry for 50 vehicles at roughly 1 Hz.

**Rationale:** The simulator demonstrates ingestion, concurrency, anomaly generation, zone counter updates, low battery warnings, and stale telemetry behavior without manual setup.

**Alternatives considered:**

- Manual API examples only: useful, but does not prove concurrent behavior.
- Test-only fixtures: good for CI, but not demonstrable in the dashboard.

**Consequences:** Evaluators can observe live dashboard behavior quickly. Simulator randomness means exact anomaly counts vary per run.

## Future Scale Path

At larger scale, the ingestion path should become:

```text
Vehicle -> Ingestion API -> Auth/rate limit -> Queue/stream -> Workers
        -> Current state store + historical telemetry store -> Dashboard read models
```

Recommended future changes:

- Move ingestion to Kafka, Kinesis, Redis Streams, RabbitMQ, or SQS.
- Add a transactional outbox so database commits and event publication cannot diverge.
- Split current vehicle state from historical telemetry storage.
- Use time-series or analytical storage for high-volume telemetry history.
- Use Redis, materialized views, or dedicated read models for dashboard aggregates.
- Add distributed rate limiting.
- Add idempotency keys for telemetry retries.
- Add dead-letter queues and retry policies.
- Add metrics, tracing, structured logs, and alerting.

## Deferred Scope

- Real geospatial zone detection: `zone_entered` is provided by the edge client.
- Full production authentication such as mTLS or OAuth: valuable, but too heavy for the slice.
- Frontend authentication and authorization: the dashboard is a local evaluator-facing tool for this project. Production would protect it with SSO/OIDC or another user auth layer.
- Kafka-based event architecture: the in-process publisher is enough to show event boundaries. Kafka or another broker belongs to the future scale path, not for this project implementation.
- Queue-based ingestion: documented as the future scale path and intentionally left out to keep the project focused.
- ML anomaly detection: deterministic rules are more inspectable and testable here.
- Advanced visual design system work: the dashboard is functional and readable, but not a full design-system implementation.
- Full observability stack: metrics, tracing, dashboards, alerting, and centralized logging are production concerns and not necessary to prove the requested telemetry workflow.
- Multi-tenant support: unnecessary for a single-fleet project.
