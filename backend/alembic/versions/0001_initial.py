"""initial schema and reference data

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.constants import ZONES

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("vehicle_id", sa.String(length=32), primary_key=True),
        sa.Column("latest_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("active_mission_id", sa.Integer(), nullable=True),
        sa.Column("stale_episode_open", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "telemetry_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_telemetry_sessions_vehicle_id", "telemetry_sessions", ["vehicle_id"])
    op.create_index("ix_telemetry_sessions_expires_at", "telemetry_sessions", ["expires_at"])

    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("telemetry_sessions.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("zone_entered", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_telemetry_events_vehicle_id", "telemetry_events", ["vehicle_id"])
    op.create_index("ix_telemetry_events_session_id", "telemetry_events", ["session_id"])
    op.create_index("ix_telemetry_events_timestamp", "telemetry_events", ["timestamp"])

    op.create_table(
        "anomalies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("telemetry_event_id", sa.Integer(), sa.ForeignKey("telemetry_events.id"), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_anomalies_vehicle_id", "anomalies", ["vehicle_id"])
    op.create_index("ix_anomalies_type", "anomalies", ["type"])
    op.create_index("ix_anomalies_timestamp", "anomalies", ["timestamp"])

    op.create_table(
        "warnings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("telemetry_event_id", sa.Integer(), sa.ForeignKey("telemetry_events.id"), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_warnings_vehicle_id", "warnings", ["vehicle_id"])
    op.create_index("ix_warnings_type", "warnings", ["type"])
    op.create_index("ix_warnings_timestamp", "warnings", ["timestamp"])

    op.create_table(
        "zone_counts",
        sa.Column("zone_id", sa.String(length=64), primary_key=True),
        sa.Column("entry_count", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_missions_vehicle_id", "missions", ["vehicle_id"])
    op.create_table(
        "maintenance_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", sa.String(length=32), sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("telemetry_event_id", sa.Integer(), sa.ForeignKey("telemetry_events.id"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_maintenance_records_vehicle_id", "maintenance_records", ["vehicle_id"])
    op.create_table(
        "domain_event_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_domain_event_logs_event_type", "domain_event_logs", ["event_type"])
    op.create_index("ix_domain_event_logs_aggregate_id", "domain_event_logs", ["aggregate_id"])

    vehicles_table = sa.table(
        "vehicles",
        sa.column("vehicle_id", sa.String),
        sa.column("status", sa.String),
        sa.column("stale_episode_open", sa.Boolean),
    )
    zones_table = sa.table(
        "zone_counts",
        sa.column("zone_id", sa.String),
        sa.column("entry_count", sa.BigInteger),
    )
    op.bulk_insert(
        vehicles_table,
        [
            {"vehicle_id": f"v-{i}", "status": "idle", "stale_episode_open": False}
            for i in range(1, 51)
        ],
    )
    op.bulk_insert(
        zones_table,
        [{"zone_id": zone_id, "entry_count": 0} for zone_id in ZONES],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_event_logs_aggregate_id", table_name="domain_event_logs")
    op.drop_index("ix_domain_event_logs_event_type", table_name="domain_event_logs")
    op.drop_table("domain_event_logs")
    op.drop_index("ix_maintenance_records_vehicle_id", table_name="maintenance_records")
    op.drop_table("maintenance_records")
    op.drop_index("ix_missions_vehicle_id", table_name="missions")
    op.drop_table("missions")
    op.drop_table("zone_counts")
    op.drop_index("ix_warnings_timestamp", table_name="warnings")
    op.drop_index("ix_warnings_type", table_name="warnings")
    op.drop_index("ix_warnings_vehicle_id", table_name="warnings")
    op.drop_table("warnings")
    op.drop_index("ix_anomalies_timestamp", table_name="anomalies")
    op.drop_index("ix_anomalies_type", table_name="anomalies")
    op.drop_index("ix_anomalies_vehicle_id", table_name="anomalies")
    op.drop_table("anomalies")
    op.drop_index("ix_telemetry_events_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_session_id", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_vehicle_id", table_name="telemetry_events")
    op.drop_table("telemetry_events")
    op.drop_index("ix_telemetry_sessions_expires_at", table_name="telemetry_sessions")
    op.drop_index("ix_telemetry_sessions_vehicle_id", table_name="telemetry_sessions")
    op.drop_table("telemetry_sessions")
    op.drop_table("vehicles")
