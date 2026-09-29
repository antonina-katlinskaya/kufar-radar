import json, os
from datetime import datetime, timezone, timedelta

from .d1 import D1
from .models import BirListing, KufarListing


HISTORY_DB_ID = os.getenv(
    'CF_HISTORY_D1_DATABASE_ID',
    'd8dd0219-8070-4f48-980d-312eba26209e',
)
MAX_BIR_AGE = timedelta(minutes=35)
MAX_KUFAR_AGE = timedelta(minutes=50)


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
        latest = db.query(
            'SELECT status,error FROM bir_scans ORDER BY checked_at DESC LIMIT 1'
        )
        failure = latest[0] if latest else {}
        if failure.get('status') == 'rejected' and 'exceeded D1\'s free tier daily row write limit' in str(failure.get('error') or ''):
            raise RuntimeError('D1_QUOTA_PAUSE: BIR history cannot update until the UTC reset')
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


def load_kufar_profile_snapshot(db, profile_id):
    state_rows = db.query(
        "SELECT cursor,last_cycle_at,last_success_at FROM kufar_bridge_state "
        "WHERE profile_id=? LIMIT 1",
        [str(profile_id)],
    )
    if not state_rows:
        raise RuntimeError(f'New Kufar bridge has no state for profile {profile_id}')
    state = state_rows[0]
    completed = _parse_ts(state.get('last_cycle_at'))
    success = _parse_ts(state.get('last_success_at'))
    if not completed:
        raise RuntimeError(
            f'New Kufar bridge has not completed a full cycle for profile {profile_id}'
        )
    if not success or datetime.now(timezone.utc) - success.astimezone(timezone.utc) > MAX_KUFAR_AGE:
        latest = db.query(
            'SELECT status,error FROM kufar_import_scans WHERE profile_id=? '
            'ORDER BY observed_at DESC LIMIT 1', [str(profile_id)]
        )
        failure = latest[0] if latest else {}
        if failure.get('status') == 'rejected' and 'exceeded D1\'s free tier daily row write limit' in str(failure.get('error') or ''):
            raise RuntimeError(f'D1_QUOTA_PAUSE: Kufar bridge cannot update profile {profile_id} until the UTC reset')
        raise RuntimeError(
            f'New Kufar bridge is stale for profile {profile_id}: '
            f'last success {state.get("last_success_at")}'
        )

    rows = db.query(
        "SELECT ad_id,profile_id,url,price_eur,price_byn,area,rooms,floor,"
        "address,title,list_time,raw_json "
        "FROM kufar_ads_live WHERE profile_id=? AND present=1",
        [str(profile_id)],
    )
    items = []
    for row in rows:
        try:
            raw = json.loads(row.get('raw_json') or '{}')
        except (TypeError, ValueError):
            raw = {}
        if row.get('list_time') and not raw.get('list_time'):
            raw['list_time'] = row.get('list_time')
        raw['source'] = 'kufar-bir-bridge'
        items.append(KufarListing(
            ad_id=str(row['ad_id']),
            url=row.get('url') or f"https://re.kufar.by/vi/{row['ad_id']}",
            profile_id=str(row.get('profile_id') or profile_id),
            price_eur=row.get('price_eur'),
            price_byn=row.get('price_byn'),
            area=row.get('area'),
            rooms=row.get('rooms'),
            floor=row.get('floor'),
            address=row.get('address'),
            title=row.get('title'),
            raw=raw,
        ))
    return items, state
