import sys

from clean_description import clean_description
from clean_reviews import clean_reviews

def main(trail_id):
    try:
        clean_description(trail_id)
    except Exception as exc:
        sys.exit(f"failed to clean description for {trail_id}: {exc}")
            
    try:
        clean_reviews(trail_id)
    except Exception as exc:
        sys.exit(f"failed to clean reviews for {trail_id}: {exc}")

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if len(args) != 1:
        sys.exit(f"usage: python pipeline.py <trail_id> \n\ngot {len(args)} argument(s): {args}")
    
    trail_id = args[0]

    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")
        
    main(trail_id)