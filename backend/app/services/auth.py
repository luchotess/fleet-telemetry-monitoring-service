from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import TelemetrySession, Vehicle


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_vehicle_jwt(
    vehicle_id: str,
    session_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    payload = {
        "vehicle_id": vehicle_id,
        "session_id": session_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_vehicle_jwt(token: str) -> dict[str, str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telemetry token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid telemetry token",
        ) from exc

    if not payload.get("vehicle_id") or not payload.get("session_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid telemetry token claims",
        )
    return payload


def issue_vehicle_token(db: Session, vehicle_id: str) -> dict[str, str]:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    now = utc_now()
    active_session = db.execute(
        select(TelemetrySession).where(
            TelemetrySession.vehicle_id == vehicle_id,
            TelemetrySession.active.is_(True),
            TelemetrySession.expires_at > now,
        )
    ).scalar_one_or_none()
    if active_session is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vehicle already has an active telemetry session",
        )

    expires_at = now + timedelta(hours=1)
    session_id = str(uuid4())
    db.add(
        TelemetrySession(
            id=session_id,
            vehicle_id=vehicle_id,
            issued_at=now,
            expires_at=expires_at,
            active=True,
        )
    )
    db.commit()

    return {
        "token": create_vehicle_jwt(vehicle_id, session_id, now, expires_at),
        "expires_at": expires_at.isoformat(),
    }


def require_active_session(db: Session, vehicle_id: str, session_id: str) -> TelemetrySession:
    now = utc_now()
    session = db.get(TelemetrySession, session_id)
    if (
        session is None
        or session.vehicle_id != vehicle_id
        or not session.active
        or session.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telemetry session is not active",
        )
    return session
