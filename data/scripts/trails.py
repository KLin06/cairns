import argparse
import json
import os

import pandas as pd

from scripts.paths import DATASETS_DIR
from scripts.alltrails.scrape_trail import main as scrape_trail
from scripts.clean.clean_data import main as clean_trail
from scripts.enrich.enrich_trail import enrich_trail, save_enriched_trail

EXPLORE_PATH = os.path.join(DATASETS_DIR, "explore", "top_100_ontario_trails.json")
# Tracks per-trail, per-stage status (done/failed) across runs, so
# re-running a stage after a crash or a `python -m scripts.trails <stage>`
# picks up where it left off instead of re-scraping/re-cleaning/re-enriching
# everything from scratch.
STATE_PATH = os.path.join(DATASETS_DIR, "explore", "pipeline_state.json")

STAGES = ["scrape", "clean", "enrich"]


def _load_trails():
    """trail_id (str) -> AllTrails URL for every trail in the explore
    index."""
    df = pd.read_json(EXPLORE_PATH)
    df = df[["ID", "slug"]]
    df["url"] = "https://www.alltrails.com/" + df["slug"]
    return {str(row.ID): row.url for row in df.itertuples()}


def _load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _run_scrape(trail_id, url):
    scrape_trail(trail_id, url)


def _run_clean(trail_id, url):
    clean_trail(trail_id)


def _run_enrich(trail_id, url):
    enriched_reviews, errors, _skipped = enrich_trail(trail_id)
    save_enriched_trail(trail_id, enriched_reviews)
    if errors:
        # Partial success still gets saved above - but flag the trail as
        # failed so it shows up for a retry rather than looking clean.
        raise RuntimeError(f"{len(errors)} review(s) failed: {errors[:3]}")


STAGE_FUNCS = {"scrape": _run_scrape, "clean": _run_clean, "enrich": _run_enrich}


def run_stage(stage, retry_failed=False, from_id=None):
    """Run one pipeline stage (scrape/clean/enrich) across every trail in
    the explore index, one trail at a time, one stage at a time - not
    scrape+clean+enrich per trail, so you can review/fix a whole stage's
    output before moving to the next.

    Trails already marked "done" for this stage in pipeline_state.json are
    skipped by default, which is what makes re-running the same stage a
    resume rather than a restart. `retry_failed` re-attempts trails marked
    "done" or "failed" instead of skipping them. `from_id` restarts at a
    specific trail_id in the explore index's order (e.g. to skip past a
    trail you've decided not to bother retrying), independent of what's
    recorded as done/failed.

    Returns (succeeded_ids, failed_ids) for this run."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}, must be one of {STAGES}")

    trails = _load_trails()
    ids = list(trails.keys())
    if from_id is not None:
        if from_id not in ids:
            raise ValueError(f"trail_id {from_id!r} not found in explore index")
        ids = ids[ids.index(from_id):]

    state = _load_state()
    run_func = STAGE_FUNCS[stage]

    total = len(ids)
    succeeded = []
    failed = []
    for i, trail_id in enumerate(ids, 1):
        trail_state = state.setdefault(trail_id, {})
        status = trail_state.get(stage, {}).get("status")
        if status in ("done", "failed") and not retry_failed:
            print(f"[{i}/{total}] {trail_id}: already {status}, skipping")
            continue

        print(f"[{i}/{total}] {trail_id}: running {stage}...")
        try:
            run_func(trail_id, trails[trail_id])
        except (Exception, SystemExit) as exc:
            print(f"[{i}/{total}] {trail_id}: {stage} FAILED - {exc}")
            trail_state[stage] = {"status": "failed", "error": str(exc)}
            failed.append(trail_id)
        else:
            trail_state[stage] = {"status": "done"}
            succeeded.append(trail_id)
        _save_state(state)

    print(f"\n{stage}: {len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        print("failed trail_ids:", failed)
    return succeeded, failed


# usage:
#   python -m scripts.trails scrape
#   python -m scripts.trails clean
#   python -m scripts.trails enrich
#   python -m scripts.trails enrich --retry-failed
#   python -m scripts.trails scrape --from-id 12345678
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run one stage (scrape/clean/enrich) of the trail pipeline across every trail in the explore index."
    )
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument(
        "--from-id",
        help="restart at this trail_id's position in the explore index, ignoring done/failed state before it",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="re-run trails already marked done or failed for this stage, instead of skipping them",
    )
    args = parser.parse_args()

    run_stage(args.stage, retry_failed=args.retry_failed, from_id=args.from_id)
