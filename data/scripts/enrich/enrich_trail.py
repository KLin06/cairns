import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.paths import DATASETS_DIR
from scripts.enrich.enrich_review import enrich_data, _load_reviews, preload_trail_weather
from scripts.enrich.enrich_description import enrich_description, save_enriched_description


CHECKPOINT_EVERY = 50

# Reviews are enriched concurrently since enrich_data is I/O-bound (mostly
# waiting on the Open-Meteo weather request) - the GIL doesn't block that
# kind of wait, so threads give a real speedup. Kept modest rather than
# "one thread per review": Open-Meteo's free tier caps out around 10,000
# calls/day, and per-(trail_id, date) weather caching (see
# _cached_historical_weather in enrich_review.py) already cuts duplicate
# calls - this just bounds how bursty the true cache-miss calls can get.
MAX_WORKERS = 8


def _load_existing_enriched(trail_id, review_ids):
    """Reviews already enriched and saved from a previous (possibly
    interrupted/failed) run of this trail, keyed by reviewId - {} if
    there's no enriched_reviews/{trail_id}.json yet. Filtered down to
    review_ids still present in the trail's current cleaned reviews, so a
    stale entry left over from before a cleaning-filter change doesn't
    resurrect a review that shouldn't be there anymore."""
    path = os.path.join(DATASETS_DIR, "enriched_reviews", f"{trail_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    still_valid = set(review_ids)
    return {r["reviewId"]: r for r in existing if r["reviewId"] in still_valid}


def enrich_trail(trail_id, checkpoint_every=CHECKPOINT_EVERY, use_recording_date=False, max_workers=MAX_WORKERS):
    """Enrich every review for a trail (see enrich_data's docstring for what
    use_recording_date controls). When True, reviews with no attached
    recording are skipped (enrich_data returns None for them), tracked
    separately from actual failures since a missing recording isn't an
    error, just data we don't have a reliable hike date for. When False
    (the default), nothing gets skipped for this reason.

    Resumes from whatever's already in enriched_reviews/{trail_id}.json
    (see _load_existing_enriched) instead of re-enriching a trail from
    scratch every time it's retried - a trail that failed because one
    review exhausted its Open-Meteo retry budget shouldn't mean redoing
    the hundreds of reviews that already succeeded.

    Reviews are enriched concurrently across `max_workers` threads. Saves a
    checkpoint every `checkpoint_every` enriched reviews (in whatever order
    they finish, not review order - order doesn't matter for storage) so a
    crash or rate-limit ban partway through a long trail doesn't lose
    everything already fetched - each checkpoint overwrites the same
    enriched_reviews/{trail_id}.json that the final save writes to, and
    that partial progress is exactly what gets resumed from above.

    Also enriches and saves the trail's description (terrain data) first,
    before touching any review - enrich_data reads weather off the
    cleaned description, not the enriched one, so this isn't a dependency
    of the review loop, but a trail's enriched_descriptions/{trail_id}.json
    should exist alongside its enriched_reviews/{trail_id}.json for
    build_training_table.py to join against, and this is the one place
    that enriches a whole trail end to end.

    Also preloads the trail's entire weather history in one bulk request
    (see preload_trail_weather) before the review loop starts - single
    thread, no concurrency to coordinate, and every review's own weather
    lookup below just slices out of what's already fetched instead of
    hitting Open-Meteo per review."""
    save_enriched_description(trail_id, enrich_description(trail_id))

    reviews = _load_reviews(trail_id)
    review_ids = reviews["reviewId"].tolist()
    total = len(review_ids)

    already_enriched = _load_existing_enriched(trail_id, review_ids)
    remaining_ids = [rid for rid in review_ids if rid not in already_enriched]
    if already_enriched:
        print(f"resuming {trail_id}: {len(already_enriched)} already enriched, {len(remaining_ids)} remaining")

    preload_trail_weather(trail_id)

    enriched_reviews = list(already_enriched.values())
    errors = []
    skipped_review_ids = []
    completed = len(already_enriched)

    def _run(review_id):
        try:
            return review_id, enrich_data(trail_id, review_id, use_recording_date=use_recording_date), None
        except Exception as exc:
            return review_id, None, exc

    # Only _run() above executes on the worker threads - as_completed()
    # yields to whichever thread is iterating it (here, the caller of
    # enrich_trail), so everything below runs on a single thread one future
    # at a time. No lock needed: enriched_reviews/errors/skipped_review_ids/
    # completed are never touched concurrently.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_run, review_id) for review_id in remaining_ids]
        for future in as_completed(futures):
            review_id, result, exc = future.result()
            completed += 1
            if exc is not None:
                errors.append({"reviewId": review_id, "error": str(exc)})
                print(f"[{completed}/{total}] failed on review {review_id}: {exc}")
            elif result is None:
                skipped_review_ids.append(review_id)
                print(f"[{completed}/{total}] skipped review {review_id} (no recording)")
            else:
                enriched_reviews.append(result)
                print(f"[{completed}/{total}] enriched review {review_id}")
                if checkpoint_every and len(enriched_reviews) % checkpoint_every == 0:
                    save_enriched_trail(trail_id, enriched_reviews)

    print(
        f"\n{len(enriched_reviews)} enriched, {len(skipped_review_ids)} skipped "
        f"(no recording), {len(errors)} failed"
    )
    return enriched_reviews, errors, skipped_review_ids


def save_enriched_trail(trail_id, enriched_reviews):
    out_dir = os.path.join(DATASETS_DIR, "enriched_reviews")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{trail_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched_reviews, f, indent=2, ensure_ascii=False, default=str)
    print(f"saved {len(enriched_reviews)} enriched reviews to {out_path}")
    return out_path


# test: python -m scripts.enrich.enrich_trail 10268327
if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 1:
        sys.exit(f"usage: python -m scripts.enrich.enrich_trail <trail_id>\n\ngot {len(args)} argument(s): {args}")

    trail_id = args[0]
    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")

    enriched_reviews, errors, skipped_review_ids = enrich_trail(trail_id)
    save_enriched_trail(trail_id, enriched_reviews)

    if skipped_review_ids:
        print(f"\n{len(skipped_review_ids)} review(s) skipped (no recording):")
        for review_id in skipped_review_ids:
            print(f"  {review_id}")

    if errors:
        print(f"\n{len(errors)} review(s) failed to enrich:")
        for e in errors:
            print(f"  {e['reviewId']}: {e['error']}")
