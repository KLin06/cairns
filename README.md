# Cairns

Predicts day-specific hiking conditions (mud, ice, snow, slippery, flooded,
bugs) for a trail on a chosen date, using a model trained on real
hiker-reported reviews plus historical weather - not just a static
difficulty label.

**Live (WIP):** [cairns-five.vercel.app](https://cairns-five.vercel.app/) —
client on Vercel, backend on Render. Still under active development, expect
rough edges.

See `APP_SPEC.md` for the product/API spec, and `server/README.md` /
`client/README.md` for each service's own docs.

## The problem

Trail difficulty ratings (AllTrails, provincial park sites) are static
labels set once - they don't reflect that a "moderate" trail in August can
turn genuinely hazardous after spring snowmelt, heavy rain, or an early
snowfall at elevation. Someone planning a hike weeks out has no way to
translate "40% chance of rain 3 days out" into "will this trail actually be
muddy/icy/dangerous on my date."

## How it works

```
scrape AllTrails reviews/descriptions
        |
        v
clean -> enrich (terrain: bedrock/soil lookups, weather: Open-Meteo
                 history, review text -> condition labels)
        |
        v
train one HistGradientBoostingClassifier per condition
        |
        v
condition_models.joblib --(S3)--> FastAPI backend <--REST--> React client
```

1. **Data pipeline** (`data/`) - scrapes trail descriptions and hiker
   reviews from AllTrails, cleans them, then enriches each review with:
   - **Terrain**: bedrock lithology mapped to a wet-traction category,
     soil-survey texture/drainage codes mapped to a mud-potential score
   - **Weather**: an 8-day window (hike day through 7 days prior) pulled
     from Open-Meteo's historical archive
   - **Condition labels**: an embedding-based text labeler applied to each
     review's comment, canonicalized against AllTrails' own obstacle tags
2. **Model** (`data/scripts/model/`) - one independent binary classifier
   per condition (mud, ice, snow, slippery, flooded, bugs) rather than one
   multi-label model, since a review can be muddy *and* icy *and* buggy at
   once and each condition depends on a different subset of features.
   Trained/evaluated with a trail-grouped split - never a random row split,
   since reviews on the same trail share near-identical weather/terrain and
   would leak between train and test - class-balanced to fix near-zero
   recall on rare conditions, and per-condition probability thresholds
   tuned on a held-out validation split rather than a blanket 0.5.
3. **Backend** (`server/`) - FastAPI. At request time it fetches the
   *forecast* equivalent of whatever the model trained on (Open-Meteo
   forecast instead of historical archive), reassembles the identical
   feature vector the training pipeline produced, and runs inference.
   Trail data (reviews/descriptions/routes) is served from either Postgres
   or parsed directly from the pipeline's JSON output and held in memory -
   a deploy-time choice (`DATA_BACKEND` env var), not a code fork.
4. **Client** (`client/`) - React + TypeScript + Vite, map-based trail
   browsing via MapLibre GL, a per-trail detail panel with weather,
   predicted conditions, and historical popularity.
5. **Infra** - Dockerized for local dev; a separate async pipeline (SQS ->
   Lambda -> DynamoDB, provisioned via both CDK and Terraform in `aws/`)
   explores scaling conditions inference beyond the synchronous request
   path. Deployed: client on Vercel, backend on Render.

## Engineering notes worth a second look

- Trained with `GroupShuffleSplit` by trail ID, not a random row split -
  the more obvious approach would silently overstate how well the model
  generalizes to a trail it hasn't seen.
- `class_weight="balanced"` roughly tripled recall on rare conditions
  (`slippery` 0.16 -> 0.74, `icy` 0.12 -> 0.59) at a small ROC-AUC cost - a
  deliberate precision/recall trade, not an oversight (see
  `data/scripts/model/MODEL_NOTES.md`).
- `dusty` was excluded from training entirely (21 positive examples out of
  21,433 rows) rather than reporting a misleadingly bad ROC-AUC computed
  from noise.
- Built spec-first: every feature has a written spec/plan/tasks trail under
  `specs/` before implementation (e.g. `specs/007-docker-containerization`).

## Running with Docker

```bash
cp .env.example .env   # fill in real values, see comments in the file
docker compose up --build
```

Brings up Postgres, the API server, and the client together. The server
fetches its prediction model from S3 rather than a local file - see
`specs/007-docker-containerization/quickstart.md` for a full walkthrough
and `specs/007-docker-containerization/contracts/env-vars.md` for what
every variable in `.env.example` does. `data/` (the training pipeline) is
run separately/manually and isn't part of this compose stack.
