from sqlalchemy.orm import Session

from app.core.constants import ZONES
from app.db.models import Vehicle, ZoneCount


def seed_reference_data(db: Session) -> None:
    for i in range(1, 51):
        vehicle_id = f"v-{i}"
        if db.get(Vehicle, vehicle_id) is None:
            db.add(Vehicle(vehicle_id=vehicle_id, status="idle"))

    for zone_id in ZONES:
        if db.get(ZoneCount, zone_id) is None:
            db.add(ZoneCount(zone_id=zone_id, entry_count=0))

    db.commit()
