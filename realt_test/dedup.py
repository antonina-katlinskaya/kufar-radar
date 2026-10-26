"""Determine new/changed review cases without notifying other subscribers.

State is a mapping of Realt listing UUID to its last reported review fingerprint.
A caller must save the state durably only after confirmed owner-only delivery.
"""
import hashlib
import json


def fingerprint(item):
    values = {key: item.get(key) for key in
              ("uuid", "person", "rooms", "area", "price", "currency", "status", "reason")}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


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
        if item.get("status") != "REVIEW":
            continue
        value = fingerprint(item)
        if acknowledged.get(uid) != value:
            pending.append(item)
            next_state[uid] = value
    return pending, next_state
