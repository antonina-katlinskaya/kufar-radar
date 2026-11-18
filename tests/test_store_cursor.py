import sqlite3
from radar.store import _query_paged

class Db:
    def __init__(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.row_factory=sqlite3.Row
        self.conn.execute('CREATE TABLE kufar_ads(ad_id TEXT PRIMARY KEY,profile_id TEXT,active INTEGER,raw_json TEXT)')
        self.conn.execute('CREATE INDEX old_profile ON kufar_ads(profile_id)')
        self.calls=[]
    def query(self,sql,params):
        self.calls.append((sql,params))
        return [dict(r) for r in self.conn.execute(sql,params)]

def fill(db,n=130):
    db.conn.executemany('INSERT INTO kufar_ads VALUES(?,?,?,?)',[
        (f'{i:06}', 'p' if i%3 else 'other',i%2,'{}') for i in range(n)])

def test_cursor_keeps_every_profile_record_once():
    db=Db();fill(db)
    expected=[dict(r) for r in db.conn.execute("SELECT * FROM kufar_ads WHERE profile_id='p' ORDER BY ad_id")]
    actual=_query_paged(db,'kufar_ads','profile_id=?',('p',),'ad_id',page_size=7)
    assert actual==expected
    assert len({r['ad_id'] for r in actual})==len(actual)
    assert all('OFFSET' not in sql for sql,_ in db.calls)

def test_cursor_preserves_active_filter_and_exact_page_boundary():
    db=Db();fill(db,120)
    expected=[dict(r) for r in db.conn.execute("SELECT * FROM kufar_ads WHERE active=1 AND profile_id='p' ORDER BY ad_id")]
    assert _query_paged(db,'kufar_ads','active=1 AND profile_id=?',('p',),'ad_id',page_size=10)==expected

def test_empty_profile_returns_no_partial_history():
    db=Db();fill(db)
    assert _query_paged(db,'kufar_ads','profile_id=?',('absent',),'ad_id')==[]

def test_object_key_cursor_preserves_bir_rows():
    db=Db()
    db.conn.execute('CREATE TABLE bir_objects(object_key TEXT PRIMARY KEY,active INTEGER)')
    db.conn.executemany('INSERT INTO bir_objects VALUES(?,?)',[(str(i),i%2) for i in range(77)])
    actual=_query_paged(db,'bir_objects','active=1',order='object_key',page_size=5)
    expected=[dict(r) for r in db.conn.execute('SELECT * FROM bir_objects WHERE active=1 ORDER BY object_key')]
    assert actual==expected

def test_nonadvancing_cursor_fails_before_caller_can_write_snapshot():
    class Broken:
        def query(self,*args): return [{'ad_id':'one'},{'ad_id':'two'}]
    try:
        _query_paged(Broken(),'kufar_ads',order='ad_id',page_size=2)
    except RuntimeError as e:
        assert 'partial snapshot refused' in str(e)
    else:
        raise AssertionError('Nonadvancing source was accepted')

def test_seek_and_compound_index_reduce_repeated_database_work():
    db=Db();fill(db,6000)
    steps=[0]
    def tick(): steps[0]+=1;return 0
    db.conn.set_progress_handler(tick,1)
    old=[];offset=0
    while True:
        page=db.query('SELECT * FROM kufar_ads WHERE profile_id=? ORDER BY ad_id LIMIT ? OFFSET ?',['p',50,offset])
        old+=page
        if len(page)<50:break
        offset+=len(page)
    before=steps[0]
    db.conn.execute('CREATE INDEX idx_kufar_profile_adid_cursor ON kufar_ads(profile_id,ad_id)')
    steps[0]=0
    new=_query_paged(db,'kufar_ads','profile_id=?',('p',),'ad_id')
    after=steps[0]
    assert new==old
    assert after < before/3, (before,after)
    plan=' '.join(str(r['detail']) for r in db.conn.execute("EXPLAIN QUERY PLAN SELECT * FROM kufar_ads WHERE profile_id='p' AND ad_id>'000050' ORDER BY ad_id LIMIT 50"))
    assert 'idx_kufar_profile_adid_cursor' in plan
