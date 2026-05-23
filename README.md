# Fleet Telemetry Monitoring Service

Fullstack take-home implementation for monitoring a 50-vehicle fleet. The service ingests authenticated vehicle telemetry, persists every valid event, updates current fleet state transactionally, detects deterministic anomalies, tracks low-battery warnings separately, and exposes a polling dashboard.

## Architecture Summary

- Backend: Python, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL.
- Frontend: React, TypeScript, Vite, RizzUI, Tailwind CSS, Recharts.
- Runtime: Docker Compose with Postgres, backend, frontend, and an optional simulator profile.
- API style: REST.
- Dashboard update model: frontend polling every 1.5 seconds.
- Vehicle authentication: `POST /auth/vehicle-token` issues 1-hour JWTs for existing vehicles without an unexpired active session.
- Telemetry ingestion: authenticated `POST /telemetry`, row-level vehicle locking, authoritative event persistence, synchronous anomaly detection, atomic zone increments, and out-of-order protection for current vehicle state.
- Domain events: lightweight in-process publisher/subscriber. Events are accumulated inside the transaction and published only after a successful commit. A subscriber writes `domain_event_logs`.

Queue-based ingestion is the future scale path: put authenticated telemetry onto a durable queue, let workers perform the same transactional ingestion, and keep the dashboard reading derived state from Postgres or a read model.

## Docker Compose Setup

Start the database, backend, and dashboard:

```bash
docker compose up --build
```

Open:

- Backend API: [http://localhost:8000](http://localhost:8000)
- Frontend dashboard: [http://localhost:5173](http://localhost:5173)

Run the simulator profile:

```bash
docker compose --profile simulator up --build simulator
```

Run the Postgres-backed test profile:

```bash
docker compose --profile test up --build --abort-on-container-exit backend-tests
```

## Backend Local Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://fleet:fleet@localhost:5432/fleet
export JWT_SECRET=development-only-secret
alembic upgrade head
uvicorn app.main:app --reload
```

If you only need Postgres locally:

```bash
docker compose up postgres
```

## Frontend Local Setup

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

The dashboard polls `/vehicles`, `/fleet/state`, `/zones/counts`, `/anomalies`, and `/warnings` every 1.5 seconds.

## Migrations

Apply migrations:

```bash
cd backend
alembic upgrade head
```

Create a new migration after model changes:

```bash
cd backend
alembic revision --autogenerate -m "describe change"
```

The initial migration creates all required tables and seeds exactly 50 vehicles (`v-1` through `v-50`) plus the 20 hardcoded zones.

## Simulator

Docker:

```bash
docker compose --profile simulator up --build simulator
```

Local:

```bash
cd simulator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 python simulate.py
```

The simulator requests tokens for all 50 vehicles, emits roughly 1Hz telemetry concurrently, occasionally enters zones, creates GPS jumps, status/speed conflicts, repeated fault codes, battery drain spikes, stale gaps, fault states, and low-battery warnings.

## Tests

Run the test profile:

```bash
docker compose --profile test up --build --abort-on-container-exit backend-tests
```

The suite covers token creation, token mismatch rejection, telemetry validation, anomaly detection, low-battery warning classification, concurrent zone increments, fault transition transactions, fleet aggregates, out-of-order telemetry, rate limiting, post-commit domain event logs, and stale episode de-duplication.

## API Examples

Request a vehicle token:

```bash
curl -sS -X POST http://localhost:8000/auth/vehicle-token \
  -H 'Content-Type: application/json' \
  -d '{"vehicle_id":"v-12"}'
```

Send telemetry:

```bash
TOKEN="paste-token-here"
curl -sS -X POST http://localhost:8000/telemetry \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "vehicle_id": "v-12",
    "timestamp": "2026-05-23T17:00:00Z",
    "lat": 37.41,
    "lon": -122.08,
    "battery_pct": 78,
    "speed_mps": 1.2,
    "status": "moving",
    "error_codes": [],
    "zone_entered": null
  }'
```

Read dashboard-facing state:

```bash
curl -sS http://localhost:8000/vehicles
curl -sS http://localhost:8000/fleet/state
curl -sS http://localhost:8000/zones/counts
curl -sS 'http://localhost:8000/anomalies?limit=25'
curl -sS 'http://localhost:8000/warnings?limit=25'
```

## Authentication Flow

1. Vehicle calls `POST /auth/vehicle-token` with `vehicle_id`.
2. Backend verifies the vehicle exists and has no unexpired active session.
3. Backend creates a telemetry session expiring in 1 hour.
4. Backend returns a JWT containing `vehicle_id`, `session_id`, `issued_at`, and `expires_at`.
5. Vehicle sends telemetry with `Authorization: Bearer <token>`.
6. Backend rejects telemetry when the token vehicle does not match the payload vehicle.

## Event-Driven Overview

The ingestion service accumulates domain events while writing telemetry, anomalies, warnings, zone counts, current state, missions, and maintenance records in one database transaction. After commit, it publishes:

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

Handlers are local and lightweight. The included handler writes `domain_event_logs`, which keeps event emission observable without introducing external infrastructure.
