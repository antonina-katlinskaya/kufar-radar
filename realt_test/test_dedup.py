import unittest
from realt_test.dedup import select_new_reviews


class DedupTests(unittest.TestCase):
    def item(self, **changes):
        result={"uuid":"a1","person":"Алёна Довгун","rooms":"1",
                "area":"45.34","price":"52232","currency":"978",
                "status":"REVIEW","reason":"different price"}
        result.update(changes)
        return result

    def test_first_review_then_no_repeat(self):
        result={"items":[self.item()]}
        new, saved=select_new_reviews(result,{})
        self.assertEqual(len(new),1)
        again,_=select_new_reviews(result,saved)
        self.assertEqual(again,[])

    def test_change_realerts_once(self):
        old={"items":[self.item()]}
        _, saved=select_new_reviews(old,{})
        changed={"items":[self.item(price="60000")]}
        new, updated=select_new_reviews(changed,saved)
        self.assertEqual(len(new),1)
        self.assertNotEqual(saved["a1"],updated["a1"])

    def test_ok_and_archived_do_not_erase_history(self):
        _,saved=select_new_reviews({"items":[self.item()]},{})
        new,updated=select_new_reviews({"items":[self.item(status="OK")]},saved)
        self.assertEqual(new,[])
        self.assertEqual(saved,updated)
        new,updated=select_new_reviews({"items":[]},updated)
        self.assertEqual(new,[])
        self.assertEqual(saved,updated)

    def test_ignores_untracked_ok_and_rejects_invalid_state(self):
        new, state=select_new_reviews({"items":[self.item(status="OK")]},{})
        self.assertEqual((new,state),([] ,{}))
        with self.assertRaises(ValueError):
            select_new_reviews({"items":[]},[])
        with self.assertRaises(ValueError):
            select_new_reviews({"items":[self.item(uuid="")]},{})


class MigrationDedupTests(unittest.TestCase):
    def test_csv_numeric_strings_do_not_repeat_after_json_migration(self):
        import hashlib,json
        from realt_test.dedup import fingerprint,select_new_reviews
        item={'uuid':'x','person':'Name','rooms':3,'area':44.42,'price':60594,'currency':978,'status':'REVIEW','reason':'same','material_edits':[]}
        old={**item,'rooms':'3','area':'44.42','price':'60594.0','currency':'978'}
        old_hash=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(fingerprint(item),fingerprint(old))
        self.assertEqual(select_new_reviews({'items':[item]},{'x':old_hash})[0],[])
        changed={**item,'price':60595}
        self.assertEqual(len(select_new_reviews({'items':[changed]},{'x':old_hash})[0]),1)
