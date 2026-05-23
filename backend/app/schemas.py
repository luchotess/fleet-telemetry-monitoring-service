from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VehicleTokenRequest(BaseModel):
    vehicle_id: str = Field(min_length=1)


class VehicleTokenResponse(BaseModel):
    token: str
    expires_at: datetime


class TelemetryIn(BaseModel):
    vehicle_id: str = Field(min_length=1)
    timestamp: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    battery_pct: int = Field(ge=0, le=100)
    speed_mps: float = Field(ge=0)
    status: Literal["idle", "moving", "charging", "fault"]
    error_codes: list[str] = Field(default_factory=list)
    zone_entered: str | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class TelemetryAccepted(BaseModel):
    telemetry_event_id: int
    anomalies: list[str]
    warnings: list[str]


class AnomalyOut(BaseModel):
    id: int
    vehicle_id: str
    telemetry_event_id: int | None
    type: str
    severity: str
    timestamp: datetime
    details: dict

    model_config = {"from_attributes": True}


class WarningOut(BaseModel):
    id: int
    vehicle_id: str
    telemetry_event_id: int | None
    type: str
    timestamp: datetime
    details: dict

    model_config = {"from_attributes": True}


class VehicleStateOut(BaseModel):
    vehicle_id: str
    latest_timestamp: datetime | None
    status: str
    battery_pct: int | None
    speed_mps: float | None
    lat: float | None
    lon: float | None
    active_mission_id: int | None
    latest_anomaly: AnomalyOut | None
    latest_warning: WarningOut | None
    freshness: Literal["never_seen", "fresh", "stale"]


class FleetStateOut(BaseModel):
    idle: int
    moving: int
    charging: int
    fault: int


class ZoneCountOut(BaseModel):
    zone_id: str
    entry_count: int
