# AI Interaction Log

This project used AI in two phases: an initial architecture and prompt-design discussion in ChatGPT, followed by implementation, verification, and iteration in Codex.

## ChatGPT Discussion

The ChatGPT phase focused on shaping the architecture and implementation prompt before coding began.

- Discussed the best database for the project scope and decided PostgreSQL was a better fit than SQLite because the challenge depends on concurrent writes, row-level locking, atomic increments, and transactional fault handling.
- Discussed a lightweight vehicle authentication model and chose a vehicle token handshake as the minimum useful authentication boundary for telemetry ingestion.
- Discussed whether to use event-driven architecture and how to balance that with rate limiting. The outcome was to use local domain events after successful commits and a simple per-vehicle rate limiter sized around the expected 1 Hz telemetry cadence.
- Discussed possible anomaly rules and selected five out of ten proposed candidates:
  - `GPS_JUMP`
  - `STATUS_SPEED_CONFLICT`
  - `REPEATED_FAULT_CODES`
  - `BATTERY_DRAIN_SPIKE`
  - `STALE_TELEMETRY`
- Clarified that low battery should be treated as a warning rather than an anomaly.
- Created, reviewed, and iterated the final implementation prompt that was then handed to Codex.

## Codex Discussion And Work

The Codex phase started from the ChatGPT-generated prompt and turned it into a working fullstack implementation.

- Entered planning mode and produced a detailed implementation plan covering backend, frontend, simulator, Docker, tests, and documentation.
- Confirmed two implementation choices with the user:
  - Use real Postgres through Docker Compose for backend tests.
  - Package the simulator as a Docker Compose profile.
- Implemented the backend with FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL models, telemetry ingestion, auth/session handling, anomaly detection, warnings, stale telemetry evaluation, rate limiting, and domain event logging.
- Implemented database migrations and seeded exactly 50 vehicles plus the 20 required zones.
- Added Postgres-backed pytest integration tests for token creation, token mismatch rejection, validation, anomaly detection, warning classification, concurrent zone increments, fault transactions, aggregate state, out-of-order telemetry, rate limiting, and post-commit domain event emission.
- Built the React + TypeScript + Vite dashboard using RizzUI, Tailwind CSS, and Recharts.
- Added the simulator, Dockerfiles, Docker Compose services, and README.
- Created incremental commits for each major implementation step.
- Ran local validation:
  - Python compilation.
  - Frontend production build.
  - Docker Compose config validation.
  - Docker image builds.
  - Postgres-backed pytest profile.
  - Live API smoke tests.
  - Simulator smoke test.
  - Browser smoke test of the dashboard.
- Improved Docker build contexts with `.dockerignore` files after noticing the frontend build context included local `node_modules` and `dist`.
- Added `request.http` for IntelliJ HTTP Client, including token capture, telemetry requests, anomaly examples, validation errors, and dashboard reads.
- Reviewed the dashboard visually in the in-app browser and improved the UX without adding another UI library:
  - Added internal panel/card padding.
  - Added metric details.
  - Improved chart layout and labels.
  - Added labeled filters.
  - Improved table spacing, sticky headers, badges, and battery bars.
- Created `ADR.md` and iterated it to explicitly answer reviewer-oriented architecture questions:
  - Most important decisions.
  - Unclear requirements and assumptions.
  - Definition of significant scale and future changes.
  - Deliberately deferred scope.
- Explicitly documented deferred items including frontend authentication, full observability, Kafka/external event architecture, queue-based ingestion, and production device identity.

## Notes On AI Use

- AI was used for architecture exploration, implementation planning, code generation, documentation drafting, test design, and iterative UX improvement.
- I made the key architectural choices and corrected implementation process details, requested documentation additions and UI improvements.
- Codex executed and verified the implementation locally, including Docker-backed integration tests once Docker was available.
