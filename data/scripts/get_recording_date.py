import os
import re
import sys

from curl_cffi import requests
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(DATA_DIR, ".env"))

SESSION_COOKIE = os.environ["ALLTRAILS_SESSION_COOKIE"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
}

# Matches the recording's own creation timestamp. It's embedded as a JSON
# string nested inside another JSON payload, so quotes are backslash-escaped:
# \"created_at\":\"2026-08-04T13:35:32Z\" -- the optional \\? handles both
# escaped and unescaped forms in case that framing ever changes.
CREATED_AT_RE = re.compile(r'\\?"created_at\\?":\\?"([^"\\]+)')


def get_recording_date(recording_id):
    """Fetch the activity start date for an AllTrails recording, given its numeric id."""
    session = requests.Session(impersonate="safari_ios")
    session.cookies.set("_alltrails_session", SESSION_COOKIE, domain=".alltrails.com")

    url = f"https://www.alltrails.com/explore/recording/{recording_id}"
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    match = CREATED_AT_RE.search(resp.text)
    if not match:
        raise ValueError(f"could not find a date for recording {recording_id}")
    return match.group(1)


if __name__ == "__main__":
    recording_id = sys.argv[1] if len(sys.argv) > 1 else "406046751"
    print(get_recording_date(recording_id))
