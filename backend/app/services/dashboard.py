from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import STALE_AFTER_SECONDS, ZONES
from app.db.models import Anomaly, Vehicle, WarningRecord, ZoneCount
from app.domain.events import DomainEvent, build_event, publisher


def freshness_for(vehicle: Vehicle, now: datetime | None = None) -> str:
    if vehicle.latest_timestamp is None:
        return "never_seen"
    now = now or datetime.now(timezone.utc)
    age_seconds = (now - vehicle.latest_timestamp).total_seconds()
    return "stale" if age_seconds > STALE_AFTER_SECONDS else "fresh"


def evaluate_stale_vehicles(db: Session) -> None:
    now = datetime.now(timezone.utc)
    candidates = db.execute(
        select(Vehicle)
        .where(
            Vehicle.latest_timestamp.is_not(None),
            Vehicle.stale_episode_open.is_(False),
        )
        .with_for_update()
    ).scalars()

    events: list[DomainEvent] = []
    for vehicle in candidates:
        if freshness_for(vehicle, now) != "stale":
            continue
        anomaly = Anomaly(
            vehicle_id=vehicle.vehicle_id,
            telemetry_event_id=None,
            type="STALE_TELEMETRY",
            severity="medium",
            timestamp=now,
            details={
                "latest_timestamp": vehicle.latest_timestamp.isoformat(),
                "stale_after_seconds": STALE_AFTER_SECONDS,
            },
        )
        db.add(anomaly)
        vehicle.stale_episode_open = True
        events.append(
            build_event(
                "TelemetryBecameStale",
                vehicle.vehicle_id,
                {"latest_timestamp": vehicle.latest_timestamp.isoformat()},
            )
        )
        events.append(
            build_event(
                "AnomalyDetected",
                vehicle.vehicle_id,
                {"type": "STALE_TELEMETRY", "severity": "medium"},
            )
        )

    if events:
        db.commit()
        publisher.publish_many(events)
    else:
        db.rollback()


def list_vehicle_states(db: Session) -> list[dict]:
    evaluate_stale_vehicles(db)
    now = datetime.now(timezone.utc)
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.vehicle_id)).scalars().all()
    results: list[dict] = []
    for vehicle in vehicles:
        latest_anomaly = db.execute(
            select(Anomaly)
            .where(Anomaly.vehicle_id == vehicle.vehicle_id)
            .order_by(Anomaly.timestamp.desc(), Anomaly.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        latest_warning = db.execute(
            select(WarningRecord)
            .where(WarningRecord.vehicle_id == vehicle.vehicle_id)
            .order_by(WarningRecord.timestamp.desc(), WarningRecord.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        results.append(
            {
                "vehicle_id": vehicle.vehicle_id,
                "latest_timestamp": vehicle.latest_timestamp,
                "status": vehicle.status,
                "battery_pct": vehicle.battery_pct,
                "speed_mps": vehicle.speed_mps,
                "lat": vehicle.lat,
                "lon": vehicle.lon,
                "active_mission_id": vehicle.active_mission_id,
                "latest_anomaly": latest_anomaly,
                "latest_warning": latest_warning,
                "freshness": freshness_for(vehicle, now),
            }
        )
    return results


def fleet_state(db: Session) -> dict[str, int]:
    rows = db.execute(select(Vehicle.status, func.count()).group_by(Vehicle.status)).all()
    state = {"idle": 0, "moving": 0, "charging": 0, "fault": 0}
    for status, count in rows:
        state[status] = count
    return state


def zone_counts(db: Session) -> list[dict]:
    rows = db.execute(select(ZoneCount)).scalars().all()
    by_id = {row.zone_id: row.entry_count for row in rows}
    return [{"zone_id": zone_id, "entry_count": by_id.get(zone_id, 0)} for zone_id in ZONES]
