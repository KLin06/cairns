-- Adds the three terrainData.soil sub-fields the live conditions-prediction
-- feature assembly needs (server/app/services/feature_flatten.py's
-- flatten_terrain) but that trails.soil_drainage (sourced from a *different*
-- soil field, "drainage") doesn't cover. Lets conditions.py's _load_description
-- read trails instead of enriched_descriptions/{trail_id}.json directly -
-- constitution Principle X: fixed-shape scalar fields, real typed columns,
-- not JSONB.
ALTER TABLE trails ADD COLUMN soil_drainage_rank SMALLINT;
ALTER TABLE trails ADD COLUMN soil_texture_mud_potential SMALLINT;
ALTER TABLE trails ADD COLUMN soil_texture_group TEXT;
