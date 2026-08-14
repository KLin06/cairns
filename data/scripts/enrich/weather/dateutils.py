from datetime import date, datetime, timedelta, timezone

API_DATE_FMT = "%Y-%m-%d"  # date format every Open-Meteo/ECCC param expects


def to_date(value):
    """Coerce a "YYYY-MM-DD" string, a full ISO datetime string (e.g. an
    ECCC "obs_date_tm" like "2026-08-13T19:15:00.000Z"), or a date/datetime,
    into a plain date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, API_DATE_FMT).date()
        except ValueError:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    raise TypeError(f"can't convert {value!r} to a date")


def to_api_date(value):
    """Format a date/datetime/ISO string as the "YYYY-MM-DD" string the
    Open-Meteo and ECCC APIs expect for date params."""
    return to_date(value).strftime(API_DATE_FMT)


def shift_days(value, n):
    """API-format date string `n` days from `value` (n may be negative)."""
    return (to_date(value) + timedelta(days=n)).strftime(API_DATE_FMT)


def today():
    """Today's date (UTC) as an API-format string."""
    return datetime.now(timezone.utc).strftime(API_DATE_FMT)


def hours_ago_iso(hours):
    """UTC timestamp `hours` before now, as the ISO 8601 string ECCC's
    swob-realtime `datetime` filter expects (e.g. "2026-08-13T17:15:00Z")."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
