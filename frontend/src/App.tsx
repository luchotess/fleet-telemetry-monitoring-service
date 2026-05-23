import { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Button, Card, Input, Select, Table, Text, Title } from 'rizzui';
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
  return value.replaceAll('_', ' ');
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: 'neutral' | 'teal' | 'rose' | 'amber' | 'indigo';
}) {
  return (
    <Card className={`metric-card tone-${tone ?? 'neutral'}`}>
      <Text className="metric-label">{label}</Text>
      <Title as="h3" className="metric-value">
        {value}
      </Title>
    </Card>
  );
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

  const statusChart = Object.entries(data.fleetState).map(([name, value]) => ({ name, value }));
  const anomalyChart = Object.entries(
    data.anomalies.reduce<Record<string, number>>((acc, anomaly) => {
      acc[anomaly.type] = (acc[anomaly.type] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  const freshnessChart = Object.entries(
    data.vehicles.reduce<Record<Freshness, number>>(
      (acc, vehicle) => {
        acc[vehicle.freshness] += 1;
        return acc;
      },
      { fresh: 0, stale: 0, never_seen: 0 },
    ),
  ).map(([name, value]) => ({ name, value }));
  const topZones = [...data.zoneCounts].sort((a, b) => b.entry_count - a.entry_count).slice(0, 10);

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
        <MetricCard label="Moving" value={data.fleetState.moving} tone="teal" />
        <MetricCard label="Faulted" value={data.fleetState.fault} tone="rose" />
        <MetricCard label="Stale" value={freshnessChart.find((item) => item.name === 'stale')?.value ?? 0} tone="amber" />
        <MetricCard label="Warnings" value={data.warnings.length} tone="indigo" />
      </section>

      <section className="chart-grid">
        <Card className="panel">
          <Title as="h2" className="panel-title">
            Fleet Status
          </Title>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={statusChart} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88}>
                {statusChart.map((entry) => (
                  <Cell key={entry.name} fill={statusColors[entry.name]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card className="panel">
          <Title as="h2" className="panel-title">
            Zone Entries
          </Title>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={topZones}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="zone_id" tick={{ fontSize: 11 }} interval={0} angle={-22} textAnchor="end" height={64} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="entry_count" fill="#0f766e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="panel">
          <Title as="h2" className="panel-title">
            Anomalies
          </Title>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={anomalyChart} layout="vertical" margin={{ left: 36 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} width={112} />
              <Tooltip />
              <Bar dataKey="value" fill="#be123c" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="panel">
          <Title as="h2" className="panel-title">
            Freshness
          </Title>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={freshnessChart} dataKey="value" nameKey="name" outerRadius={88}>
                {freshnessChart.map((entry) => (
                  <Cell key={entry.name} fill={freshnessColors[entry.name]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </section>

      <Card className="panel vehicle-panel">
        <div className="vehicle-panel-head">
          <div>
            <Title as="h2" className="panel-title">
              Vehicles
            </Title>
            <Text className="subtle">{filteredVehicles.length} of {data.vehicles.length} vehicles</Text>
          </div>
          <div className="filters">
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search vehicles" />
            <Select
              value={statusFilter}
              onChange={(option: { value: string } | null) => setStatusFilter(option?.value ?? 'all')}
              options={[
                { label: 'All status', value: 'all' },
                { label: 'Idle', value: 'idle' },
                { label: 'Moving', value: 'moving' },
                { label: 'Charging', value: 'charging' },
                { label: 'Fault', value: 'fault' },
              ]}
            />
            <Select
              value={freshnessFilter}
              onChange={(option: { value: string } | null) => setFreshnessFilter(option?.value ?? 'all')}
              options={[
                { label: 'All freshness', value: 'all' },
                { label: 'Fresh', value: 'fresh' },
                { label: 'Stale', value: 'stale' },
                { label: 'Never seen', value: 'never_seen' },
              ]}
            />
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
                    <Badge color={badgeColors[vehicle.status]}>{humanize(vehicle.status)}</Badge>
                  </Table.Cell>
                  <Table.Cell>{vehicle.battery_pct ?? '-'}%</Table.Cell>
                  <Table.Cell>{vehicle.speed_mps?.toFixed(1) ?? '-'} m/s</Table.Cell>
                  <Table.Cell>{fmtTime(vehicle.latest_timestamp)}</Table.Cell>
                  <Table.Cell>{humanize(vehicle.latest_anomaly?.type)}</Table.Cell>
                  <Table.Cell>{humanize(vehicle.latest_warning?.type)}</Table.Cell>
                  <Table.Cell>
                    <Badge color={badgeColors[vehicle.freshness]}>{humanize(vehicle.freshness)}</Badge>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </div>
      </Card>
    </main>
  );
}

export default App;
