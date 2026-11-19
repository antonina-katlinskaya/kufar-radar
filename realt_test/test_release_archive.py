import gzip,hashlib,io,json,unittest,zipfile
from realt_test.incremental import release_snapshot

class ReleaseReaderTests(unittest.TestCase):
    def packet(self):
        raw=gzip.compress(json.dumps({'snapshot_at':'2026-10-26T16:00:00Z','minsk_mir_objects':[{'uuid':'x','price':100}]}).encode())
        manifest={'snapshot_at':'2026-10-26T16:00:00Z','raw_members':['source.json.gz'],'sha256':{'source.json.gz':hashlib.sha256(raw).hexdigest()}}
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('manifest.json',json.dumps(manifest));z.writestr('source.json.gz',raw)
        packet=stream.getvalue()
        entry={'url':'https://github.com/antonina-katlinskaya/realt-collector/releases/download/test/snapshot.zip','bytes':len(packet),'sha256':hashlib.sha256(packet).hexdigest(),'snapshot_at':manifest['snapshot_at'],'raw_members':['source.json.gz'],'rows':1}
        return packet,entry
    def test_release_snapshot_roundtrip(self):
        packet,entry=self.packet();result=release_snapshot(entry,reader=lambda u:packet)
        self.assertEqual(result[0][1],[{'uuid':'x','price':100}])

    def test_multiple_source_members_count_together(self):
        first=gzip.compress(json.dumps({'snapshot_at':'2026-10-26T16:00:00Z','minsk_mir_objects':[{'uuid':'a'}]}).encode())
        second=gzip.compress(json.dumps({'snapshot_at':'2026-10-26T16:00:00Z','minsk_mir_objects':[{'uuid':'b'},{'uuid':'c'}]}).encode())
        members={'first.json.gz':first,'second.json.gz':second}
        manifest={'snapshot_at':'2026-10-26T16:00:00Z','raw_members':list(members),
                  'sha256':{k:hashlib.sha256(v).hexdigest() for k,v in members.items()}}
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('manifest.json',json.dumps(manifest))
            for name,raw in members.items():archive.writestr(name,raw)
        packet=stream.getvalue()
        entry={'url':'https://github.com/antonina-katlinskaya/realt-collector/releases/download/test/snapshot.zip',
               'bytes':len(packet),'sha256':hashlib.sha256(packet).hexdigest(),
               'snapshot_at':manifest['snapshot_at'],'raw_members':list(members),'rows':3}
        self.assertEqual(sum(len(rows) for _,rows in release_snapshot(entry,reader=lambda u:packet)),3)
        with self.assertRaisesRegex(RuntimeError,'Release RAW count mismatch'):
            release_snapshot({**entry,'rows':4},reader=lambda u:packet)
    def test_corrupt_or_untrusted_data_is_never_compared(self):
        packet,entry=self.packet()
        with self.assertRaises(RuntimeError):release_snapshot(entry,reader=lambda u:packet+b'corrupt')
        with self.assertRaises(RuntimeError):release_snapshot({**entry,'url':'https://example.invalid/archive'},reader=lambda u:self.fail('Untrusted URL requested'))
