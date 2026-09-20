import httpx
from datetime import datetime, timezone
from .config import settings

class D1:
    def __init__(self):
        missing = [k for k,v in {
            'CF_ACCOUNT_ID': settings.cf_account_id,
            'CF_D1_DATABASE_ID': settings.cf_database_id,
            'CF_D1_API_TOKEN': settings.cf_token,
        }.items() if not v]
        if missing:
            raise RuntimeError('Missing Cloudflare secrets: ' + ', '.join(missing))
        self.url = f'https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}/d1/database/{settings.cf_database_id}/query'
        self.headers = {'Authorization': f'Bearer {settings.cf_token}', 'Content-Type': 'application/json'}

    def _post(self, body):
        with httpx.Client(timeout=60) as c:
            r = c.post(self.url, headers=self.headers, json=body)
            if r.status_code >= 400:
                raise RuntimeError(f'D1 API error {r.status_code}: {r.text[:1500]}')
            data = r.json()
        if not data.get('success'):
            raise RuntimeError(f'D1 error: {data.get("errors")}')
        return data.get('result') or []

    def query(self, sql: str, params=None):
        res = self._post({'sql': sql, 'params': list(params or [])})
        if not res:
            return []
        return res[0].get('results') or []

    def execute(self, sql: str, params=None):
        return self._post({'sql': sql, 'params': list(params or [])})

    def batch(self, statements):
        if not statements:
            return []
        payload = {'batch': [{'sql': sql, 'params': list(params or [])} for sql, params in statements]}
        return self._post(payload)

    def get_state(self, key: str, default=None):
        rows = self.query('SELECT value FROM state WHERE key=? LIMIT 1', [key])
        return rows[0]['value'] if rows else default

    def set_state(self, key: str, value: str):
        now = datetime.now(timezone.utc).isoformat()
        self.execute('INSERT INTO state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at', [key, value, now])
