from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import (
    Anomaly,
    DomainEventLog,
    MaintenanceRecord,
    Mission,
    TelemetryEvent,
    TelemetrySession,
    Vehicle,
    WarningRecord,
    ZoneCount,
)
from app.schemas import TelemetryIn
from app.services.auth import create_vehicle_jwt
from app.services.telemetry import persist_telemetry
from tests.conftest import TestSessionLocal


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def get_token(client: TestClient, vehicle_id: str = "v-1") -> str:
    response = client.post("/auth/vehicle-token", json={"vehicle_id": vehicle_id})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def telemetry_payload(
    vehicle_id: str = "v-1",
    timestamp: datetime | None = None,
    **overrides,
) -> dict:
    payload = {
        "vehicle_id": vehicle_id,
        "timestamp": iso(timestamp or datetime.now(timezone.utc)),
        "lat": 37.41,
        "lon": -122.08,
        "battery_pct": 78,
        "speed_mps": 1.2,
        "status": "moving",
        "error_codes": [],
        "zone_entered": None,
    }
    payload.update(overrides)
    return payload


def test_vehicle_token_creation_and_duplicate_active_session_rejection(client: TestClient) -> None:
    response = client.post("/auth/vehicle-token", json={"vehicle_id": "v-12"})

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["expires_at"]

    duplicate = client.post("/auth/vehicle-token", json={"vehicle_id": "v-12"})
    assert duplicate.status_code == 409


def test_token_vehicle_id_mismatch_rejected(client: TestClient) -> None:
    token = get_token(client, "v-1")

    response = client.post(
        "/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json=telemetry_payload("v-2"),
    )

    assert response.status_code == 403


def test_telemetry_validation_rejects_invalid_payload(client: TestClient) -> None:
    token = get_token(client, "v-3")
    payload = telemetry_payload("v-3", lat=91, battery_pct=101, speed_mps=-1)

    response = client.post(
        "/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 422


def test_anomaly_detection_rules(client: TestClient, db_session) -> None:
    token = get_token(client, "v-4")
    base_time = datetime.now(timezone.utc)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload("v-4", base_time, battery_pct=90, error_codes=["E42"]),
    )
    assert first.status_code == 200

    second = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload(
            "v-4",
            base_time + timedelta(seconds=10),
            lat=37.42,
            lon=-122.08,
            battery_pct=75,
            speed_mps=1.0,
            status="idle",
            error_codes=["E42"],
        ),
    )
    assert second.status_code == 200

    third = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload(
            "v-4",
            base_time + timedelta(seconds=20),
            battery_pct=70,
            error_codes=["E42"],
        ),
    )
    assert third.status_code == 200

    anomaly_types = {
        row.type
        for row in db_session.execute(
            select(Anomaly).where(Anomaly.vehicle_id == "v-4")
        ).scalars()
    }
    assert {
        "GPS_JUMP",
        "STATUS_SPEED_CONFLICT",
        "BATTERY_DRAIN_SPIKE",
        "REPEATED_FAULT_CODES",
    }.issubset(anomaly_types)


def test_low_battery_warning_is_not_an_anomaly(client: TestClient, db_session) -> None:
    token = get_token(client, "v-5")

    response = client.post(
        "/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json=telemetry_payload("v-5", battery_pct=10),
    )

    assert response.status_code == 200
    warnings = db_session.execute(
        select(WarningRecord).where(WarningRecord.vehicle_id == "v-5")
    ).scalars().all()
    anomalies = db_session.execute(
        select(Anomaly).where(
            Anomaly.vehicle_id == "v-5",
            Anomaly.type == "LOW_BATTERY_WARNING",
        )
    ).scalars().all()
    assert [warning.type for warning in warnings] == ["LOW_BATTERY_WARNING"]
    assert anomalies == []


def test_zone_counter_concurrent_increments(db_session) -> None:
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    db_session.add(
        TelemetrySession(
            id=session_id,
            vehicle_id="v-6",
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            active=True,
        )
    )
    db_session.commit()

    token = create_vehicle_jwt("v-6", session_id, now, now + timedelta(hours=1))
    assert token

    def send(index: int) -> int:
        with TestSessionLocal() as db:
            result = persist_telemetry(
                db,
                TelemetryIn(
                    **telemetry_payload(
                        "v-6",
                        now + timedelta(milliseconds=index),
                        zone_entered="pack_station",
                    )
                ),
                "v-6",
                session_id,
            )
            return result["telemetry_event_id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(send, range(20)))

    assert len(ids) == 20
    db_session.expire_all()
    count = db_session.get(ZoneCount, "pack_station")
    assert count.entry_count == 20


def test_fault_transition_transaction_behavior(client: TestClient, db_session) -> None:
    mission = Mission(vehicle_id="v-7", status="active")
    db_session.add(mission)
    db_session.flush()
    vehicle = db_session.get(Vehicle, "v-7")
    vehicle.active_mission_id = mission.id
    db_session.commit()

    token = get_token(client, "v-7")
    response = client.post(
        "/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json=telemetry_payload(
            "v-7",
            status="fault",
            error_codes=["F999"],
        ),
    )

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Vehicle, "v-7").status == "fault"
    assert db_session.get(Mission, mission.id).status == "cancelled"
    maintenance = db_session.execute(
        select(MaintenanceRecord).where(MaintenanceRecord.vehicle_id == "v-7")
    ).scalar_one()
    assert maintenance.reason == "Vehicle entered fault status from telemetry"


def test_fleet_aggregate_state(client: TestClient, db_session) -> None:
    db_session.get(Vehicle, "v-1").status = "moving"
    db_session.get(Vehicle, "v-2").status = "charging"
    db_session.get(Vehicle, "v-3").status = "fault"
    db_session.commit()

    response = client.get("/fleet/state")

    assert response.status_code == 200
    assert response.json() == {"idle": 47, "moving": 1, "charging": 1, "fault": 1}


def test_out_of_order_telemetry_does_not_overwrite_current_state(
    client: TestClient,
    db_session,
) -> None:
    token = get_token(client, "v-8")
    headers = {"Authorization": f"Bearer {token}"}
    base_time = datetime.now(timezone.utc)

    newer = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload("v-8", base_time + timedelta(seconds=30), battery_pct=55),
    )
    older = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload(
            "v-8",
            base_time,
            status="idle",
            battery_pct=95,
            speed_mps=0,
        ),
    )

    assert newer.status_code == 200
    assert older.status_code == 200
    db_session.expire_all()
    vehicle = db_session.get(Vehicle, "v-8")
    assert vehicle.battery_pct == 55
    assert vehicle.latest_timestamp == base_time + timedelta(seconds=30)
    assert db_session.scalar(
        select(func.count()).select_from(TelemetryEvent).where(TelemetryEvent.vehicle_id == "v-8")
    ) == 2


def test_rate_limit_behavior(client: TestClient) -> None:
    token = get_token(client, "v-9")
    headers = {"Authorization": f"Bearer {token}"}
    base_time = datetime.now(timezone.utc)

    for i in range(15):
        response = client.post(
            "/telemetry",
            headers=headers,
            json=telemetry_payload("v-9", base_time + timedelta(milliseconds=i)),
        )
        assert response.status_code == 200

    limited = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload("v-9", base_time + timedelta(seconds=1)),
    )
    assert limited.status_code == 429


def test_domain_events_emitted_after_successful_commits(client: TestClient, db_session) -> None:
    token = get_token(client, "v-10")
    headers = {"Authorization": f"Bearer {token}"}

    valid = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload("v-10", zone_entered="sort_belt"),
    )
    assert valid.status_code == 200
    event_types = {
        row.event_type
        for row in db_session.execute(
            select(DomainEventLog).where(DomainEventLog.aggregate_id.in_(["v-10", "sort_belt"]))
        ).scalars()
    }
    assert "TelemetryReceived" in event_types
    assert "VehicleStateUpdated" in event_types
    assert "ZoneEntryCountIncremented" in event_types

    before = db_session.scalar(select(func.count()).select_from(DomainEventLog))
    invalid = client.post(
        "/telemetry",
        headers=headers,
        json=telemetry_payload("v-10", zone_entered="missing_zone"),
    )
    assert invalid.status_code == 422
    after = db_session.scalar(select(func.count()).select_from(DomainEventLog))
    assert after == before


def test_stale_telemetry_persisted_once_per_episode(client: TestClient, db_session) -> None:
    vehicle = db_session.get(Vehicle, "v-11")
    vehicle.latest_timestamp = datetime.now(timezone.utc) - timedelta(seconds=20)
    vehicle.status = "moving"
    db_session.commit()

    first = client.get("/vehicles")
    second = client.get("/vehicles")

    assert first.status_code == 200
    assert second.status_code == 200
    stale = [
        row
        for row in db_session.execute(
            select(Anomaly).where(
                Anomaly.vehicle_id == "v-11",
                Anomaly.type == "STALE_TELEMETRY",
            )
        ).scalars()
    ]
    assert len(stale) == 1
