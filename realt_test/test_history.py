import unittest
from realt_test.history import KEY, load, pending, acknowledge

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
