# Phase 1 Data Model

## Backend

### `ConditionResult` (existing, unchanged)
- `probability: float` — raw `predict_proba` output, 0-1
- `predicted: bool` — `probability >= thresholds[condition]` (per-condition, not blanket 0.5)

### `ConditionsConfidence` (NEW)
- `reviewCount: int` — the trail's `trail_activity.total_reviews` (0 if the trail has no activity
  row at all — a missing activity row is treated the same as zero reviews, not as an error; see
  Edge Cases in spec.md)
- `limitedData: bool` — `reviewCount < LIMITED_DATA_THRESHOLD` (20, per spec.md's Assumptions —
  "a reasonable low-data cutoff... not a product decision requiring sign-off")

### `ConditionsResponse` (extended)
- `trailId: str`
- `date: str`
- `conditions: dict[str, ConditionResult]` — keyed by plain condition name (`"muddy"`, not
  `"condition_muddy"`); only conditions actually present in `model_bundle["models"]` appear (FR-003
  — `dusty` is absent because it was excluded from training, not because of a filter step here)
- `modelVersion: str` — the `condition_models.joblib` file's mtime, ISO date (auto-advances on
  retrain without a code change)
- `confidence: ConditionsConfidence` (NEW)

### Feature row (internal, not wire-visible)

One pandas DataFrame row, columns = `model_bundle["features"]` exactly (70 columns, see
research.md decision 3), assembled by:

| Group | Source | Function |
|---|---|---|
| `dayOfYear` | `date.timetuple().tm_yday` | inline in `conditions.py` |
| `antecedentPrecipIndex` | 14 days of weather before `date` | `feature_flatten.antecedent_precip_index` |
| `weather_d0_*`..`weather_d7_*` | 8 days of weather ending at `date` | `feature_flatten.flatten_weather` |
| `trail_latitude`/`longitude`/`length`/`difficultyRating` | `enriched_descriptions/{id}.json` top-level fields | `feature_flatten.flatten_description` |
| `terrain_*` (4 cols) | `enriched_descriptions/{id}.json`'s `terrainData` | `feature_flatten.flatten_terrain` |
| `feature_*` (11 cols) | trail's own `features` list, tested against the model's fixed vocab | inline in `conditions.py` |
| `trail_surface_*_pct` (9 cols) | trail's own `surfaceTypes` list, tested against the model's fixed vocab | inline in `conditions.py` |

`terrain_rockSlipRisk`/`terrain_soilTextureGroup` cast to pandas `category` dtype before
`predict_proba` (matches `train_model.py`'s `CATEGORICAL_COLUMNS`).

## Frontend

### `PanelState` (extended, in `App.tsx`)

```ts
interface PanelState {
  selectedTrailId: string | null
  overview: OverviewState
  popularity: PopularityState
  route: RouteState
  mapViewBeforeOpen: MapView | null
  selectedDate: string | null          // NEW - "YYYY-MM-DD", null until the weather window loads then defaults to today
  weatherWindow: WeatherWindowState    // NEW - the whole ~16-day window, fetched once per trail
  conditionsByDate: Record<string, ConditionsDateState>  // NEW - keyed by date, one entry per date whose conditions have been requested
}
```

`selectedDate` is the single piece of state constitution Principle IV requires — the Weather
section's day-stepper and the Day Selection strip both read it and both call the same
`setSelectedDate`.

### `WeatherWindowState`
```ts
interface WeatherWindowState {
  status: 'loading' | 'ready' | 'error' | 'absent'
  days: DailyWeather[]   // full window, today..today+15; Weather section picks selectedDate's entry locally
}
```
One fetch per trail selection (not per date) — see research.md decision 5's backend mirror; no
FR-020 staleness concern here since it's fetched exactly once per trail.

### `ConditionsDateState`
```ts
interface ConditionsDateState {
  status: 'loading' | 'ready' | 'error' | 'out-of-range'
  data: ConditionsResponse | null
}
```
One entry is created per date the UI has ever requested (the currently-selected date, plus all 16
window dates for the strip's favorability coloring). FR-020 (stale response must not overwrite
current display) is satisfied by keying state updates on `(trailId, date)` matching the in-flight
request, same pattern `App.tsx` already uses for `overview`/`popularity`/`route`.

### Gear/prep suggestion lookup (client-only, fixed per spec.md Assumptions)
```ts
const PREP_SUGGESTIONS: Record<string, string> = {
  icy: 'Microspikes recommended',
  muddy: 'Waterproof boots recommended',
  bugs: 'Bring insect repellent',
  slippery: 'Trekking poles recommended',
  flooded: 'Expect stream crossings — check water levels before you go',
  snow: 'Snowshoes or traction devices recommended',
}
```

### Best-day favorability (client-only, derived, per spec.md Assumptions)
For a given date's `ConditionsResponse`, favorability = count of `predicted === true` conditions
(lower is better). No new model output — purely a client-side derived ranking used only for the
strip's color scale.
