"""Read archived collector snapshots without changing the collector."""
import csv
import io
import json
import re
from urllib.request import Request, urlopen

from realt_test.policy import created_in_window

REPOSITORY = "antonina-katlinskaya/realt-collector"
TRACKED = {
    "77ff7ab0-6e68-11ee-818e-0935d63487ea": "Ирина Барашенко",
    "53504f40-a386-11ec-beec-b72528b8f1cb": "Анастасия Биянова",
    "5f3a9050-b4b1-11f0-a915-7b17e0ec0a88": "Анна Зенкевич",
    "25ad48c4-facc-4b01-a773-0bb74a2d4fbc": "Жанна Вакуленчик",
}
EMAILS = {
    "i.s.barashenko@minsk.etagi.com": "Ирина Барашенко",
    "a.v.biyanova@minsk.etagi.com": "Анастасия Биянова",
    "a.p.zenkevich@minsk.etagi.com": "Анна Зенкевич",
    "zh.a.vakulenchik@minsk.etagi.com": "Жанна Вакуленчик",
}


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "Realt-private-audit"}), timeout=60) as response:
        return response.read()


def merge_snapshots(snapshots):
    selected = {}
    for observed_at, rows in sorted(snapshots, key=lambda v: v[0]):
        for row in rows:
            who = TRACKED.get(str(row.get("userUuid") or ""))
            email_who = EMAILS.get(str(row.get("contactEmail") or "").strip().lower())
            if who and email_who and who != email_who:
                raise RuntimeError("Conflicting employee identity in Realt snapshot")
            if not who or not created_in_window(row.get("createdAt")):
                continue
            key = str(row.get("uuid") or "")
            if not key:
                raise RuntimeError("Selected listing has no UUID")
            old = selected.get(key)
            selected[key] = {**row, "person": who, "last_seen_at": observed_at,
                             "first_seen_at": old["first_seen_at"] if old else observed_at}
    return list(selected.values())


def load_realt():
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/git/trees/main?recursive=1"))
    if tree.get("truncated"):
        raise RuntimeError("Collector archive tree is incomplete")
    ref = tree["sha"]
    raw_base = f"https://raw.githubusercontent.com/{REPOSITORY}/{ref}/"
    paths = sorted(v["path"] for v in tree["tree"] if re.fullmatch(
        r"data/raw/2026-10-(22|23|24|25)_\d{2}-\d{2}_etazhi.json", v["path"]))
    if {p[9:19] for p in paths} != {f"2026-10-{d}" for d in range(22, 26)}:
        raise RuntimeError("Missing a day of the requested Realt archive")
    snapshots = []
    for path in paths:
        data = json.loads(fetch(raw_base + path))
        snapshots.append((data["snapshot_at"], data["minsk_mir_objects"]))
    current = list(csv.DictReader(io.StringIO(fetch(raw_base + "data/analytics/current_listings.csv").decode("utf-8-sig"))))
    if not current:
        raise RuntimeError("Current Realt snapshot is empty")
    current_ids = {str(r["uuid"]) for r in current}
    snapshots.append((max(r["snapshot_at"] for r in current), current))
    rows = merge_snapshots(snapshots)
    for row in rows:
        row["present_in_latest_snapshot"] = str(row["uuid"]) in current_ids
    return rows, {"source_ref": ref, "archive_paths": paths,
                  "archive_snapshots": len(paths), "latest_snapshot_at": snapshots[-1][0],
                  "latest_source_rows": len(current)}
