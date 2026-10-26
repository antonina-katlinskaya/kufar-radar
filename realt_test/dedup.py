"""Determine new/changed review cases without notifying other subscribers.

State is a mapping of Realt listing UUID to its last reported review fingerprint.
A caller must save the state durably only after confirmed owner-only delivery.
"""
import hashlib
import json


NUMERIC = ('rooms','area','price','currency')

def _hash(values):
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def legacy_fingerprints(item):
    """Bridge old CSV-string hashes and raw-JSON numeric values without re-sending."""
    from itertools import product
    from realt_test.policy import decimal_value
    values={key:item.get(key) for key in ('uuid','person','rooms','area','price','currency','status','reason','material_edits')}
    choices=[]
    for key in NUMERIC:
        value=values[key];options=[value]
        number=decimal_value(value)
        if number is not None:
            options.extend([str(value),format(number,'f'),format(number.normalize(),'f'),str(float(number))])
        choices.append(list({(type(v).__name__,str(v)):v for v in options}.values()))
    candidates=[{**values,**dict(zip(NUMERIC,c))} for c in product(*choices)]
    hashes={_hash(v) for v in candidates}
    # The first deployed v1 hash predates the material_edits field entirely.
    if not item.get('material_edits'):
        hashes.update(_hash({k:v for k,v in candidate.items() if k!='material_edits'}) for candidate in candidates)
    return hashes

def fingerprint(item):
    values = {key: item.get(key) for key in
              ("uuid", "person", "rooms", "area", "price", "currency", "status", "reason", "material_edits")}
    from realt_test.policy import decimal_value
    for key in NUMERIC:
        number=decimal_value(values.get(key))
        if number is not None:values[key]=format(number.normalize(),'f')
    return _hash(values)


def select_new_reviews(result, acknowledged):
    """Returns only unreported REVIEW cases and prospective next state.

    Never clear earlier fingerprints just because a listing was absent in a snapshot.
    This preserves history for archived/disappeared listings.
    """
    if not isinstance(acknowledged, dict):
        raise ValueError("Acknowledgement state must be a mapping")
    next_state = dict(acknowledged)
    pending = []
    for item in result.get("items", []):
        uid = str(item.get("uuid") or "")
        if not uid:
            raise ValueError("Realt listing UUID is missing")
        if item.get("status") not in ("REVIEW", "BACKDATED", "RESOLVED"):
            continue
        value = fingerprint(item)
        previous=acknowledged.get(uid)
        if previous != value and previous not in legacy_fingerprints(item):
            pending.append(item)
            next_state[uid] = value
    return pending, next_state
