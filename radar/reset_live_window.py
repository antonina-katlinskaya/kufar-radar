from datetime import datetime, timezone
from .d1 import D1

def main():
    db=D1()
    ts=datetime.now(timezone.utc).isoformat()
    rows=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1')
    before=int(rows[0]['n']) if rows else 0

    db.execute('UPDATE events SET active=0,resolved_at=? WHERE active=1',[ts])
    db.execute('DELETE FROM matches')
    db.execute('DELETE FROM unmatched_state')
    db.set_state('monitoring_started_at',ts)
    db.set_state('morning_summary_date','')

    rows=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1')
    after=int(rows[0]['n']) if rows else 0
    print(f'LIVE_WINDOW_RESET before={before} after={after} started_at={ts}')

if __name__=='__main__':
    main()
