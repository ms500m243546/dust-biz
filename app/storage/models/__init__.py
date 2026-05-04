"""SQLAlchemy ORM models.

Models materialize the data contracts in docs/data-contracts.md. They
are imported here so `Base.metadata.create_all` sees them in tests
and migrations (migrations land in B.5+).
"""

from app.storage.models.approvals import RecommendationApproval
from app.storage.models.attributions import SourceAttribution
from app.storage.models.audit import AuditLog
from app.storage.models.base import Base
from app.storage.models.dispersion import DispersionMatrix
from app.storage.models.dust_events import DustEvent
from app.storage.models.features import FeatureRecord
from app.storage.models.forecasts import DustPrediction
from app.storage.models.ingest_errors import IngestError
from app.storage.models.interventions import InterventionOption
from app.storage.models.mine import Equipment, HaulRoadSegment, Mine, Sensor, Zone
from app.storage.models.mine_state import MineStateSnapshot
from app.storage.models.model_performance import ModelPerformanceMetric
from app.storage.models.outcomes import ActionOutcome
from app.storage.models.readings import EquipmentActivity, SensorReading, WeatherReading
from app.storage.models.receptor import PopulatedPlace
from app.storage.models.recommendations import Recommendation
from app.storage.models.road_silt import HaulRoadSegmentSilt
from app.storage.models.simulations import InterventionSimulation
from app.storage.models.site_config import SiteConfiguration
from app.storage.models.station_thresholds import StationThresholdOverride
from app.storage.models.users import User

__all__ = [
    "ActionOutcome",
    "AuditLog",
    "Base",
    "DispersionMatrix",
    "DustEvent",
    "DustPrediction",
    "Equipment",
    "EquipmentActivity",
    "FeatureRecord",
    "HaulRoadSegment",
    "HaulRoadSegmentSilt",
    "IngestError",
    "InterventionOption",
    "InterventionSimulation",
    "Mine",
    "MineStateSnapshot",
    "ModelPerformanceMetric",
    "PopulatedPlace",
    "Recommendation",
    "RecommendationApproval",
    "Sensor",
    "SensorReading",
    "SiteConfiguration",
    "SourceAttribution",
    "StationThresholdOverride",
    "User",
    "WeatherReading",
    "Zone",
]
