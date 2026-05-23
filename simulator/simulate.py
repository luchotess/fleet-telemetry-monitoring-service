import asyncio
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

ZONES = [
    "inbound_dock_a",
    "inbound_dock_b",
    "receiving_staging",
    "aisle_a",
    "aisle_b",
    "aisle_c",
    "high_bay_1",
    "high_bay_2",
    "bulk_storage",
    "pick_zone_1",
    "pick_zone_2",
    "pack_station",
    "sort_belt",
    "outbound_dock_a",
    "outbound_dock_b",
    "shipping_staging",
    "charging_bay_1",
    "charging_bay_2",
    "charging_bay_3",
    "maintenance_bay",
]

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
VEHICLE_IDS = [f"v-{i}" for i in range(1, 51)]


@dataclass
class VehicleSimState:
    vehicle_id: str
    token: str | None = None
    expires_at: datetime | None = None
    lat: float = field(default_factory=lambda: 37.41 + random.random() * 0.01)
    lon: float = field(default_factory=lambda: -122.08 + random.random() * 0.01)
    battery_pct: int = field(default_factory=lambda: random.randint(35, 95))
    status: str = "idle"
    repeated_fault_code: str | None = None
    repeated_fault_remaining: int = 0


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


async def wait_for_backend(client: httpx.AsyncClient) -> None:
    while True:
        try:
            response = await client.get(f"{BACKEND_URL}/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        print("waiting for backend...")
        await asyncio.sleep(2)


async def ensure_token(client: httpx.AsyncClient, state: VehicleSimState) -> None:
    now = datetime.now(timezone.utc)
    if state.token and state.expires_at and state.expires_at - now > timedelta(minutes=2):
        return

    response = await client.post(
        f"{BACKEND_URL}/auth/vehicle-token",
        json={"vehicle_id": state.vehicle_id},
        timeout=10,
    )
    if response.status_code == 409 and state.token:
        return
    response.raise_for_status()
    body = response.json()
    state.token = body["token"]
    state.expires_at = parse_dt(body["expires_at"])


def choose_status(state: VehicleSimState) -> str:
    if random.random() < 0.015:
        return "fault"
    if state.battery_pct < 18 and random.random() < 0.35:
        return "charging"
    return random.choices(
        ["moving", "idle", "charging"],
        weights=[0.68, 0.22, 0.10],
    )[0]


def build_payload(state: VehicleSimState) -> dict:
    now = datetime.now(timezone.utc)
    status = choose_status(state)
    speed = 0.0
    if status == "moving":
        speed = random.uniform(0.6, 2.2)
        state.lat += random.uniform(-0.000025, 0.000025)
        state.lon += random.uniform(-0.000025, 0.000025)
    elif status == "charging":
        state.battery_pct = min(100, state.battery_pct + random.randint(0, 2))

    if random.random() < 0.02:
        state.lat += random.uniform(0.004, 0.008)
        state.lon += random.uniform(0.004, 0.008)

    if random.random() < 0.025:
        status = random.choice(["idle", "charging"])
        speed = random.uniform(0.8, 2.0)

    if random.random() < 0.025:
        state.battery_pct = max(0, state.battery_pct - random.randint(11, 18))
    elif status != "charging":
        state.battery_pct = max(0, state.battery_pct - random.choice([0, 0, 1]))

    if random.random() < 0.02:
        state.battery_pct = random.randint(5, 14)

    error_codes: list[str] = []
    if state.repeated_fault_remaining <= 0 and random.random() < 0.025:
        state.repeated_fault_code = random.choice(["E_DRIVE", "E_BRAKE", "E_SENSOR"])
        state.repeated_fault_remaining = 3
    if state.repeated_fault_remaining > 0 and state.repeated_fault_code:
        error_codes.append(state.repeated_fault_code)
        state.repeated_fault_remaining -= 1

    if status == "fault" and not error_codes:
        error_codes.append(random.choice(["F_MOTOR", "F_BATTERY", "F_NAV"]))

    state.status = status
    return {
        "vehicle_id": state.vehicle_id,
        "timestamp": now.isoformat(),
        "lat": round(state.lat, 6),
        "lon": round(state.lon, 6),
        "battery_pct": state.battery_pct,
        "speed_mps": round(speed, 2),
        "status": status,
        "error_codes": error_codes,
        "zone_entered": random.choice(ZONES) if random.random() < 0.08 else None,
    }


async def vehicle_loop(client: httpx.AsyncClient, state: VehicleSimState) -> None:
    while True:
        try:
            if random.random() < 0.015:
                await asyncio.sleep(random.uniform(12, 18))

            await ensure_token(client, state)
            payload = build_payload(state)
            response = await client.post(
                f"{BACKEND_URL}/telemetry",
                headers={"Authorization": f"Bearer {state.token}"},
                json=payload,
                timeout=10,
            )
            if response.status_code == 401:
                state.token = None
                state.expires_at = None
            elif response.status_code == 429:
                await asyncio.sleep(1.5)
            else:
                response.raise_for_status()
        except Exception as exc:
            print(f"{state.vehicle_id}: {exc}")
            await asyncio.sleep(2)

        await asyncio.sleep(random.uniform(0.85, 1.15))


async def main() -> None:
    timeout = httpx.Timeout(10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await wait_for_backend(client)
        states = [VehicleSimState(vehicle_id=vehicle_id) for vehicle_id in VEHICLE_IDS]
        print(f"starting simulator for {len(states)} vehicles against {BACKEND_URL}")
        await asyncio.gather(*(vehicle_loop(client, state) for state in states))


if __name__ == "__main__":
    asyncio.run(main())
