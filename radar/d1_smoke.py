from radar.d1 import D1

def main():
    db=D1()
    db.batch([
      ('INSERT INTO state(key,value,updated_at) VALUES(?,?,datetime("now")) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',['__smoke_a','1']),
      ('INSERT INTO state(key,value,updated_at) VALUES(?,?,datetime("now")) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',['__smoke_b','2']),
    ])
    rows=db.query("SELECT key,value FROM state WHERE key IN ('__smoke_a','__smoke_b') ORDER BY key")
    print('rows',rows)
    assert len(rows)==2
    db.execute("DELETE FROM state WHERE key IN ('__smoke_a','__smoke_b')")
    print('telegram_chat_configured', bool(db.get_state('telegram_chat_id')))
    print('baseline_complete', db.get_state('baseline_complete','0'))
    print('active_events', (db.query('SELECT COUNT(*) AS n FROM events WHERE active=1') or [{'n':0}])[0]['n'])
    print('D1_SMOKE_OK')

if __name__=='__main__':
    main()

# batch smoke trigger

# d1 access recheck 2

# state status check
