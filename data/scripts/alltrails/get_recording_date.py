import re
import sys

from session import USER_AGENT, make_session

HEADERS = {"User-Agent": USER_AGENT}

# Matches the recording's own creation timestamp. It's embedded as a JSON
# string nested inside another JSON payload, so quotes are backslash-escaped:
# \"created_at\":\"2026-08-04T13:35:32Z\" -- the optional \\? handles both
# escaped and unescaped forms in case that framing ever changes.
CREATED_AT_RE = re.compile(r'\\?"created_at\\?":\\?"([^"\\]+)')


def get_recording_date(recording_id):
    """Fetch the activity start date for an AllTrails recording, given its numeric id."""
    session = make_session()

    url = f"https://www.alltrails.com/explore/recording/{recording_id}"
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    match = CREATED_AT_RE.search(resp.text)
    if not match:
        raise ValueError(f"could not find a date for recording {recording_id}")
    return match.group(1)
