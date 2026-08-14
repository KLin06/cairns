import json
import os
import time

from scripts.paths import DATASETS_DIR

PER_PAGE = 500


def fetch_reviews(session, trail_id, headers, api_key, per_page=PER_PAGE):
    """Fetch every review for a trail, paginating until AllTrails returns a
    short page. `session` must already carry a primed DataDome cookie (from
    having fetched a trail page first) and the AllTrails auth cookie.
    """
    all_reviews = []
    page = 1
    while True:
        url = (
            f"https://www.alltrails.com/api/alltrails/v2/trails/{trail_id}/reviews"
            f"?per_page={per_page}&page={page}&key={api_key}"
        )

        for attempt in range(4):
            try:
                resp = session.get(url, headers=headers, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                wait = 5 * (attempt + 1)
                print(f"page {page} attempt {attempt + 1} failed ({exc}); retrying in {wait}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"page {page} failed after all retries")

        batch = data.get("trail_reviews", [])
        all_reviews.extend(batch)
        print(f"page {page}: {len(batch)} reviews (total so far: {len(all_reviews)})")
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(2)

    reviews_path = os.path.join(DATASETS_DIR, "raw_reviews", f"{trail_id}.json")
    with open(reviews_path, "w", encoding="utf-8") as f:
        json.dump(all_reviews, f, indent=2, ensure_ascii=False)

    print(f"\nTotal reviews collected: {len(all_reviews)}")
    print(f"saved to {reviews_path}")

    return all_reviews
