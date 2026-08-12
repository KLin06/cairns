import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests
from dotenv import load_dotenv

from paths import DATA_DIR

load_dotenv(os.path.join(DATA_DIR, ".env"))
SESSION_COOKIE = os.environ["ALLTRAILS_SESSION_COOKIE"]

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

def build_headers(trail_url):
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": trail_url,
    }


def make_session():
    session = requests.Session(impersonate="safari_ios")
    session.cookies.set("_alltrails_session", SESSION_COOKIE, domain=".alltrails.com")
    return session
