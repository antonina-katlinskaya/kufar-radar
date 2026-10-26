"""Realt-only persisted observation checkpoint; no Kufar tables are modified."""
import csv
import gzip
import io
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError

from realt_test.sources import REPOSITORY, TRACKED, EMAILS, fetch
from realt_test.backdated import material_change

KEY = "realt_owner_observations_v2"
FIELDS = ("uuid","code","userUuid","contactName","createdAt","updatedAt",
          "rooms","areaTotal","price","priceCurrency","storey","address","streetName","houseNumber","quarter","title","snapshot_at","observed_at")
MAX_AGE = timedelta(minutes=90)


def checked_time(value):
    out = datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if out.tzinfo is None: raise RuntimeError("Snapshot time has no timezone")
    return out


def load(db):
    value = db.get_state(KEY)
    if not value: return {}
    state = json.loads(value)
    if state.get("schema") != 2 or not isinstance(state.get("rows"),dict):
        raise RuntimeError("Invalid Realt observation checkpoint")
    return state


def compact(row):
    return {k: row.get(k) for k in FIELDS}


def advance(previous, snapshots):
    """Preserve disappeared/old listings, process only newer observations."""
    state = json.loads(json.dumps(previous or {"schema":2,"rows":{}}))
    rows = state["rows"]
    for stamp, batch in sorted(snapshots,key=lambda x:x[0]):
        for row in batch:
            who = TRACKED.get(str(row.get("userUuid") or ""))
            if not who: continue
            email_who=EMAILS.get(str(row.get("contactEmail") or "").strip().lower())
            if email_who and email_who!=who:
                raise RuntimeError("Conflicting employee identity in incremental snapshot")
            uid = str(row.get("uuid") or "")
            if not uid: raise RuntimeError("Tracked listing has no UUID")
            before = rows.get(uid)
            if before and checked_time(stamp) <= checked_time(before["last_seen_at"]): continue
            edits = list(before.get("material_edits",[])) if before else []
            historical = list(before.get("historical_material_edits",[])) if before else []
            if before and before.get("createdAt")!=row.get("createdAt"):
                historical.extend(edits);edits=[]
            if before:
                change = material_change(before,row,row.get("observed_at") or stamp)
                if change and change not in edits: edits.append(change)
            rows[uid] = {**compact(row),"person":who,"first_seen_at":before["first_seen_at"] if before else stamp,
                         "last_seen_at":stamp,"material_edits":edits,"historical_material_edits":historical}
    return state


class BudgetPause(RuntimeError):
    def __init__(self,budget):
        self.budget=budget
        super().__init__(budget.get("reason") or "D1 free budget safety threshold reached")


def source(state, budget_reader=None):
    tree=json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/git/trees/main?recursive=1"))
    if tree.get("truncated"):raise RuntimeError("Incomplete collector tree")
    ref=tree["sha"]; base=f"https://raw.githubusercontent.com/{REPOSITORY}/{ref}/"
    paths={v["path"] for v in tree["tree"]}
    marker=None
    if "data/collection_state.json" in paths:
        marker=json.loads(fetch(base+"data/collection_state.json"))
        if marker.get("complete") is not True:raise RuntimeError("Collector snapshot is incomplete")
        latest=marker["snapshot_at"]
    else:
        current=list(csv.DictReader(io.StringIO(fetch(base+"data/analytics/current_listings.csv").decode("utf-8-sig"))))
        if not current:raise RuntimeError("Current source snapshot is empty")
        latest=max(r["snapshot_at"] for r in current)
    age=datetime.now(timezone.utc)-checked_time(marker.get("completed_at",latest) if marker else latest)
    if age<timedelta(minutes=-5) or age>MAX_AGE:raise RuntimeError("Current Realt snapshot is stale or future")
    if state.get("snapshot_at")==latest:
        return state,{"unchanged":True,"source_ref":ref,"latest_snapshot_at":latest}
    if budget_reader:
        budget=budget_reader()
        if not budget.get("safe"):raise BudgetPause(budget)
    previous_time=state.get("snapshot_at")
    snapshots=[]
    for p in sorted(paths):
        match=re.fullmatch(r"data/raw/(\d{4}-\d\d-\d\d)_\d\d-\d\d_etazhi\.json(\.gz)?",p)
        if not match:continue
        day=match[1]
        if day<"2026-10-23":continue
        if previous_time and day<previous_time[:10]:continue
        if previous_time:
            file_time=checked_time(match[1]+"T"+p.split("_")[1].replace("-",":")+":00+00:00")
            if file_time.replace(second=0,microsecond=0)<=checked_time(previous_time).replace(second=0,microsecond=0):continue
        raw=fetch(base+p)
        data=json.loads(gzip.decompress(raw) if p.endswith(".gz") else raw)
        stamp=data["snapshot_at"]
        if previous_time and checked_time(stamp)<=checked_time(previous_time):continue
        snapshots.append((stamp,data["minsk_mir_objects"]))
    if not marker:
        snapshots.append((latest,current))
    if not snapshots or max(x[0] for x in snapshots)!=latest:
        raise RuntimeError("Latest complete snapshot is absent from the archive")
    result=advance(state,snapshots)
    latest_ids={str(row["uuid"]) for stamp,batch in snapshots if stamp==latest for row in batch}
    for row in result["rows"].values():
        row["present_in_latest_snapshot"]=row["uuid"] in latest_ids
    result.update(snapshot_at=latest,schema=2)
    return result,{"unchanged":False,"source_ref":ref,"latest_snapshot_at":latest,
                  "new_snapshots":len(snapshots),"checkpoint_key":KEY}


def save(db,state):
    encoded=json.dumps(state,ensure_ascii=False,separators=(",",":"))
    if len(encoded.encode())>700_000:raise RuntimeError("Realt checkpoint exceeds safe GitHub state budget")
    db.set_state(KEY,encoded)
