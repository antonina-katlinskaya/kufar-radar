"""Read-only historical Realt x BIR test for October 22-25, 2026.

No Telegram integration: produces an Actions artifact only. This is a deliberate
guard against accidentally notifying the Kufar subscribers.
"""
import csv
import io
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.request import urlopen

from radar.d1 import D1
from radar.source_snapshot import load_bir_snapshot
from realt_test.policy import created_in_window, area_equal

SNAPSHOTS = "https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/analytics/current_listings.csv"
OUT = "realt_test/results.json"
# Confirmed by matching email contact and name in the collected Realt data.
TRACKED = {
    "i.s.barashenko@minsk.etagi.com": "Ирина Барашенко",
}


def dec(value):
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def run():
    # The snapshot is fetched read-only, collector queries and cadence unchanged.
    with urlopen(SNAPSHOTS, timeout=60) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    db = D1(os.getenv("CF_HISTORY_D1_DATABASE_ID"))
    bir, bir_checked = load_bir_snapshot(db)
    selected = []
    for row in rows:
        who = TRACKED.get(str(row.get("contactEmail") or "").strip().lower())
        if who and created_in_window(row.get("createdAt")):
            selected.append((row, who))
    items = []
    for row, who in selected:
        rooms = dec(row.get("rooms"))
        area = dec(row.get("areaTotal"))
        price = dec(row.get("price"))
        candidates = [b for b in bir if rooms is not None and dec(b.rooms) == rooms and area_equal(area, b.area)]
        price_confirmed = (
            str(row.get("priceCurrency")) in {"978", "EUR"}
            and price is not None
        )
        exact = next((b for b in candidates if price_confirmed and dec(b.price_fast_eur) == price), None)
        if exact:
            status = "OK"
            reason = "Совпали комнаты, площадь (точно до 0,01) и спеццена BIR"
        elif not price_confirmed:
            status = "REVIEW"
            reason = "Валюта Realt не подтверждена как EUR, ценовое нарушение не выставляется"
        else:
            status = "REVIEW"
            reason = "Нет полного совпадения; требуется проверка возможной неоднозначности"
        items.append({
            "code": row.get("code"), "uuid": row.get("uuid"), "person": who,
            "created_at": row.get("createdAt"), "updated_at": row.get("updatedAt"),
            "rooms": row.get("rooms"), "area": row.get("areaTotal"),
            "price": row.get("price"), "currency": row.get("priceCurrency"),
            "status": status, "reason": reason,
            "matching_bir_key": exact.object_key if exact else None,
            "bir_room_area_candidates": len(candidates),
        })
    output = {
        "scope": "2026-10-22..2026-10-25", "bir_checked_at": bir_checked,
        "realt_source": SNAPSHOTS, "source_rows": len(rows),
        "checked": len(items), "status_counts": dict(Counter(v["status"] for v in items)),
        "coverage_warning": "Only Realt contact email verified for Irina Barashenko; other controlled people remain unverified and are not silently included.",
        "notification_sent": False, "items": items,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in output.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    run()
