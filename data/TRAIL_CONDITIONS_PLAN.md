# Trail Condition Prediction — Design Notes

## Goal

Predict trail conditions (mud, snow, ice, flooding, etc.) from weather data, so the
app can warn users before they go rather than relying only on stale review text.

## Available data

`reviews.py` + `clean_reviews.py` produce per-review records that already include:

- `obstacles` — e.g. `"Bugs"`, `"Well maintained"`
- `trailConditions` — e.g. `"Bugs"`
- `ratingAttributes` — e.g. `"Great conditions"`, `"Great views"` (sentiment-flavored, not raw condition info)
- `hasRecording` — whether the review is linked to a GPS-tracked activity (`associatedRecording`)
- `date` — when the review was **posted**
- trail-level fields from the actor scrape: `elevationGainFt`, difficulty, `features`, lat/long, etc.

## Pipeline

### 1. Pinpoint the actual hike date

Review `date` is when it was posted, not necessarily when the hike happened — people
sometimes post days later. When `hasRecording` is true, look up the linked
`associatedRecording`'s own activity date instead; it should be closer to the actual
hike. Fall back to the review's `date` when there's no recording.

### 2. Label trail conditions

Skip building a custom embedding/NLP extractor for v1. `obstacles` and
`trailConditions` are already structured labels scraped directly from AllTrails —
use those as the prediction target instead of extracting conditions from free text.

Only fall back to text extraction (e.g. LLM-based structured extraction from
`comment`) later, if this fixed tag vocabulary turns out too coarse for what we
actually want to predict (mud depth, ice, specific flooding, etc. aren't in it).

### 3. Fetch weather data

Pull historical weather for the week leading up to the (corrected) hike date, keyed
by the trail's location (`latitude`/`longitude`).

### 4. Train the model

One pooled model, not one per region. Feed it weather features **and** trail-level
features (elevation gain, surface type, `features` list, difficulty) together,
rather than manually splitting training data by geography.

**Why pooled instead of split by region:** sample size is the real constraint, not
weather-pattern diversity. A single trail (The Crack Trail) only produced ~769
usable hiking/backpacking reviews after cleaning — splitting that thin across many
regions would starve each regional model of data. Including terrain features lets
one model learn how the same weather produces different conditions depending on
trail characteristics (e.g. exposed rock vs. flat forest), instead of needing
separate models to capture that.

Revisit per-region splitting only if a pooled model demonstrably underfits regional
patterns that terrain features can't explain (e.g. microclimates a weather API
doesn't capture).

## Open questions / next steps

- [ ] Confirm `associatedRecording` actually exposes a usable activity date via the API
- [ ] Pick a weather data source/API and decide granularity (daily vs. hourly)
- [ ] Check how often `obstacles`/`trailConditions` are actually populated — too
      sparse to train on?
- [ ] Scale scraping beyond The Crack Trail — need multiple trails/regions before
      "pooled across Ontario" means anything
