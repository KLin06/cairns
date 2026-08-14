import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from paths import DATASETS_DIR

from bedrock import fetch_rock_type
from soil import fetch_soil_type

def main(trail_id):
    path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")
    
    with open(path, "r", encoding="utf-8") as f:
        trail_info = json.load(f)
        
    lat, lng = trail_info["latitude"], trail_info["longitude"]
    
    print(fetch_rock_type(lat, lng))
    print(fetch_soil_type(lat, lng))
    

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if len(args) != 1:
        sys.exit(f"usage: python pipeline.py <trail_id> \n\ngot {len(args)} argument(s): {args}")
    
    trail_id = args[0]

    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")
        
    main(trail_id)