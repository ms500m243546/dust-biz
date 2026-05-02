"""SQLAlchemy ORM models.

Models materialize the data contracts in docs/data-contracts.md. They
are imported here so `Base.metadata.create_all` sees them in tests
and migrations (migrations land in B.5+).
"""

from app.storage.models.approvals import RecommendationApproval
from app.storage.models.attributions import SourceAttribution
from app.storage.models.audit import AuditLog
from app.storage.models.base import Base
from app.storage.models.dust_events import DustEvent
from app.storage.models.features import FeatureRecord
from app.storage.models.forecasts import DustPrediction
from app.storage.models.ingest_errors import IngestError
from app.storage.models.interventions import InterventionOption
from app.storage.models.mine import Equipment, HaulRoadSegment, Mine, Sensor, Zone
from app.storage.models.mine_state import MineStateSnapshot
from app.storage.models.outcomes import ActionOutcome
from app.storage.models.readings import EquipmentActivity, SensorReading, WeatherReading
from app.storage.models.recommendations import Recommendation
from app.storage.models.simulations import InterventionSimulation
from app.storage.models.site_config import SiteConfiguration
from app.storage.models.users import User

__all__ = [
    "ActionOutcome",
    "AuditLog",
    "Base",
    "DustEvent",
    "DustPrediction",
    "Equipment",
    "EquipmentActivity",
    "FeatureRecord",
    "HaulRoadSegment",
    "IngestError",
    "InterventionOption",
    "InterventionSimulation",
    "Mine",
    "MineStateSnapshot",
    "Recommendation",
    "RecommendationApproval",
    "Sensor",
    "SensorReading",
    "SiteConfiguration",
    "SourceAttribution",
    "User",
    "WeatherReading",
    "Zone",
]
