import sys
import os
import json
import pandas as pd

from scripts.paths import DATASETS_DIR
from scripts.enrich.weather.dateutils import to_date, shift_days
from scripts.enrich.weather.open_meteo import fetch_historical_weather

WEEK_AHEAD = -7


def _pprint(label, data):
    print(f"\n{label}")
    print("-" * len(label))
    print(json.dumps(data, indent=2))
    

def main(trail_id, review_id):
    description_path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")
    review_path = os.path.join(DATASETS_DIR, "cleaned_reviews", f"{trail_id}.json")
    
    with open(description_path, "r", encoding="utf-8") as f:
        trail_info = json.load(f)
        
    reviews = pd.read_json(review_path)
    matches = reviews[reviews["reviewId"] == int(review_id)]
    if matches.empty:
        sys.exit(f"no review with reviewId {review_id!r} found for trail {trail_id!r}")
    review = matches.iloc[0]

    try:
        review_date = to_date(review["date"])
    except (TypeError, ValueError):
        sys.exit(f"review_date must be a date, got: {review['date']!r}")
    
    lat, lng = trail_info["latitude"], trail_info["longitude"]
    
    _pprint("historical data: ", fetch_historical_weather(lat, lng, shift_days(review_date, WEEK_AHEAD),review_date))
    

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if len(args) != 2:
        sys.exit(f"usage: python pipeline.py <trail_id> <review_id>\n\ngot {len(args)} argument(s): {args}")
    
    trail_id, review_id = args

    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")
        
    if not review_id.isdigit():
        sys.exit(f"review_id must be numeric, got: {review_id!r}")
        
    main(trail_id, review_id)