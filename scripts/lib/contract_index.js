'use strict';

/**
 * Phase-aware contract expectations.
 *
 * Each entry says: at this phase, this entity should have a Pydantic
 * schema (in app.schemas.<module>) and/or a SQLAlchemy model (in
 * app.storage.models). Adding entries here is the way to enforce a
 * new contract.
 *
 * The validate-contracts check uses this to confirm the implementation
 * matches the documented contracts in docs/data-contracts.md without
 * hand-curated mass parsing.
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

module.exports = { PHASE_B4 };
