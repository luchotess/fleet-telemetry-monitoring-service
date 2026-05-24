import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Box, Button, Input, Select, Table, Text, Title } from 'rizzui';
import { RotateCw } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { fetchDashboard } from './api';
import type { Anomaly, FleetState, Freshness, VehicleState, WarningRecord, ZoneCount } from './types';

interface DashboardData {
  vehicles: VehicleState[];
  fleetState: FleetState;
  zoneCounts: ZoneCount[];
  anomalies: Anomaly[];
  warnings: WarningRecord[];
}

const emptyFleet: FleetState = { idle: 0, moving: 0, charging: 0, fault: 0 };
const statusColors: Record<string, string> = {
  idle: '#64748b',
  moving: '#0f766e',
  charging: '#4338ca',
  fault: '#be123c',
};
const freshnessColors: Record<string, string> = {
  fresh: '#0f766e',
  stale: '#be123c',
  never_seen: '#b7791f',
};
const badgeColors: Record<string, 'success' | 'warning' | 'danger' | 'secondary' | 'primary'> = {
  idle: 'secondary',
  moving: 'success',
  charging: 'primary',
  fault: 'danger',
  fresh: 'success',
  stale: 'danger',
  never_seen: 'warning',
};
const statusOptions = [
  { label: 'All status', value: 'all' },
  { label: 'Idle', value: 'idle' },
  { label: 'Moving', value: 'moving' },
  { label: 'Charging', value: 'charging' },
  { label: 'Fault', value: 'fault' },
];
const freshnessOptions = [
  { label: 'All freshness', value: 'all' },
  { label: 'Fresh', value: 'fresh' },
  { label: 'Stale', value: 'stale' },
  { label: 'Never seen', value: 'never_seen' },
];

function fmtTime(value: string | null): string {
  if (!value) return 'Never';
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value));
}

function humanize(value: string | null | undefined): string {
  if (!value) return '-';
  return value
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function selectValue(value: unknown): string {
  if (value && typeof value === 'object' && 'value' in value) {
    return String((value as { value: string | number }).value);
  }
  return 'all';
}

function zoneLabel(value: string): string {
  return humanize(value).replace('Dock', 'Dk').replace('Charging Bay', 'Charge');
}

function MetricCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number | string;
  detail: string;
  tone?: 'neutral' | 'teal' | 'rose' | 'amber' | 'indigo';
}) {
  return (
    <Box className={`metric-card tone-${tone ?? 'neutral'}`}>
      <div>
        <Text className="metric-label">{label}</Text>
        <Title as="h3" className="metric-value">
          {value}
        </Title>
      </div>
      <Text className="metric-detail">{detail}</Text>
    </Box>
  );
}

function ChartPanel({
  title,
  detail,
  className,
  children,
}: {
  title: string;
  detail: string;
  className: string;
  children: ReactNode;
}) {
  return (
    <Box className={`panel chart-panel ${className}`}>
      <div className="panel-head">
        <div>
          <Title as="h2" className="panel-title">
            {title}
          </Title>
          <Text className="panel-detail">{detail}</Text>
        </div>
      </div>
      <div className="chart-body">{children}</div>
    </Box>
  );
}

function DomainBadge({
  value,
  tone,
}: {
  value: string | null | undefined;
  tone: 'status' | 'freshness' | 'anomaly' | 'warning';
}) {
  if (!value) return <span className="muted-value">-</span>;
  return (
    <Badge
      rounded="pill"
      size="sm"
      variant="flat"
      color={badgeColors[value] ?? (tone === 'warning' ? 'warning' : tone === 'anomaly' ? 'danger' : 'secondary')}
      className={`domain-badge ${tone}-${value.toLowerCase()}`}
    >
      {humanize(value)}
    </Badge>
  );
}

function BatteryCell({ value }: { value: number | null }) {
  if (value === null) return <span className="muted-value">-</span>;
  const tone = value < 15 ? 'danger' : value < 35 ? 'warning' : 'healthy';
  return (
    <div className="battery-cell">
      <span>{value}%</span>
      <span className="battery-track" aria-hidden="true">
        <span className={`battery-fill battery-${tone}`} style={{ width: `${value}%` }} />
      </span>
    </div>
  );
}

function freshnessChartValue(vehicles: VehicleState[], target: Freshness): number {
  return vehicles.filter((vehicle) => vehicle.freshness === target).length;
}

function App() {
  const [data, setData] = useState<DashboardData>({
    vehicles: [],
    fleetState: emptyFleet,
    zoneCounts: [],
    anomalies: [],
    warnings: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [freshnessFilter, setFreshnessFilter] = useState<string>('all');

  async function refresh() {
    try {
      const next = await fetchDashboard();
      setData(next);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load dashboard data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, []);

  const filteredVehicles = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return data.vehicles.filter((vehicle) => {
      const matchesText =
        normalized.length === 0 ||
        vehicle.vehicle_id.toLowerCase().includes(normalized) ||
        vehicle.latest_anomaly?.type.toLowerCase().includes(normalized) ||
        vehicle.latest_warning?.type.toLowerCase().includes(normalized);
      const matchesStatus = statusFilter === 'all' || vehicle.status === statusFilter;
      const matchesFreshness = freshnessFilter === 'all' || vehicle.freshness === freshnessFilter;
      return matchesText && matchesStatus && matchesFreshness;
    });
  }, [data.vehicles, freshnessFilter, query, statusFilter]);

  const staleCount = freshnessChartValue(data.vehicles, 'stale');
  const freshCount = freshnessChartValue(data.vehicles, 'fresh');
  const statusChart = Object.entries(data.fleetState).map(([name, value]) => ({
    name,
    label: humanize(name),
    value,
  }));
  const anomalyChart = Object.entries(
    data.anomalies.reduce<Record<string, number>>((acc, anomaly) => {
      acc[anomaly.type] = (acc[anomaly.type] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .map(([name, value]) => ({ name, label: humanize(name), value }))
    .sort((a, b) => b.value - a.value);
  const freshnessChart = Object.entries(
    data.vehicles.reduce<Record<Freshness, number>>(
      (acc, vehicle) => {
        acc[vehicle.freshness] += 1;
        return acc;
      },
      { fresh: 0, stale: 0, never_seen: 0 },
    ),
  ).map(([name, value]) => ({ name, label: humanize(name), value }));
  const topZones = [...data.zoneCounts]
    .sort((a, b) => b.entry_count - a.entry_count)
    .slice(0, 10)
    .map((zone) => ({ ...zone, label: zoneLabel(zone.zone_id) }));

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <Text className="eyebrow">Fleet Telemetry Monitoring Service</Text>
          <Title as="h1" className="page-title">
            Operations Dashboard
          </Title>
        </div>
        <div className="topbar-actions">
          <Text className="timestamp">Updated {lastUpdated ? fmtTime(lastUpdated.toISOString()) : '-'}</Text>
          <Button aria-label="Refresh dashboard" onClick={refresh} isLoading={loading} className="refresh-button">
            <RotateCw size={16} />
          </Button>
        </div>
      </section>

      {error ? (
        <Alert color="danger" className="mb-4">
          API error: {error}
        </Alert>
      ) : null}

      <section className="metrics-grid">
        <MetricCard label="Moving" value={data.fleetState.moving} detail="active vehicles" tone="teal" />
        <MetricCard label="Faulted" value={data.fleetState.fault} detail="needs maintenance" tone="rose" />
        <MetricCard label="Stale" value={staleCount} detail={`${freshCount} reporting fresh`} tone="amber" />
        <MetricCard label="Warnings" value={data.warnings.length} detail="latest 100 window" tone="indigo" />
      </section>

      <section className="chart-grid">
        <ChartPanel title="Fleet Status" detail="Current state distribution" className="status-panel">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={statusChart} dataKey="value" nameKey="label" innerRadius={62} outerRadius={92}>
                {statusChart.map((entry) => (
                  <Cell key={entry.name} fill={statusColors[entry.name]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Zone Entries" detail="Top zones by edge-reported entry count" className="zone-panel">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={topZones} margin={{ top: 8, right: 12, bottom: 40, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-28} textAnchor="end" height={70} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="entry_count" fill="#0f766e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Anomalies" detail="Recent anomaly count by type" className="anomaly-panel">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={anomalyChart} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 72 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} />
              <YAxis dataKey="label" type="category" tick={{ fontSize: 11 }} width={150} />
              <Tooltip />
              <Bar dataKey="value" fill="#be123c" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Freshness" detail="Telemetry freshness across fleet" className="freshness-panel">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={freshnessChart} dataKey="value" nameKey="label" outerRadius={90}>
                {freshnessChart.map((entry) => (
                  <Cell key={entry.name} fill={freshnessColors[entry.name]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartPanel>
      </section>

      <Box className="panel vehicle-panel">
        <div className="vehicle-panel-head">
          <div>
            <Title as="h2" className="panel-title">
              Vehicles
            </Title>
            <Text className="subtle">{filteredVehicles.length} of {data.vehicles.length} vehicles</Text>
          </div>
          <div className="filters">
            <div className="filter-field">
              <Text className="filter-label">Search</Text>
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Vehicle or signal" />
            </div>
            <div className="filter-field">
              <Text className="filter-label">Status</Text>
              <Select
                value={statusOptions.find((option) => option.value === statusFilter)}
                onChange={(option: unknown) => setStatusFilter(selectValue(option))}
                options={statusOptions}
              />
            </div>
            <div className="filter-field">
              <Text className="filter-label">Freshness</Text>
              <Select
                value={freshnessOptions.find((option) => option.value === freshnessFilter)}
                onChange={(option: unknown) => setFreshnessFilter(selectValue(option))}
                options={freshnessOptions}
              />
            </div>
          </div>
        </div>

        <div className="table-wrap">
          <Table variant="minimal" className="vehicle-table">
            <Table.Header>
              <Table.Row>
                <Table.Head>Vehicle</Table.Head>
                <Table.Head>Status</Table.Head>
                <Table.Head>Battery</Table.Head>
                <Table.Head>Speed</Table.Head>
                <Table.Head>Latest</Table.Head>
                <Table.Head>Anomaly</Table.Head>
                <Table.Head>Warning</Table.Head>
                <Table.Head>Freshness</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {filteredVehicles.map((vehicle) => (
                <Table.Row key={vehicle.vehicle_id}>
                  <Table.Cell className="mono">{vehicle.vehicle_id}</Table.Cell>
                  <Table.Cell>
                    <DomainBadge value={vehicle.status} tone="status" />
                  </Table.Cell>
                  <Table.Cell>
                    <BatteryCell value={vehicle.battery_pct} />
                  </Table.Cell>
                  <Table.Cell>{vehicle.speed_mps?.toFixed(1) ?? '-'} m/s</Table.Cell>
                  <Table.Cell>{fmtTime(vehicle.latest_timestamp)}</Table.Cell>
                  <Table.Cell>
                    <DomainBadge value={vehicle.latest_anomaly?.type} tone="anomaly" />
                  </Table.Cell>
                  <Table.Cell>
                    <DomainBadge value={vehicle.latest_warning?.type} tone="warning" />
                  </Table.Cell>
                  <Table.Cell>
                    <DomainBadge value={vehicle.freshness} tone="freshness" />
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </div>
      </Box>
    </main>
  );
}

export default App;
