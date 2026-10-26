import unittest
from unittest.mock import patch
import json
from datetime import datetime,timezone
from realt_test.incremental import advance
from realt_test.sources import TRACKED

PERSON=next(iter(TRACKED))
def row(price,created="2026-10-01T00:00:00Z"):
    return {"uuid":"x","userUuid":PERSON,"price":price,"priceCurrency":"978","areaTotal":44.42,"rooms":1,"createdAt":created}

class IncrementalTests(unittest.TestCase):
    def test_unchanged_snapshot_never_reads_archive_or_bir_budget(self):
        from realt_test.incremental import source
        now=datetime.now(timezone.utc).isoformat()
        tree={"sha":"commit","tree":[{"path":"data/collection_state.json"},{"path":"data/raw/2026-10-26_12-00_etazhi.json.gz"}]}
        marker={"complete":True,"snapshot_at":now,"completed_at":now}
        calls=[]
        def fake(url):
            calls.append(url)
            return json.dumps(tree if 'git/trees' in url else marker).encode()
        with patch('realt_test.incremental.fetch',side_effect=fake):
            state,meta=source({"schema":2,"rows":{},"snapshot_at":now},budget_reader=lambda:self.fail("Unchanged source must not query quota"))
        self.assertTrue(meta["unchanged"]);self.assertEqual(len(calls),2)
    def test_old_ad_changes_and_disappearance_are_retained(self):
        first=advance({},[("2026-10-23T10:00:00Z",[row(50000)])])
        changed=advance(first,[("2026-10-24T10:00:00Z",[row(51000)])])
        self.assertEqual(len(changed["rows"]["x"]["material_edits"]),1)
        self.assertEqual(advance(changed,[("2026-10-25T10:00:00Z",[])])["rows"],changed["rows"])
    def test_repeated_snapshot_no_new_event(self):
        batch=[("2026-10-23T10:00:00Z",[row(50000)]),("2026-10-24T10:00:00Z",[row(51000)])]
        state=advance({},batch)
        self.assertEqual(advance(state,batch),state)
    def test_renewed_publication_is_not_backdated(self):
        first=advance({},[("2026-10-23T10:00:00Z",[row(50000)])])
        changed=advance(first,[("2026-10-24T10:00:00Z",[row(51000,"2026-10-24T09:00:00Z")])])
        self.assertEqual(changed["rows"]["x"]["material_edits"],[])

    def test_checkpoint_compression_preserves_all_history_and_unicode(self):
        from realt_test.incremental import save,load
        class Memory:
            def __init__(self):self.data={}
            def get_state(self,key):return self.data.get(key)
            def set_state(self,key,value):self.data[key]=value
        db=Memory()
        state=advance({},[("2026-10-23T10:00:00Z",[row(50000)])])
        state['padding']='История без потери данных '*50000
        save(db,state)
        self.assertEqual(load(db),state)
