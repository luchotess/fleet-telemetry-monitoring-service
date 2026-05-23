from collections import Counter
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TelemetryEvent
from app.schemas import TelemetryIn


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * radius_m * asin(sqrt(a))


def nearest_prior_telemetry(db: Session, payload: TelemetryIn) -> TelemetryEvent | None:
    return db.execute(
        select(TelemetryEvent)
        .where(
            TelemetryEvent.vehicle_id == payload.vehicle_id,
            TelemetryEvent.timestamp < payload.timestamp,
        )
        .order_by(TelemetryEvent.timestamp.desc(), TelemetryEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def detect_anomalies(
    db: Session,
    payload: TelemetryIn,
    previous: TelemetryEvent | None,
) -> list[dict]:
    anomalies: list[dict] = []

    if previous is not None:
        seconds = (payload.timestamp - previous.timestamp).total_seconds()
        if seconds > 0:
            speed = haversine_meters(
                previous.lat,
                previous.lon,
                payload.lat,
                payload.lon,
            ) / seconds
            if speed > 12:
                anomalies.append(
                    {
                        "type": "GPS_JUMP",
                        "severity": "high",
                        "details": {
                            "implied_speed_mps": round(speed, 2),
                            "threshold_mps": 12,
                            "previous_telemetry_event_id": previous.id,
                        },
                    }
                )

            battery_drop = previous.battery_pct - payload.battery_pct
            if seconds <= 60 and battery_drop > 10:
                anomalies.append(
                    {
                        "type": "BATTERY_DRAIN_SPIKE",
                        "severity": "medium",
                        "details": {
                            "battery_drop_pct": battery_drop,
                            "elapsed_seconds": round(seconds, 2),
                            "previous_telemetry_event_id": previous.id,
                        },
                    }
                )

    if payload.status in {"idle", "charging"} and payload.speed_mps > 0.5:
        anomalies.append(
            {
                "type": "STATUS_SPEED_CONFLICT",
                "severity": "medium",
                "details": {
                    "status": payload.status,
                    "speed_mps": payload.speed_mps,
                    "threshold_mps": 0.5,
                },
            }
        )

    if payload.error_codes:
        window_start = payload.timestamp - timedelta(minutes=5)
        recent_events = db.execute(
            select(TelemetryEvent.error_codes).where(
                TelemetryEvent.vehicle_id == payload.vehicle_id,
                TelemetryEvent.timestamp >= window_start,
                TelemetryEvent.timestamp <= payload.timestamp,
            )
        ).scalars()
        counts: Counter[str] = Counter()
        for error_codes in recent_events:
            counts.update(set(error_codes or []))
        for code in set(payload.error_codes):
            if counts[code] >= 3:
                anomalies.append(
                    {
                        "type": "REPEATED_FAULT_CODES",
                        "severity": "high",
                        "details": {
                            "error_code": code,
                            "occurrences_in_5m": counts[code],
                        },
                    }
                )

    return anomalies
