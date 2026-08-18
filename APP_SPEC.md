# Trail Conditions App — Spec

## Goal

A client calls the backend with a trail + a target date (today through
however far the weather forecast reaches). The backend predicts trail
conditions for that date (mud, ice, snow, slippery, flooded, bugs, dusty)
using the pretrained model, and separately returns static trail
information (difficulty, scrambling, length, etc.) that doesn't depend on
weather at all.

Two different kinds of output, from two different kinds of computation -
keep them conceptually (and probably as separate endpoints) apart:

- **Conditions** - weather-dependent, changes every day, requires a live
  forecast call and model inference.
- **Trail info** - static, computed once per trail from historical
  review/description data, cacheable indefinitely (until the trail is
  re-enriched).

## Problem

Trail difficulty ratings on platforms like AllTrails and provincial park
sites are static labels, often set by people with different levels of
experience, and rarely reflect current conditions. A trail rated
"moderate" in dry August can turn dangerous after spring snowmelt, heavy
rain, or an early snowfall at elevation, since factors like mud, swollen
stream crossings, and ice on switchbacks aren't captured anywhere in the
rating. Hikers planning trips weeks or months in advance have no reliable
way to know if a trail's actual difficulty on their planned date will
match the label, which leads to underpreparation and avoidable risk on
routes that looked fine on paper.

## Who this is for

- **Solo/beginner hikers** planning ahead who can't personally translate
  "40% chance of rain 3 days out" into "will this trail be dangerous" -
  the primary persona given the problem above.
- **Trip/group leaders** booking weeks out for a group with mixed
  experience, who need a defensible answer for "is this still doable"
  rather than just vibes.
- **Trail runners/mountain bikers** - the same conditions (mud, ice)
  matter differently to them than to hikers; a plausible v2 audience with
  different threshold framing, not necessarily v1 scope.

## Architecture

```
Client
  |
  v
Backend (server/)
  |-- GET /trails/:id/info        -> static trail info (no model, no forecast)
  |-- GET /trails/:id/conditions?date=YYYY-MM-DD
  |     |
  |     |-- 1. look up trail's cleaned/enriched description (lat/lng, terrain)
  |     |-- 2. fetch weather forecast for [date-7, date] from Open-Meteo
  |     |-- 3. assemble the exact feature vector the model was trained on
  |     |-- 4. run each condition's HistGradientBoostingClassifier.predict_proba()
  |     `-- 5. return per-condition probabilities
  v
Pretrained model (data/datasets/models/condition_models.joblib)
```

## API contract (draft - not final, this is what spec-driven dev is for)

### `GET /trails/:trailId/conditions?date=YYYY-MM-DD`

Request:
- `trailId` - AllTrails trail ID, must have gone through the full
  scrape/clean/enrich pipeline (cleaned_descriptions +
  enriched_descriptions must exist).
- `date` - defaults to today. Must be within Open-Meteo's forecast
  window (see "Forecast horizon" below) - reject dates too far out
  rather than silently degrading.

Response (draft shape):
```json
{
  "trailId": "10268327",
  "date": "2026-08-20",
  "conditions": {
    "muddy":    { "probability": 0.62, "predicted": true },
    "icy":      { "probability": 0.03, "predicted": false },
    "snow":     { "probability": 0.01, "predicted": false },
    "slippery": { "probability": 0.41, "predicted": false },
    "flooded":  { "probability": 0.05, "predicted": false },
    "bugs":     { "probability": 0.71, "predicted": true },
    "dusty":    { "probability": 0.02, "predicted": false }
  },
  "modelVersion": "2026-08-14-v1"
}
```

- `probability`: raw `predict_proba` output, 0-1.
- `predicted`: `probability >= threshold` (0.5 to start; per-condition
  thresholds are a tuning question, not a v1 concern - imbalanced
  conditions like `dusty` may want a different cutoff than `muddy`).
- `modelVersion`: which trained model produced this, so the client (and
  you, debugging) can tell when predictions shift because of a retrain vs.
  a genuine conditions change. Ties to whatever versioning scheme
  `train_model.py` ends up using for its saved `.joblib` file.

### `GET /trails/:trailId/info`

Static, no weather/model involved - safe to cache aggressively.

Response (draft shape):
```json
{
  "trailId": "10268327",
  "name": "Track and Tower Trail",
  "difficultyRating": 3,
  "lengthMeters": 8368.568,
  "durationMinutes": 145,
  "hasScrambling": true,
  "surfaceTypes": [
    { "label": "natural", "percentOfSurface": 99.33 },
    { "label": "gravel", "percentOfSurface": 0.67 }
  ],
  "terrain": {
    "rockSlipRisk": "moderate",
    "soilDrainage": "imperfect"
  },
  "features": ["Fee required", "Forests", "Lakes"]
}
```

- `hasScrambling`: derived from historical review data (what fraction of
  a trail's reviews/AllTrails tags mention scrambling), not predicted -
  see "Open questions" below for how exactly to compute/threshold this.

### `GET /trails/:trailId/weather`

Exposes the raw forecast the conditions model consumes, for the Weather
UI section below - not currently surfaced anywhere; `conditions` only
returns the *derived* probabilities today. Backed by the same
`fetch_forecast_with_history` call `conditions` already makes
internally, just returned as-is instead of getting fed into the model -
one Open-Meteo call, two consumers, so this should share the fetch/cache
with `conditions` rather than doubling the upstream calls per page load.

Response (draft shape) - full ~16-day forecast window, not scoped to one
date, since the UI's weather mini-strip spans the same range as the date
picker:
```json
{
  "trailId": "10268327",
  "days": [
    {
      "date": "2026-08-20",
      "tempMaxC": 24.1,
      "tempMinC": 12.3,
      "precipMm": 3.2,
      "windMaxKmh": 18.4,
      "snowCm": 0.0
    }
  ]
}
```

## UI / Frontend

### App sidebar (persistent, app-level navigation - not trail-level)

A left sidebar, always present, for the sections that sit above any
single trail: **Explore (the map)**, **Saved**, **Favorited**, **Plans**.
This is the actual Google Maps sidebar pattern - the real one holds
search/saved-places/your-lists, separate from whatever place card happens
to be open. Switching sidebar sections is real navigation (different app
state - "your saved trails" isn't "a trail's detail"), unlike anything
inside the trail detail panel below, which is all one scrollable surface,
not navigation.

### Trail discovery (persistent map, unchanged behind everything else)

Map-based browsing via OpenStreetMap tiles, rendered with MapLibre GL JS
(free, no API key, WebGL vector rendering - not a raw tile-image embed).
Picked over Leaflet because the map needs to draw more than static pins
eventually (trail route lines, condition-severity overlays); MapLibre
handles that natively where Leaflet needs plugins bolted on. One marker
per trail already in the pipeline, placed using `trail_latitude`/
`trail_longitude` from that trail's `cleaned_descriptions` - not a live
query against OSM's own hiking-trail/POI data. That distinction matters:
OSM trail data and AllTrails trail IDs aren't the same identifiers, and
only trails that have actually been through scrape/clean/enrich have
predictions available, so pulling in arbitrary OSM trails would mean a
chunk of markers on the map lead nowhere (no `trailId` to query
conditions for). Filtering/search (by difficulty, by name) can layer on
top of the same marker set later without needing a different data source.

The map is the **default view under the Explore sidebar section** - it's
not replaced by navigation, only ever partially covered. Clicking a
marker doesn't route anywhere; it opens the trail detail panel described
below alongside it. Dismissing the panel returns to exactly the map state
the user left, no reload.

### Trail detail: side panel over the map, single continuous scroll

Clicking a marker opens a **side panel** (docked to the map's edge, not a
bottom sheet) that appears at **full height immediately** - no
grow/drag-to-expand animation, it's there at full height on the first
frame, map remains visible and interactive in the remaining space.
Everything below is **one scrollable surface, no tabs** - tabs would've
mostly just been scroll-jump anchors anyway, so a plain scroll gets
the same result with less state to manage. Sections, in scroll order:

1. **Overview** - general information + popularity. Static trail info
   from `GET /trails/:id/info` (name, AllTrails difficulty, length,
   duration, surface type mix, feature chips) followed by the popularity
   chart - monthly bars (the trustworthy granularity per the caveat
   below). Nothing here depends on a selected date or a live forecast
   call, so it's what's visible immediately when the panel opens, before
   anything else has to load.
2. **Weather** - weather forecast + forecasted conditions, i.e. the raw
   data and the model's read of it, together since one explains the
   other. Raw side: temp high/low, precip, wind, snow for the selected
   date and the `[date-7, date]` window feeding the model (per the
   architecture above) - a day-by-day mini forecast strip across that
   window. Derived side, right below it: headline (static vs.
   conditions-adjusted rating), per-condition breakdown with severity
   color, "why" behind each flagged condition tying back to the raw
   numbers just shown above it, gear/prep nudges, confidence signal
   ("based on 975 historical reports"). Keeping raw and derived together
   is what makes the "why" checkable instead of a black box.
3. **Day selection** - the date-strip picker (see below) plus the 16-day
   best-days chart, together since they're the same interaction from two
   angles: picking a date, and seeing which dates are best. Day-of-week
   popularity layers onto this chart too (not a separate chart), since
   it's only meaningful anchored to real upcoming dates rather than a
   bare "Saturdays are busy" claim. Picking a day here updates the
   selected date used by the Weather section above (scrolls back up to
   it, or re-renders it in place without losing the user's scroll
   position - avoid making this feel like navigation).

If in practice these three sections end up long enough that reaching Day
selection means a lot of scrolling, a lightweight sticky mini-nav (small
jump pills, not full tabs) can be layered on later without changing this
structure - worth deferring until it's an actual problem rather than
building it preemptively.

### Date picker

A native calendar/month-grid picker is the wrong tool: the valid range is
exactly ~16 days from today (the forecast horizon), so a month grid would
render mostly disabled days - confusing, and wasteful of space in a side
panel that's already narrow. Instead: a **horizontal scrollable
day-strip** - today plus the next ~15 days as tappable pills, swipe/arrow
to scroll, selected day highlighted. This is the same component the
best-days chart and the weather mini-strip already need (a strip of ~16
days), just re-skinned per section - best days colors each pill by
conditions favorability, weather shows a temp/precip icon per pill, the
picker itself just marks today/selected. Tapping a pill in any of the
three drives the same selected-date state, shared across the whole panel.

### Gear/prep nudges

Turns a prediction into action instead of just information: if icy is
likely → "microspikes recommended." If muddy → "waterproof boots." If
buggy → "bring repellent." Directly targets the "underpreparation"
named in the problem statement - a probability alone doesn't change
behavior, a concrete prep suggestion does.

### Confidence/data-availability signal

Since this is a real (imperfect) model trained on review volume that
varies a lot by trail, something like "based on 975 historical reports
for this trail" (or a "limited data" flag for thin trails) keeps trust
calibrated instead of presenting a probability as certain.

## Trail activity / popularity

Not a model - just aggregation. `reviewCount`/`popularity` (from
`cleaned_descriptions`) are single static numbers per trail, useless for
"which day is busiest." What's actually useful is already sitting in
every trail's cleaned/enriched reviews: the per-review `date`. Bucketing
those historical review dates by month and by day-of-week gives a real
empirical activity pattern for free, no training required - "this trail
gets 3x the traffic on weekends," "July-August is peak season, tapers
off by October."

**Caveat worth keeping in mind:** review *post* date lags the actual hike
date by anywhere from same-day to a few weeks (the same imprecision
that drove `dayOfYear`/`use_recording_date` decisions in the enrichment
pipeline - see `enrich_data`'s docstring). That smears day-of-week
granularity - someone who hiked Saturday might post Tuesday - so
**monthly/seasonal popularity is trustworthy, day-of-week popularity is
directionally right but noisier.** Lead with season, treat day-of-week as
a lower-confidence secondary signal.

### Possible endpoint

`GET /trails/:trailId/activity` - static-ish (recompute whenever the
trail's reviews are re-enriched, not per-request), returns review counts
bucketed by month and by day-of-week:
```json
{
  "trailId": "10268327",
  "byMonth": { "1": 12, "2": 9, "...": "...", "8": 210 },
  "byDayOfWeek": { "Mon": 40, "...": "...", "Sat": 190, "Sun": 175 },
  "totalReviews": 975
}
```

### UI placement

Two places, following the same preview-on-main/press-into-full pattern
as the rest of the core screen:

Lives in the trail detail sheet (see above) as its own scrolled-to
section, not a separate screen:

- **Monthly bars** (12 bars, one per month) is the section's main chart -
  the trustworthy granularity per the caveat above, "this trail peaks in
  summer" without needing to be anchored to specific upcoming dates.
- **Day-of-week doesn't get its own chart.** It layers onto the best-days
  section instead (next ~16 days, conditions favorability + activity
  level on the same strip) - that's the only place day-of-week noise is
  acceptable, because it's anchored to real upcoming dates rather than a
  bare "Saturdays are busy" claim. This is where the interesting conflict
  shows up: "conditions are great this weekend, but it'll be packed -
  Tuesday is nearly as good and much quieter."

## Feature reconstruction at inference time

This is the part most likely to bite if not handled carefully: the model
was trained on columns produced by `build_training_table.py`
(`weather_d0_tempMax` ... `weather_d7_windMax`, `dayOfYear`,
`terrain_rockSlipRisk`, etc.), sourced from **historical** weather
(`fetch_historical_weather`/`fetch_full_history`, ERA5 archive). At
inference time there's no historical record for a future date - the
backend needs the **forecast** equivalent
(`fetch_forecast_with_history`, already exists in
`scripts/enrich/weather/open_meteo.py`) feeding into a function that
produces the *identical* column set/order/dtypes the model expects.

Concretely: `condition_models.joblib` saves `features` (the exact list
`train_model.py` trained on) alongside the models - the backend's feature
assembly must produce a DataFrame with exactly those columns, in a
compatible dtype (categorical columns as pandas `category`, same as
`train_model.py`'s `CATEGORICAL_COLUMNS`). Worth factoring the "flatten
one row of weather + terrain + trail info into model columns" logic out
of `build_training_table.py` into something both the offline table-builder
and the live backend can share, rather than reimplementing it twice and
having them drift apart.

## Forecast horizon

Open-Meteo's forecast endpoint only goes out ~16 days
(`fetch_forecast`'s `days` param), and `fetch_forecast_with_history`'s own
past-window is capped at `MAX_FORECAST_PAST_DAYS = 92`. So:
- Requesting conditions for today through ~16 days out: fine.
- Further out: no forecast data exists yet: reject the request or fall back
  to a seasonal/historical-average estimate (open question, see below).

## Open questions

- [ ] **Per-condition prediction threshold** - is 0.5 the right cutoff for
  every condition, or do imbalanced ones (`dusty`, `flooded`) need a
  different threshold tuned against precision/recall trade-offs?
- [ ] **hasScrambling computation** - what fraction of historical reviews
  mentioning "scramble" counts as "this trail has scrambling"? A hard
  cutoff (e.g. >5% of reviews) or something softer?
- [ ] **Model versioning/reload strategy** - how does the backend pick up
  a newly retrained `condition_models.joblib` without a redeploy? Simple
  answer for v1: reload on backend restart, revisit if that's not enough.
- [ ] **Missing terrain coverage** - some trails fall outside the
  soil-survey/bedrock-geology coverage area (`terrain_soilTextureGroup`
  etc. are `None`). Does the model handle that gracefully at inference
  (it should, HistGradientBoostingClassifier natively supports missing
  categoricals) - confirm this explicitly with a test case before relying
  on it.
- [ ] **Trails never fully enriched** - what does `/trails/:id/conditions`
  return for a trail_id that hasn't been through the pipeline at all? 404,
  or trigger on-demand enrichment (much slower, probably not v1)?
- [ ] **Caching conditions responses** - a forecast doesn't change every
  second; is there a sensible TTL (e.g. re-fetch forecast/re-run model at
  most once per hour per trail+date) instead of hitting Open-Meteo on
  every request?
