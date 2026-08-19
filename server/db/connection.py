import os

import psycopg2
from dotenv import load_dotenv

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(SERVER_DIR, ".env"))


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set - check server/.env")
    return psycopg2.connect(database_url)
