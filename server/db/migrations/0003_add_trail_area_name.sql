-- Adds the trail's area/park name, sourced from enriched_descriptions'
-- "areaName" field (e.g. "Rattlesnake Point Conservation Area") - already
-- scraped from AllTrails, just never carried past the flat file until now.
-- Nullable: only ~62/68 trails currently on disk have a non-null value.
ALTER TABLE trails ADD COLUMN area_name TEXT;
