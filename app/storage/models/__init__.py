"""SQLAlchemy ORM models.

Models materialize the data contracts in docs/data-contracts.md. They
are imported here so `Base.metadata.create_all` sees them in tests
and migrations (migrations land in B.5+).
"""

from app.storage.models.base import Base
from app.storage.models.mine import Equipment, HaulRoadSegment, Mine, Sensor, Zone
from app.storage.models.readings import EquipmentActivity, SensorReading, WeatherReading

__all__ = [
    "Base",
    "Equipment",
    "EquipmentActivity",
    "HaulRoadSegment",
    "Mine",
    "Sensor",
    "SensorReading",
    "WeatherReading",
    "Zone",
]
