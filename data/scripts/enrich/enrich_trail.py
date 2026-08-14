import json
import os
import sys

from scripts.paths import DATASETS_DIR
from scripts.enrich.enrich_review import enrich_data, _load_reviews
from scripts.enrich.enrich_description import enrich_description, save_enriched_description


CHECKPOINT_EVERY = 50


def enrich_trail(trail_id, checkpoint_every=CHECKPOINT_EVERY, use_recording_date=False):
    """Enrich every review for a trail (see enrich_data's docstring for what
    use_recording_date controls). When True, reviews with no attached
    recording are skipped (enrich_data returns None for them), tracked
    separately from actual failures since a missing recording isn't an
    error, just data we don't have a reliable hike date for. When False
    (the default), nothing gets skipped for this reason.

    Saves a checkpoint every `checkpoint_every` enriched reviews so a crash
    or rate-limit ban partway through a long trail doesn't lose everything
    already fetched - each checkpoint overwrites the same
    enriched_reviews/{trail_id}.json that the final save writes to.

    Also enriches and saves the trail's description (terrain data) first,
    before touching any review - enrich_data reads weather off the
    cleaned description, not the enriched one, so this isn't a dependency
    of the review loop, but a trail's enriched_descriptions/{trail_id}.json
    should exist alongside its enriched_reviews/{trail_id}.json for
    build_training_table.py to join against, and this is the one place
    that enriches a whole trail end to end."""
    save_enriched_description(trail_id, enrich_description(trail_id))

    reviews = _load_reviews(trail_id)
    review_ids = reviews["reviewId"].tolist()

    enriched_reviews = []
    errors = []
    skipped_review_ids = []

    for i, review_id in enumerate(review_ids, 1):
        try:
            result = enrich_data(trail_id, review_id, use_recording_date=use_recording_date)
        except Exception as exc:
            errors.append({"reviewId": review_id, "error": str(exc)})
            print(f"[{i}/{len(review_ids)}] failed on review {review_id}: {exc}")
            continue

        if result is None:
            skipped_review_ids.append(review_id)
            print(f"[{i}/{len(review_ids)}] skipped review {review_id} (no recording)")
            continue

        enriched_reviews.append(result)
        print(f"[{i}/{len(review_ids)}] enriched review {review_id}")

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
