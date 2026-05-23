import type { Anomaly, FleetState, VehicleState, WarningRecord, ZoneCount } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchDashboard() {
  const [vehicles, fleetState, zoneCounts, anomalies, warnings] = await Promise.all([
    getJson<VehicleState[]>('/vehicles'),
    getJson<FleetState>('/fleet/state'),
    getJson<ZoneCount[]>('/zones/counts'),
    getJson<Anomaly[]>('/anomalies?limit=100'),
    getJson<WarningRecord[]>('/warnings?limit=100'),
  ]);

  return { vehicles, fleetState, zoneCounts, anomalies, warnings };
}
