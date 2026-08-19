<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0
- Modified principles: none (additive amendment)
- Added sections:
  - Core Principles IX (Selective Field Storage), X (Scoped JSONB Usage)
- Removed sections: none
- Deferred items: none
- Rationale for MINOR bump: two new principles added ahead of introducing a
  Postgres-backed trail data store; no existing principle was redefined or
  removed.
-->

# Trail Conditions App Constitution

## Core Principles

### I. Endpoint Separation: Weather-Dependent vs Static Computation
Conditions (weather-dependent: requires a live forecast call plus model
inference) and trail info (static: computed once from historical
review/description data, cacheable indefinitely) MUST remain distinct
endpoints and distinct code paths. They MUST NOT be merged into a single
computation or a single handler, even when it would be convenient to
return both from one call.
Rationale: the two have entirely different cost, latency, and cache
characteristics. Merging them forces every static-info read to pay for a
live forecast fetch and model inference it doesn't need.

### II. Feature Parity Between Training and Inference
The backend's feature assembly for live model inference MUST produce a
column-for-column identical structure — same columns, same order, same
dtypes, same categorical handling — to what `build_training_table.py`
produces when building the training table for `condition_models.joblib`.
This flattening logic MUST be factored into a single shared implementation
used by both the offline table-builder and the live backend. It MUST NOT
be reimplemented separately for training vs. inference.
Rationale: silent drift between training-time and inference-time feature
construction is the single most likely source of a model that trains
cleanly but predicts garbage in production, and it fails silently.

### III. Forecast Horizon as a Hard Boundary
Open-Meteo's forecast endpoint extends roughly 16 days out. Requests for
conditions on a date beyond that window MUST be explicitly rejected with a
clear error. Silent degradation, estimation, or seasonal-average fallback
in place of a rejected out-of-range request is NOT permitted without an
explicit, separately-specified feature for it.
Rationale: a confidently-returned guess dressed up as a forecast-backed
prediction is worse than an honest "can't answer that yet," given the
app's purpose is safety-relevant trip planning.

### IV. Shared Date State Across the UI
Within the trail detail panel, the selected date is a single piece of
shared state. The weather strip, the best-days chart, and the date picker
MUST all read from and write to that same state. Selecting a date in any
one of them MUST update the other two; none of them may maintain
independent, disconnected date state.
Rationale: these three surfaces are the same interaction viewed from
different angles (per APP_SPEC.md's "Day selection" section) — divergent
state would make the panel internally inconsistent.

### V. Single Continuous Scroll, No Tabbed Navigation
The trail detail panel is one continuous scrollable surface. Sections
(Overview, Weather, Day selection) are scroll-anchored, not tab-routed.
New panel content MUST be added as another scroll section, not as a new
tab or a separate routed view. A lightweight sticky jump-nav MAY be added
later if scroll length becomes a real problem, but tabs specifically MUST
NOT replace this structure.
Rationale: tabs here would only function as scroll-jump anchors with added
state-management cost; a plain scroll achieves the same outcome for less
complexity.

### VI. Popularity Granularity Honesty
Monthly/seasonal aggregation of historical review dates is treated as a
reliable signal and MAY be presented as a standalone claim (e.g., a
monthly bar chart). Day-of-week aggregation is a lower-confidence
secondary signal and MUST only be surfaced anchored to real, specific
upcoming dates (e.g., layered onto the best-days strip) — it MUST NOT be
presented as a standalone claim (e.g., a bare "Saturdays are busiest"
chart).
Rationale: review post-date lags actual hike date by up to several weeks,
which smears day-of-week granularity specifically; monthly granularity is
robust to that lag.

### VII. Pipeline-Gated Trail Data
Only trails that have completed the full scrape/clean/enrich pipeline are
addressable through the app's trail endpoints or shown as queryable map
markers. The app MUST NOT query live external POI sources (e.g. OSM's own
trail/POI data) as a source of trail identity or additional markers.
Rationale: AllTrails trail IDs and OSM identifiers are not reconcilable;
pulling in arbitrary external trails would produce markers with no
`trailId` to query conditions for — dead ends by construction.

### VIII. Honest Uncertainty in Predictions
Any condition prediction returned to the client MUST be accompanied by a
confidence or data-availability signal (e.g., the historical review count
backing that trail's model, or an explicit "limited data" flag for thin
trails). Probabilities MUST NOT be presented as unqualified certainty.
Rationale: the model is real but imperfect and trained on unevenly
distributed review volume; presenting a bare probability without context
overstates what the app actually knows about a given trail.

### IX. Selective Field Storage
Trail data storage MUST hold only the fields the application actually
consumes — selectively extracted from whichever pipeline stage
(`raw_descriptions`, `cleaned_descriptions`, or `enriched_descriptions`)
originates them. It MUST NOT be a wholesale dump of a pipeline stage's
full JSON output into the database. If a field from any stage isn't read
by a backend service or displayed on the frontend, it does not belong in
storage.
Rationale: storing whole pipeline artifacts "just in case" would recreate
the same flat-file sprawl this migration exists to fix, just inside a
database instead of on disk — and every unused field is a schema-drift
risk with no offsetting value.

### X. Scoped JSONB Usage
JSON/JSONB columns are reserved for fields that are genuinely irregular
or variable in shape (e.g. route coordinates/geometry, variable-length
tag or feature lists) — not a dumping ground for anything merely
inconvenient to model as typed columns. Any field with a fixed,
predictable shape (name, difficulty rating, length, latitude/longitude)
MUST be a real typed column, not JSONB.
Rationale: JSONB that could have been a typed column loses indexing,
constraints, and query ergonomics for no structural reason — its use
should be a deliberate response to genuine shape irregularity, not a
default.

## Data & Pipeline Integrity

Trail data flows through a fixed pipeline: scrape (AllTrails) → clean →
enrich (description, review, terrain, weather) → label → build training
table → train model. Any new signal or field added to the pipeline (a new
enrichment source, a new label, a new terrain attribute) MUST be added at
its actual pipeline stage and MUST propagate through every downstream
stage that depends on it (cleaned data → enriched data → training table →
model → live inference feature assembly), rather than being bolted on
only at the point where it's currently needed. Partial propagation that
leaves training-time and inference-time feature sets out of sync is a
violation of Principle II above.

## Governance

This constitution supersedes ad hoc practice for anything it addresses.
Amendments are made by editing this file directly (via `/speckit-constitution`
or a direct edit), and MUST update the version number and the Sync Impact
Report at the top of the file in the same change.

Versioning policy (semantic):
- MAJOR: a principle is removed or redefined in a backward-incompatible way.
- MINOR: a new principle or section is added, or existing guidance is
  materially expanded.
- PATCH: wording, clarification, or non-semantic fixes.

Every `/speckit-plan` and `/speckit-analyze` run should be checked against
these principles; a plan that violates one of them needs either a spec
change (dropping the requirement that causes the conflict) or an explicit,
documented exception — not a silent workaround in `plan.md`.

**Version**: 1.1.0 | **Ratified**: 2026-08-18 | **Last Amended**: 2026-08-18
