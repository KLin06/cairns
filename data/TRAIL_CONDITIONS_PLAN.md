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

**Update:** checked how often `obstacles`/`trailConditions` are actually populated
(the open question below) — they're too sparse to rely on alone. Falling back to
text extraction from `comment` for v1, earlier than originally planned.

**Approach: sentence-level embeddings + cosine similarity, not single-word matching.**
Comparing a whole review's `comment` against one word like `"muddy"` dilutes the
signal — reviews are multi-sentence, and only one sentence may actually describe
conditions. Instead:

1. Split each review's `comment` into sentences.
2. Embed each sentence with a lightweight local sentence-transformer
   (`all-MiniLM-L6-v2` — offline, no API cost, fast enough at this volume).
3. Embed a small set of reference phrases *per condition category*, not one word
   each (a single anchor word misses phrasing variety):
   - `mud`: "the trail was muddy", "lots of mud on the path", "muddy conditions underfoot"
   - `ice`: "icy trail", "ice made it slippery", "frozen and slick"
   - `snow`: "snow covered the trail", "deep snow", "snowy and hard to walk"
   - `flooding`: "trail was flooded", "water covering the path", "creek crossing was flooded"
4. For each sentence, take the max cosine similarity against each category's phrase
   set; flag the category if it clears a threshold.
5. Store as a new field alongside the existing tags —
   `conditionMentions: [{"category": "mud", "sentence": "...", "score": 0.61}]` —
   rather than overwriting `obstacles`/`trailConditions`. Real AllTrails tags stay
   the highest-confidence label when present; embedding matches backfill reviews
   where tags are empty.

**Threshold tuning has no principled a priori cutoff.** Run once, manually spot-check
~20-30 borderline-scored sentences per category, and tune from there rather than
guessing a number up front.

New dependency: `sentence-transformers` (add to `requirements.txt`).

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
- [x] Pick a weather data source/API and decide granularity (daily vs. hourly) —
      MSC GeoMet `climate-daily` (station-based, daily). See `weather/climate_daily.py`.
- [x] Check how often `obstacles`/`trailConditions` are actually populated — too
      sparse to train on alone. Falling back to embedding-based text extraction
      from `comment` (see "Label trail conditions" above).
- [ ] Pick and validate cosine-similarity thresholds per condition category
      (mud/ice/snow/flooding) against manually spot-checked sentences
- [ ] Scale scraping beyond The Crack Trail — need multiple trails/regions before
      "pooled across Ontario" means anything

## Readings — sentence embeddings & cosine similarity

For understanding the mechanics behind the condition-labeling approach above.

Start here:
- [Exploring Cosine Similarity: How Sentence Embedding Models Measure Meaning](https://medium.com/researchify/exploring-cosine-similarity-how-sentence-embedding-models-measure-meaning-1b047675ef8a) — why cosine similarity (angle between vectors) works better than raw distance for text
- [What is Sentence Similarity? (Hugging Face)](https://huggingface.co/tasks/sentence-similarity) — short task overview with live examples

Then the practical how-to:
- [Semantic Textual Similarity — Sentence Transformers docs](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) — official docs for `sentence-transformers` and `all-MiniLM-L6-v2`, the library/model used here
- [How to Perform Sentence Similarity Check Using Sentence Transformers (freeCodeCamp)](https://www.freecodecamp.org/news/how-to-perform-sentence-similarity-check-using-sentence-transformers/) — full walkthrough tutorial

Deeper grounding:
- [What is cosine similarity and how is it used with Sentence Transformer embeddings? (Milvus)](https://milvus.io/ai-quick-reference/what-is-cosine-similarity-and-how-is-it-used-with-sentence-transformer-embeddings-to-measure-sentence-similarity) — connects the math to what the embedding model does internally

**Note:** these tutorials mostly cover "compare sentence A to sentence B." Our case
compares a sentence against a *category* of several reference phrases (step 3
above) — taking the max/mean similarity across a phrase set is a small extension
past what these readings show directly, not something pre-packaged in them.
