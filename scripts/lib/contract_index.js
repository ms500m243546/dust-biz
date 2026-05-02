'use strict';

/**
 * Phase-aware contract expectations.
 *
 * Each entity entry says: at this phase, this entity should have a
 * Pydantic schema (in app.schemas.<module>) and/or a SQLAlchemy model
 * (in app.storage.models). Each repository entry says: this repository
 * class should be importable.
 *
 * Adding entries here is the way to enforce a new contract. The
 * validate-contracts check uses this to confirm implementation
 * matches the documented contracts in docs/data-contracts.md.
 */

const PHASE_B4 = [
  // Static spatial / equipment entities
  { entity: 'Mine',                 schemaModule: 'app.schemas.mine',      schemaClass: 'MineSchema',                model: 'Mine' },
  { entity: 'Zone',                 schemaModule: 'app.schemas.mine',      schemaClass: 'ZoneSchema',                model: 'Zone' },
  { entity: 'HaulRoadSegment',      schemaModule: 'app.schemas.mine',      schemaClass: 'HaulRoadSegmentSchema',     model: 'HaulRoadSegment' },
  { entity: 'Sensor',               schemaModule: 'app.schemas.sensor',    schemaClass: 'SensorSchema',              model: 'Sensor' },
  { entity: 'Equipment',            schemaModule: 'app.schemas.equipment', schemaClass: 'EquipmentSchema',           model: 'Equipment' },
  // Raw immutable readings
  { entity: 'SensorReading',        schemaModule: 'app.schemas.sensor',    schemaClass: 'RawSensorReadingSchema',    model: 'SensorReading' },
  { entity: 'WeatherReading',       schemaModule: 'app.schemas.weather',   schemaClass: 'RawWeatherReadingSchema',   model: 'WeatherReading' },
  { entity: 'EquipmentActivity',    schemaModule: 'app.schemas.equipment', schemaClass: 'RawEquipmentActivitySchema', model: 'EquipmentActivity' },
  // Subsystem outputs that are schema-only at B.4 (no DB rows yet)
  { entity: 'SensorHealthStatus',   schemaModule: 'app.schemas.sensor',    schemaClass: 'SensorHealthStatusSchema',  model: null },
];

const PHASE_C = [
  { entity: 'IngestError',          schemaModule: 'app.schemas.ingest_errors', schemaClass: 'IngestErrorSchema',     model: 'IngestError' },
];

const PHASE_D = [
  { entity: 'SiteConfiguration',    schemaModule: 'app.schemas.site_config',   schemaClass: 'SiteConfigSchema',      model: 'SiteConfiguration' },
  { entity: 'MineStateSnapshot',    schemaModule: 'app.schemas.mine_state',    schemaClass: 'MineStateZoneSchema',   model: 'MineStateSnapshot' },
];

const PHASE_E = [
  { entity: 'FeatureRecord',        schemaModule: 'app.schemas.features',      schemaClass: 'FeatureRecordSchema',   model: 'FeatureRecord' },
  { entity: 'DustForecast',         schemaModule: 'app.schemas.forecasts',     schemaClass: 'DustForecastSchema',    model: null },
  { entity: 'DustPrediction',       schemaModule: 'app.schemas.forecasts',     schemaClass: 'DustForecastSchema',    model: 'DustPrediction' },
];

const PHASE_F = [
  { entity: 'DustEvent',            schemaModule: 'app.schemas.dust_events',   schemaClass: 'DustEventSchema',           model: 'DustEvent' },
  { entity: 'SourceAttribution',    schemaModule: 'app.schemas.attributions',  schemaClass: 'SourceAttributionSchema',   model: 'SourceAttribution' },
];

const PHASE_G = [
  { entity: 'InterventionOption',     schemaModule: 'app.schemas.interventions', schemaClass: 'InterventionOptionSchema',     model: 'InterventionOption' },
  { entity: 'InterventionSimulation', schemaModule: 'app.schemas.simulations',   schemaClass: 'InterventionSimulationSchema', model: 'InterventionSimulation' },
];

const PHASE_H = [
  { entity: 'Recommendation',         schemaModule: 'app.schemas.recommendations', schemaClass: 'RecommendationSchema',       model: 'Recommendation' },
];

const PHASE_I = [
  { entity: 'User',                    schemaModule: 'app.schemas.auth',      schemaClass: 'UserSchema',                    model: 'User' },
  { entity: 'RecommendationApproval',  schemaModule: 'app.schemas.approvals', schemaClass: 'RecommendationApprovalSchema',  model: 'RecommendationApproval' },
  // AuditLog is repo-only at I (no Pydantic wire schema yet); the
  // AuditLogRepository entry below covers the contract-presence check.
  { entity: 'ActionOutcome',           schemaModule: 'app.schemas.outcomes',  schemaClass: 'ActionOutcomeSchema',           model: 'ActionOutcome' },
];

const PHASE_K = [
  { entity: 'TrainingRecord',           schemaModule: 'app.schemas.model_performance', schemaClass: 'TrainingRecordSchema',           model: null },
  { entity: 'ModelPerformanceMetric',   schemaModule: 'app.schemas.model_performance', schemaClass: 'ModelPerformanceMetricSchema',   model: 'ModelPerformanceMetric' },
];

const REPOSITORIES = [
  { name: 'SensorReadingRepository',         module: 'app.storage.repositories.sensor_readings' },
  { name: 'WeatherReadingRepository',        module: 'app.storage.repositories.weather_readings' },
  { name: 'EquipmentActivityRepository',     module: 'app.storage.repositories.equipment_activity' },
  { name: 'IngestErrorRepository',           module: 'app.storage.repositories.ingest_errors' },
  { name: 'SiteConfigRepository',            module: 'app.storage.repositories.site_config' },
  { name: 'ZoneRepository',                  module: 'app.storage.repositories.zones' },
  { name: 'HaulRoadSegmentRepository',       module: 'app.storage.repositories.haul_road_segments' },
  { name: 'MineStateSnapshotRepository',     module: 'app.storage.repositories.mine_state' },
  { name: 'FeatureRepository',               module: 'app.storage.repositories.features' },
  { name: 'DustPredictionRepository',        module: 'app.storage.repositories.forecasts' },
  { name: 'DustEventRepository',             module: 'app.storage.repositories.dust_events' },
  { name: 'SourceAttributionRepository',     module: 'app.storage.repositories.attributions' },
  { name: 'InterventionOptionRepository',    module: 'app.storage.repositories.interventions' },
  { name: 'InterventionSimulationRepository', module: 'app.storage.repositories.simulations' },
  { name: 'RecommendationRepository',         module: 'app.storage.repositories.recommendations' },
  { name: 'UserRepository',                   module: 'app.storage.repositories.users' },
  { name: 'RecommendationApprovalRepository', module: 'app.storage.repositories.approvals' },
  { name: 'AuditLogRepository',               module: 'app.storage.repositories.audit' },
  { name: 'ActionOutcomeRepository',          module: 'app.storage.repositories.outcomes' },
  { name: 'ModelPerformanceMetricRepository', module: 'app.storage.repositories.model_performance' },
];

const ENTITIES = [...PHASE_B4, ...PHASE_C, ...PHASE_D, ...PHASE_E, ...PHASE_F, ...PHASE_G, ...PHASE_H, ...PHASE_I, ...PHASE_K];

module.exports = { PHASE_B4, PHASE_C, PHASE_D, PHASE_E, PHASE_F, PHASE_G, PHASE_H, PHASE_I, PHASE_K, ENTITIES, REPOSITORIES };
