export type Status = 'idle' | 'moving' | 'charging' | 'fault';
export type Freshness = 'never_seen' | 'fresh' | 'stale';

export interface Anomaly {
  id: number;
  vehicle_id: string;
  telemetry_event_id: number | null;
  type: string;
  severity: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export interface WarningRecord {
  id: number;
  vehicle_id: string;
  telemetry_event_id: number | null;
  type: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export interface VehicleState {
  vehicle_id: string;
  latest_timestamp: string | null;
  status: Status;
  battery_pct: number | null;
  speed_mps: number | null;
  lat: number | null;
  lon: number | null;
  active_mission_id: number | null;
  latest_anomaly: Anomaly | null;
  latest_warning: WarningRecord | null;
  freshness: Freshness;
}

export interface FleetState {
  idle: number;
  moving: number;
  charging: number;
  fault: number;
}

export interface ZoneCount {
  zone_id: string;
  entry_count: number;
}
