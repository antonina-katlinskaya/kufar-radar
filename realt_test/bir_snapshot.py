"""Read one exported Bir snapshot from GitHub; no D1 queries in Realt jobs."""
from datetime import datetime, timezone, timedelta
from radar.models import BirListing
from realt_test.github_store import GitHubFile

FIELDS = ('object_key','building_name','official_address','unit_no','price_regular_eur',
          'price_fast_eur','area','rooms','floor')

def decode(payload, now=None):
    if payload.get('schema') != 1 or not payload.get('complete'):
        raise RuntimeError('Bir export is incomplete')
    checked = datetime.fromisoformat(str(payload['checked_at']).replace('Z','+00:00'))
    if checked.tzinfo is None:
        raise RuntimeError('Bir export time has no timezone')
    age = (now or datetime.now(timezone.utc)) - checked
    if age > timedelta(minutes=35) or age < timedelta(minutes=-5):
        raise RuntimeError('Bir GitHub snapshot is stale or future; no price alerts sent')
    rows = payload.get('items') or []
    if not rows or len({x['object_key'] for x in rows}) != len(rows):
        raise RuntimeError('Bir export is empty or contains duplicates')
    return [BirListing(**{k:r.get(k) for k in FIELDS}) for r in rows], payload['checked_at']

def load():
    return decode(GitHubFile('realt-bir-snapshot','realt_state/bir.json').read())
