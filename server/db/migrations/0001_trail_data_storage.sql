-- Mirrors specs/002-trail-data-storage-schema/contracts/schema.sql - keep both
-- in sync if either is edited (see that file for column-by-column rationale).
--
-- Trail Data Storage Schema
-- Three independently refreshable tables (spec FR-011): updating trail_activity
-- or trail_geometry never requires touching trails, and vice versa.

CREATE TABLE trails (
    trail_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude            DOUBLE PRECISION NOT NULL,
    difficulty_rating   INTEGER,
    length_meters       DOUBLE PRECISION,
    duration_minutes    INTEGER,
    has_scrambling      BOOLEAN NOT NULL,
    rock_slip_risk      TEXT,
    soil_drainage       TEXT,
    surface_types       JSONB,
    features            JSONB,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT surface_types_is_array
        CHECK (surface_types IS NULL OR jsonb_typeof(surface_types) = 'array'),
    CONSTRAINT features_is_array
        CHECK (features IS NULL OR jsonb_typeof(features) = 'array')
);

CREATE TABLE trail_activity (
    trail_id          TEXT PRIMARY KEY REFERENCES trails (trail_id) ON DELETE CASCADE,
    by_month          JSONB NOT NULL,
    by_day_of_week    JSONB NOT NULL,
    total_reviews     INTEGER NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT by_month_is_object
        CHECK (jsonb_typeof(by_month) = 'object'),
    CONSTRAINT by_day_of_week_is_object
        CHECK (jsonb_typeof(by_day_of_week) = 'object'),
    CONSTRAINT total_reviews_non_negative
        CHECK (total_reviews >= 0)
);

CREATE TABLE trail_geometry (
    trail_id     TEXT PRIMARY KEY REFERENCES trails (trail_id) ON DELETE CASCADE,
    geometry     JSONB NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT geometry_is_object
        CHECK (jsonb_typeof(geometry) = 'object')
);

-- Supports SC-002 (map marker data retrievable without loading full detail data)
-- for spatial-ish bounding queries later; harmless even before that's needed.
CREATE INDEX idx_trails_location ON trails (latitude, longitude);
