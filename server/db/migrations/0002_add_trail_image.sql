-- Adds the trail's primary photo, sourced from enriched_descriptions'
-- "images" array (the first URL) - already scraped from AllTrails by the
-- pipeline, just never carried past the flat file until now. Nullable:
-- every trail backfilled so far has at least one image, but a future trail
-- legitimately might not.
ALTER TABLE trails ADD COLUMN image_url TEXT;
