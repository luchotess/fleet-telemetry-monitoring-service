from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.constants import ZONES
from app.db.models import (
    Anomaly,
    MaintenanceRecord,
    Mission,
    TelemetryEvent,
    Vehicle,
    WarningRecord,
    ZoneCount,
)
from app.domain.events import DomainEvent, build_event, publisher
from app.schemas import TelemetryIn
from app.services.anomaly_detection import detect_anomalies, nearest_prior_telemetry
from app.services.auth import require_active_session


def persist_telemetry(
    db: Session,
    payload: TelemetryIn,
    authenticated_vehicle_id: str,
    session_id: str,
) -> dict:
    if payload.vehicle_id != authenticated_vehicle_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telemetry vehicle_id does not match token",
        )

    if payload.zone_entered is not None and payload.zone_entered not in ZONES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="zone_entered is not a known zone",
        )

    events: list[DomainEvent] = []
    try:
        require_active_session(db, authenticated_vehicle_id, session_id)

        vehicle = db.execute(
            select(Vehicle)
            .where(Vehicle.vehicle_id == payload.vehicle_id)
            .with_for_update()
        ).scalar_one_or_none()
        if vehicle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

        previous = nearest_prior_telemetry(db, payload)
        telemetry_event = TelemetryEvent(
            vehicle_id=payload.vehicle_id,
            session_id=session_id,
            timestamp=payload.timestamp,
            lat=payload.lat,
            lon=payload.lon,
            battery_pct=payload.battery_pct,
            speed_mps=payload.speed_mps,
            status=payload.status,
            error_codes=payload.error_codes,
            zone_entered=payload.zone_entered,
        )
        db.add(telemetry_event)
        db.flush()

        events.append(
            build_event(
                "TelemetryReceived",
                payload.vehicle_id,
                {
                    "telemetry_event_id": telemetry_event.id,
                    "timestamp": payload.timestamp.isoformat(),
                },
            )
        )

        anomaly_specs = detect_anomalies(db, payload, previous)
        persisted_anomalies: list[Anomaly] = []
        for spec in anomaly_specs:
            anomaly = Anomaly(
                vehicle_id=payload.vehicle_id,
                telemetry_event_id=telemetry_event.id,
                type=spec["type"],
                severity=spec["severity"],
                timestamp=payload.timestamp,
                details=spec["details"],
            )
            db.add(anomaly)
            persisted_anomalies.append(anomaly)
            events.append(
                build_event(
                    "AnomalyDetected",
                    payload.vehicle_id,
                    {
                        "type": spec["type"],
                        "severity": spec["severity"],
                        "telemetry_event_id": telemetry_event.id,
                    },
                )
            )

        persisted_warnings: list[WarningRecord] = []
        if payload.battery_pct < 15:
            warning = WarningRecord(
                vehicle_id=payload.vehicle_id,
                telemetry_event_id=telemetry_event.id,
                type="LOW_BATTERY_WARNING",
                timestamp=payload.timestamp,
                details={"battery_pct": payload.battery_pct, "threshold_pct": 15},
            )
            db.add(warning)
            persisted_warnings.append(warning)
            events.append(
                build_event(
                    "WarningRaised",
                    payload.vehicle_id,
                    {
                        "type": "LOW_BATTERY_WARNING",
                        "telemetry_event_id": telemetry_event.id,
                    },
                )
            )

        if payload.zone_entered is not None:
            db.execute(
                update(ZoneCount)
                .where(ZoneCount.zone_id == payload.zone_entered)
                .values(entry_count=ZoneCount.entry_count + 1)
            )
            events.append(
                build_event(
                    "ZoneEntered",
                    payload.vehicle_id,
                    {
                        "zone_id": payload.zone_entered,
                        "telemetry_event_id": telemetry_event.id,
                    },
                )
            )
            events.append(
                build_event(
                    "ZoneEntryCountIncremented",
                    payload.zone_entered,
                    {"zone_id": payload.zone_entered},
                )
            )

        should_update_state = (
            vehicle.latest_timestamp is None or payload.timestamp > vehicle.latest_timestamp
        )
        if should_update_state:
            previous_status = vehicle.status
            transitioning_to_fault = previous_status != "fault" and payload.status == "fault"

            vehicle.latest_timestamp = payload.timestamp
            vehicle.status = payload.status
            vehicle.battery_pct = payload.battery_pct
            vehicle.speed_mps = payload.speed_mps
            vehicle.lat = payload.lat
            vehicle.lon = payload.lon
            vehicle.stale_episode_open = False

            events.append(
                build_event(
                    "VehicleStateUpdated",
                    vehicle.vehicle_id,
                    {
                        "previous_status": previous_status,
                        "status": payload.status,
                        "latest_timestamp": payload.timestamp.isoformat(),
                    },
                )
            )

            if transitioning_to_fault:
                if vehicle.active_mission_id is not None:
                    mission = db.get(Mission, vehicle.active_mission_id)
                    if mission is not None and mission.status == "active":
                        mission.status = "cancelled"
                        mission.cancelled_at = datetime.now(timezone.utc)
                        events.append(
                            build_event(
                                "MissionCancelled",
                                vehicle.vehicle_id,
                                {
                                    "mission_id": mission.id,
                                    "telemetry_event_id": telemetry_event.id,
                                },
                            )
                        )

                maintenance_record = MaintenanceRecord(
                    vehicle_id=vehicle.vehicle_id,
                    telemetry_event_id=telemetry_event.id,
                    reason="Vehicle entered fault status from telemetry",
                )
                db.add(maintenance_record)
                db.flush()
                events.append(
                    build_event(
                        "MaintenanceRecordCreated",
                        vehicle.vehicle_id,
                        {
                            "maintenance_record_id": maintenance_record.id,
                            "telemetry_event_id": telemetry_event.id,
                        },
                    )
                )
                events.append(
                    build_event(
                        "VehicleFaulted",
                        vehicle.vehicle_id,
                        {"telemetry_event_id": telemetry_event.id},
                    )
                )

        db.commit()
    except Exception:
        db.rollback()
        raise

    publisher.publish_many(events)
    return {
        "telemetry_event_id": telemetry_event.id,
        "anomalies": [anomaly.type for anomaly in persisted_anomalies],
        "warnings": [warning.type for warning in persisted_warnings],
    }
