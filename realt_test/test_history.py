import unittest
from realt_test.history import KEY, load, pending, acknowledge
from realt_test.history import claim

class Db:
    def __init__(self):
        self.state = {}
        self.writes = 0
    def get_state(self, key): return self.state.get(key)
    def set_state(self, key, value):
        self.state[key] = value
        self.writes += 1

def example(price="51000"):
    return {"uuid":"x1", "person":"Алёна Довгун", "status":"REVIEW",
            "rooms":"1", "area":"45.34", "price":price,
            "currency":"978", "reason":"different price"}

class HistoryTests(unittest.TestCase):
    def test_acknowledgements(self):
        db = Db()
        items, _ = pending(db, {"items":[example()]})
        self.assertEqual(len(items), 1)
        self.assertEqual(db.writes, 0)
        acknowledge(db, items)
        self.assertEqual(pending(db, {"items":[example()]})[0], [])
        self.assertEqual(len(pending(db, {"items":[example("52000")]})[0]), 1)
    def test_no_unrelated_writes(self):
        db = Db()
        db.state["kufar_state"] = "original"
        acknowledge(db, [])
        self.assertEqual(db.writes, 0)
        acknowledge(db, [example()])
        self.assertEqual(db.state["kufar_state"], "original")
        self.assertIn(KEY, db.state)
    def test_invalid_state(self):
        db = Db()
        db.state[KEY] = "[]"
        with self.assertRaises(RuntimeError): load(db)
    def test_backdated_delivery_is_acknowledged_without_repeating(self):
        db = Db()
        item = {**example(), "status": "BACKDATED", "material_edits": [{"changes": [{"field":"цена","before":51000,"after":52000}]}]}
        acknowledge(db, [item])
        self.assertEqual(pending(db, {"items":[item]})[0], [])
    def test_uncertain_claim_never_retries_automatically(self):
        db=Db();item=example()
        claim(db,item)
        self.assertEqual(pending(db,{"items":[item]})[0],[])
        with self.assertRaises(RuntimeError):claim(db,item)
        acknowledge(db,[item])
        self.assertEqual(pending(db,{"items":[item]})[0],[])
