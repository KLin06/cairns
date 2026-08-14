import json
import os
import random
import threading
import time

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

# A trail's lat/lng is fixed, so the HISTORY_DAYS window only depends on the
# weather_date - many reviews on the same trail land on the same date (or
# get enriched in the same run before that changes), so caching per
# (trail_id, weather_date) avoids re-fetching identical Open-Meteo requests.
# This matters beyond just speed: Open-Meteo's free tier caps out around
# 10,000 calls/day, and enriching every review with its own uncached call
# would blow well past that across the full trail set. Locked since
# enrich_trail.py runs this loop across a thread pool.
_weather_cache = {}
_weather_cache_lock = threading.Lock()

# Minimum spacing between requests to alltrails.com - only recording-date
# lookups hit their site directly (weather goes to Open-Meteo, unrelated
# limit). Module-level so it applies whether enrich_data is called once or
# in a tight batch loop (see enrich_trail.py), without either caller having
# to know this exists.
#
# A fixed interval is a detectable pattern on its own, so a random jitter
# on top of the floor - wider than a token amount so consecutive gaps don't
# cluster near the same value.
RECORDING_FETCH_MIN_INTERVAL = 3.0
RECORDING_FETCH_JITTER = 4.0
_last_recording_fetch_time = 0.0


_recording_fetch_lock = threading.Lock()


def _rate_limited_recording_date(recording_id):
    global _last_recording_fetch_time
    with _recording_fetch_lock:
        wait_for = RECORDING_FETCH_MIN_INTERVAL + random.uniform(0, RECORDING_FETCH_JITTER)
        elapsed = time.monotonic() - _last_recording_fetch_time
        if elapsed < wait_for:
            time.sleep(wait_for - elapsed)
        _last_recording_fetch_time = time.monotonic()
    return get_recording_date(None, recording_id)


def _cached_historical_weather(trail_id, lat, lng, weather_date):
    key = (trail_id, weather_date)
    with _weather_cache_lock:
        cached = _weather_cache.get(key)
    if cached is not None:
        return cached
    weather = fetch_historical_weather(lat, lng, shift_days(weather_date, -HISTORY_DAYS), weather_date)
    with _weather_cache_lock:
        _weather_cache[key] = weather
    return weather


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


# Canonical set of trail-condition categories the model actually cares
# about, mapped from every raw spelling that can show up across our own
# keyword/embedding labels and AllTrails' own obstacles/trailConditions
# tags. AllTrails' tag vocabulary covers more than physical conditions
# (e.g. "Fee", "Great!", "Well maintained" are about cost/experience, not
# terrain) and spells the same condition differently depending on the
# source (trailConditions has its own "Buggy" tag where obstacles just
# says "Bugs"; our labeler says "snowy", AllTrails' own tag says "Snow") -
# a raw tag not in this map (None) is dropped rather than kept, since it's
# noise for a mud/ice/slip conditions model, not signal.
CONDITION_CATEGORY_MAP = {
    "bugs": "bugs",
    "buggy": "bugs",
    "dusty": "dusty",
    "flooded": "flooded",
    "muddy": "muddy",
    "icy": "icy",
    "rocky": "rock",
    "scramble": "scramble",
    "slippery": "slippery",
    "snow": "snow",
    "snowy": "snow",
}


def _merged_conditions(review, labels):
    """Combine our own keyword/embedding-derived condition labels with
    AllTrails' own obstacles/trailConditions tags into one deduplicated
    list of canonical categories (see CONDITION_CATEGORY_MAP), e.g.
    {"muddy": True, ...} + ["Bugs"] + ["Muddy", "Muddy"] ->
    ["muddy", "bugs"]. Lowercased so "Muddy" (AllTrails tag) and "muddy"
    (our label key) collapse into the same entry instead of duplicating."""
    labeled = [category for category, matched in labels.items() if matched]
    tagged = review.get("obstacles", []) + review.get("trailConditions", [])
    raw = (c.lower() for c in labeled + tagged)
    mapped = (CONDITION_CATEGORY_MAP.get(c) for c in raw)
    return list(dict.fromkeys(c for c in mapped if c is not None))


def enrich_data(trail_id, review_id, use_recording_date=False):
    """Build one enriched review record: the review itself, plus
    HISTORY_DAYS of historical weather leading up to the hike, plus a
    merged `conditions` list combining our own keyword/embedding-derived
    labels with AllTrails' own obstacles/trailConditions tags.

    Terrain (bedrock/soil) isn't included here - it's a property of the
    trail's location, not of any individual review, so it's fetched once
    per trail in `enrich_description.py` instead of once per review.

    When use_recording_date=False (default): skips the recording-date
    lookup entirely - no alltrails.com request, no rate limiting/jitter,
    and no review dropped for lacking a recording - and uses review["date"]
    directly as the weather anchor instead, trading date precision for
    full coverage. `recordingDate` is omitted from the result.

    When use_recording_date=True: returns None for reviews with no
    attached recording - review["date"] is just when the review was
    posted (possibly days/weeks after the hike), not a reliable anchor for
    "what was the weather that day", so we only keep reviews where we can
    get the recording's own activity date instead. The recording-date fetch
    itself can still fail (e.g. a 404 for a deleted/private recording) even
    when hasRecording=True; in that case the review is enriched using
    review["date"] as a fallback rather than dropped, since it's still
    labeled data, just with a less precise date. `recordingDate` is included
    in the result.

    Reviews and descriptions are cached per trail_id (see _load_reviews /
    _load_description), so enriching many reviews for the same trail only
    reads each file once.
    """
    review = find_review(trail_id, review_id)

    recording_date = None
    if use_recording_date:
        if not review.get("hasRecording"):
            return None
        try:
            recording_date = _rate_limited_recording_date(int(review["recordingId"]))
        except Exception as exc:
            print(f"warning: couldn't fetch recording date for review {review_id!r}: {exc}")

    description = _load_description(trail_id)

    weather_date = to_date(recording_date) if recording_date else to_date(review["date"])
    weather = _cached_historical_weather(trail_id, description["latitude"], description["longitude"], weather_date)

    labels, _ = label_comment(review.get("comment"))
    conditions = _merged_conditions(review, labels)

    enriched = {
        **review.to_dict(),
        "historicalWeather": weather,
        "conditions": conditions,
        # seasonality signal - mud/snow/ice risk swings hugely by time of
        # year in a way raw weather alone doesn't fully capture (e.g. spring
        # thaw), and this is the hike date, not review["date"], so it stays
        # correct even when the review was posted weeks later.
        "dayOfYear": weather_date.timetuple().tm_yday,
    }
    if use_recording_date:
        enriched["recordingDate"] = recording_date
    del enriched["obstacles"]
    del enriched["trailConditions"]

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
