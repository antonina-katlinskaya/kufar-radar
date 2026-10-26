"""Detect material edits to older Realt ads from sequential collector snapshots."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

CORE = (("price", "цена"), ("priceCurrency", "валюта"),
        ("areaTotal", "площадь"), ("rooms", "комнаты"))
CONTEXT = (("storey", "этаж"), ("address", "адрес"), ("houseNumber", "дом"))

def dt(value):
    try:
        out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return out.replace(tzinfo=timezone.utc) if out.tzinfo is None else out
    except (TypeError, ValueError):
        return None

def equal(a, b):
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, TypeError, ValueError):
        return str(a or "").strip() == str(b or "").strip()

def material_change(before, after, observed_at):
    """Mirror Kufar: core edit to an ad older than 24h, context fields secondary."""
    created = dt(after.get("createdAt")) or dt(before.get("createdAt"))
    observed = dt(observed_at)
    previous_created = dt(before.get("createdAt"))
    current_created = dt(after.get("createdAt"))
    if not previous_created or not current_created or previous_created != current_created:
        return None
    if not created or not observed or (observed - created).total_seconds() < 86400:
        return None
    core = [(label, before.get(key), after.get(key)) for key, label in CORE
            if not equal(before.get(key), after.get(key))]
    if not core:
        return None
    context = [(label, before.get(key), after.get(key)) for key, label in CONTEXT
               if not equal(before.get(key), after.get(key))]
    return {"observed_at": observed_at, "changes": [
        {"field": label, "before": old, "after": new}
        for label, old, new in core + context]}
