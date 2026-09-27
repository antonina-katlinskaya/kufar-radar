import json, os
from datetime import datetime, timezone, timedelta

from .d1 import D1
from .models import BirListing


HISTORY_DB_ID = os.getenv(
    'CF_HISTORY_D1_DATABASE_ID',
    'd8dd0219-8070-4f48-980d-312eba26209e',
)
MAX_BIR_AGE = timedelta(minutes=35)


def history_db():
    return D1(HISTORY_DB_ID)


def _parse_ts(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (TypeError, ValueError):
        return None


def latest_bir_scan(db):
    rows = db.query(
        "SELECT checked_at,parsed_count FROM bir_scans "
        "WHERE status='ok' ORDER BY checked_at DESC LIMIT 1"
    )
    if not rows:
        raise RuntimeError('New BIR history has no successful scan')
    row = rows[0]
    checked = _parse_ts(row.get('checked_at'))
    if not checked:
        raise RuntimeError('New BIR history returned invalid scan time')
    age = datetime.now(timezone.utc) - checked.astimezone(timezone.utc)
    if age > MAX_BIR_AGE:
        raise RuntimeError(
            f'New BIR history is stale: last successful scan {row.get("checked_at")}'
        )
    return row


def load_bir_snapshot(db):
    scan = latest_bir_scan(db)
    rows = db.query(
        "SELECT id,house,listing_json,detail_json,detail_fetched_at "
        "FROM bir_objects WHERE present=1"
    )
    items = []
    for row in rows:
        try:
            detail = json.loads(row.get('detail_json') or '{}')
        except (TypeError, ValueError):
            detail = {}
        try:
            listing = json.loads(row.get('listing_json') or '{}')
        except (TypeError, ValueError):
            listing = {}

        raw = dict(detail)
        raw['history_listing'] = listing
        raw['detail_fetched_at'] = row.get('detail_fetched_at')
        raw['source'] = 'bir-history-residential'

        items.append(BirListing(
            object_key=str(row['id']),
            building_name=row.get('house') or detail.get('nomerDoma'),
            official_address=detail.get('adres') or detail.get('address'),
            unit_no=(
                str(detail.get('nomerPomeschenia'))
                if detail.get('nomerPomeschenia') is not None
                else str(listing.get('number'))
                if listing.get('number') is not None
                else None
            ),
            price_regular_eur=detail.get('cena'),
            price_fast_eur=detail.get('Rassrochka10_cena'),
            area=detail.get('obschPloschad'),
            rooms=detail.get('comnat'),
            floor=detail.get('etaj'),
            raw=raw,
        ))
    return items, scan.get('checked_at')
