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
    def test_corrupt_or_untrusted_data_is_never_compared(self):
        packet,entry=self.packet()
        with self.assertRaises(RuntimeError):release_snapshot(entry,reader=lambda u:packet+b'corrupt')
        with self.assertRaises(RuntimeError):release_snapshot({**entry,'url':'https://example.invalid/archive'},reader=lambda u:self.fail('Untrusted URL requested'))
