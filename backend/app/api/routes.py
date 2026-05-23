from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Anomaly, WarningRecord
from app.db.session import get_db
from app.schemas import (
    AnomalyOut,
    FleetStateOut,
    TelemetryAccepted,
    TelemetryIn,
    VehicleStateOut,
    VehicleTokenRequest,
    VehicleTokenResponse,
    WarningOut,
    ZoneCountOut,
)
from app.services.auth import decode_vehicle_jwt, issue_vehicle_token
from app.services.dashboard import evaluate_stale_vehicles, fleet_state, list_vehicle_states, zone_counts
from app.services.rate_limiter import vehicle_rate_limiter
from app.services.telemetry import persist_telemetry

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def token_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer telemetry token required",
        )
    return decode_vehicle_jwt(credentials.credentials)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/vehicle-token", response_model=VehicleTokenResponse)
def vehicle_token(payload: VehicleTokenRequest, db: Session = Depends(get_db)) -> dict:
    return issue_vehicle_token(db, payload.vehicle_id)


@router.post("/telemetry", response_model=TelemetryAccepted)
def telemetry(
    payload: TelemetryIn,
    claims: dict[str, str] = Depends(token_claims),
    db: Session = Depends(get_db),
) -> dict:
    vehicle_id = claims["vehicle_id"]
    if not vehicle_rate_limiter.allow(vehicle_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Telemetry rate limit exceeded",
        )
    return persist_telemetry(db, payload, vehicle_id, claims["session_id"])


@router.get("/vehicles", response_model=list[VehicleStateOut])
def vehicles(db: Session = Depends(get_db)) -> list[dict]:
    return list_vehicle_states(db)


@router.get("/fleet/state", response_model=FleetStateOut)
def get_fleet_state(db: Session = Depends(get_db)) -> dict:
    return fleet_state(db)


@router.get("/zones/counts", response_model=list[ZoneCountOut])
def get_zone_counts(db: Session = Depends(get_db)) -> list[dict]:
    return zone_counts(db)


@router.get("/anomalies", response_model=list[AnomalyOut])
def anomalies(
    vehicle_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Anomaly]:
    evaluate_stale_vehicles(db)
    query = select(Anomaly)
    if vehicle_id:
        query = query.where(Anomaly.vehicle_id == vehicle_id)
    if start_time:
        query = query.where(Anomaly.timestamp >= start_time)
    if end_time:
        query = query.where(Anomaly.timestamp <= end_time)
    return (
        db.execute(query.order_by(Anomaly.timestamp.desc(), Anomaly.id.desc()).limit(limit))
        .scalars()
        .all()
    )


@router.get("/warnings", response_model=list[WarningOut])
def warnings(
    vehicle_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[WarningRecord]:
    query = select(WarningRecord)
    if vehicle_id:
        query = query.where(WarningRecord.vehicle_id == vehicle_id)
    if start_time:
        query = query.where(WarningRecord.timestamp >= start_time)
    if end_time:
        query = query.where(WarningRecord.timestamp <= end_time)
    return (
        db.execute(query.order_by(WarningRecord.timestamp.desc(), WarningRecord.id.desc()).limit(limit))
        .scalars()
        .all()
    )
