import glob
import os

import psycopg2
import psycopg2.errors
import pytest
from dotenv import load_dotenv

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(SERVER_DIR, ".env"))

MIGRATIONS_DIR = os.path.join(SERVER_DIR, "db", "migrations")


def _resolve_test_database_url():
    """Deliberately does NOT fall back to DATABASE_URL - db_conn TRUNCATEs
    the three backfill tables before and after every test, so silently
    reusing the dev database's own connection string would wipe real
    backfilled data the moment the suite runs (this happened once during
    development: a plain `pytest` run against DATABASE_URL emptied every
    table). TEST_DATABASE_URL must be a separate database, set explicitly."""
    return os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def test_database_url():
    """Applies the trail data storage schema once per test session, tolerating
    it already existing - the backfill tests run against a real Postgres
    instance (not a mock), since there's no in-memory substitute for JSONB
    upsert/change-detection behavior. Skips the whole session's backfill
    tests with a clear message if no test database is configured. Returns
    the resolved connection string itself (not just a ready connection) so
    tests that need to open their own additional connections - e.g. to
    exercise db.backfill.get_connection() - can do so with real credentials;
    psycopg2 connection objects' own `.dsn` attribute redacts the password,
    so it can't be recovered from an already-open connection."""
    url = _resolve_test_database_url()
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not set - skipping tests that need a live Postgres instance "
            "(deliberately not falling back to DATABASE_URL: these tests TRUNCATE their tables, "
            "which would destroy real data in a dev database)"
        )

    conn = psycopg2.connect(url)
    conn.autocommit = True
    # Applies every migration in order (0001, 0002, ... - not just the first
    # one), tolerating each already being applied from a prior test run
    # against a persistent test database.
    for migration_path in sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))):
        with open(migration_path, "r", encoding="utf-8") as f:
            migration_sql = f.read()
        with conn.cursor() as cur:
            try:
                cur.execute(migration_sql)
            except (psycopg2.errors.DuplicateTable, psycopg2.errors.DuplicateColumn):
                pass
    conn.close()
    return url


@pytest.fixture
def db_conn(test_database_url):
    """A live connection to the test database, with the three backfill tables
    truncated before and after the test so each test starts and ends from a
    clean slate without dropping/recreating the schema per test."""
    conn = psycopg2.connect(test_database_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE trails, trail_activity, trail_geometry CASCADE")
    conn.commit()
    yield conn
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE trails, trail_activity, trail_geometry CASCADE")
    conn.commit()
    conn.close()
