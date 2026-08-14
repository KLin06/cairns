import json
import os

import pandas as pd

from scripts.paths import DATASETS_DIR
from scripts.enrich.weather.dateutils import to_date, shift_days
from scripts.enrich.weather.open_meteo import fetch_historical_weather
from scripts.enrich.label.label_conditions_keyword import label_comment
from scripts.enrich.recording.get_recording_date import get_recording_date

HISTORY_DAYS = 7

# Keyed by trail_id, not a single global - enriching reviews across multiple
# trails in one run shouldn't evict each other's cached data, and repeat
# calls for the same trail shouldn't re-read its files.
_reviews_cache = {}
_description_cache = {}


def _load_reviews(trail_id):
    """Load and cache a trail's cleaned reviews (DataFrame, keyed by reviewId
    lookups), reading cleaned_reviews/{trail_id}.json at most once."""
    if trail_id not in _reviews_cache:
        path = os.path.join(DATASETS_DIR, "cleaned_reviews", f"{trail_id}.json")
        _reviews_cache[trail_id] = pd.read_json(path)
    return _reviews_cache[trail_id]


def _load_description(trail_id):
    """Load and cache a trail's cleaned description (lat/lng, name, etc.),
    reading cleaned_descriptions/{trail_id}.json at most once."""
    if trail_id not in _description_cache:
        path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            _description_cache[trail_id] = json.load(f)
    return _description_cache[trail_id]


def find_review(trail_id, review_id):
    """Look up one review by reviewId within a trail's cached reviews."""
    reviews = _load_reviews(trail_id)
    matches = reviews[reviews["reviewId"] == int(review_id)]
    if matches.empty:
        raise ValueError(f"no review with reviewId {review_id!r} found for trail {trail_id!r}")
    return matches.iloc[0]


def _merged_conditions(review, labels):
    """Combine our own keyword/embedding-derived condition labels with
    AllTrails' own obstacles/trailConditions tags into one deduplicated
    list, e.g. {"muddy": True, ...} + ["Bugs"] + ["Muddy", "Muddy"]
    -> ["muddy", "bugs"]. Lowercased so "Muddy" (AllTrails tag) and "muddy"
    (our label key) collapse into the same entry instead of duplicating."""
    labeled = [category for category, matched in labels.items() if matched]
    tagged = review.get("obstacles", []) + review.get("trailConditions", [])
    return list(dict.fromkeys(c.lower() for c in labeled + tagged))


def enrich_data(trail_id, review_id):
    """Build one enriched review record: the review itself, plus
    HISTORY_DAYS of historical weather leading up to the review's date, plus
    a merged `conditions` list combining our own keyword/embedding-derived
    labels with AllTrails' own obstacles/trailConditions tags.

    If any conditions were found and the review has an attached recording,
    also fetch the recording's own activity date (`recordingDate`) - it's a
    more precise timestamp of when the hike actually happened than the
    review's `date` (which is just when the review was posted, possibly
    days/weeks after the hike), useful when correlating weather from a day a
    condition was actually observed.

    Reviews and descriptions are cached per trail_id (see _load_reviews /
    _load_description), so enriching many reviews for the same trail only
    reads each file once.
    """
    review = find_review(trail_id, review_id)
    description = _load_description(trail_id)

    review_date = to_date(review["date"])
    weather = fetch_historical_weather(
        description["latitude"],
        description["longitude"],
        shift_days(review_date, -HISTORY_DAYS),
        review_date,
    )

    labels, _ = label_comment(review.get("comment"))
    conditions = _merged_conditions(review, labels)

    enriched = {
        **review.to_dict(),
        "historicalWeather": weather,
        "conditions": conditions,
    }
    del enriched["obstacles"]
    del enriched["trailConditions"]

    if conditions and review.get("hasRecording"):
        try:
            enriched["recordingDate"] = get_recording_date(None, int(review["recordingId"]))
        except Exception as exc:
            print(f"warning: couldn't fetch recording date for review {review_id!r}: {exc}")
            enriched["recordingDate"] = None

    return enriched


# test call: python -m scripts.enrich.enrich_data 10268327 78565385
if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if len(args) != 2:
        sys.exit(f"usage: python enrich_data.py <trail_id> <review_id>\n\ngot {len(args)} argument(s): {args}")

    trail_id, review_id = args
    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")
    if not review_id.isdigit():
        sys.exit(f"review_id must be numeric, got: {review_id!r}")

    print(json.dumps(enrich_data(trail_id, review_id), indent=2, default=str))
