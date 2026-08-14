import sys

from scripts.alltrails.session import build_headers
from scripts.alltrails.trail import find_api_key, scrape_page, populate_trail_data
from scripts.alltrails.reviews import fetch_reviews

def main(trail_id, trail_url):
    headers = build_headers(trail_url)

    try:
        session, html = scrape_page(trail_id, trail_url, headers)
    except Exception as exc:
        sys.exit(f"failed to scrape trail page for {trail_id}: {exc}")

    try:
        api_key = find_api_key(html)
    except Exception as exc:
        sys.exit(f"failed to find API key for {trail_id}: {exc}")

    try:
        populate_trail_data(session, trail_id, headers, api_key, html)
    except Exception as exc:
        sys.exit(f"failed to populate trail data for {trail_id}: {exc}")

    try:
        fetch_reviews(session, trail_id, headers, api_key)
    except Exception as exc:
        sys.exit(f"failed to fetch reviews for {trail_id}: {exc}")

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if len(args) != 2:
        sys.exit(f"usage: python pipeline.py <trail_id> <trail_url>\n\ngot {len(args)} argument(s): {args}")
    
    trail_id, trail_url = args

    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")
    if not trail_url.startswith("https://www.alltrails.com/trail/"):
        sys.exit(f"trail_url doesn't look like an AllTrails trail page: {trail_url!r}")
        
    main(trail_id, trail_url)
