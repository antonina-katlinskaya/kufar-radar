"""Persistent Realt-only acknowledgement state in the existing D1 state table.

This key is never used by Kufar alerts. Writes only follow Telegram delivery.
"""
import json
from realt_test.dedup import select_new_reviews
KEY="realt_private_owner_review_fingerprints_v1"

def load(db):
    raw=db.get_state(KEY)
    if not raw:return {}
    data=json.loads(raw)
    if not isinstance(data,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in data.items()):
        raise RuntimeError("Invalid Realt notification history")
    return data

def pending(db,result):
    return select_new_reviews(result,load(db))

def acknowledge(db,delivered):
    """Persist only cases confirmed delivered, never the whole proposed batch."""
    if not delivered:return
    from realt_test.dedup import fingerprint
    state=load(db)
    for item in delivered:
        if item.get("status")!="REVIEW" or not item.get("uuid"):
            raise RuntimeError("Invalid review acknowledgement")
        state[str(item["uuid"])]=fingerprint(item)
    db.set_state(KEY,json.dumps(state,ensure_ascii=False,sort_keys=True))
