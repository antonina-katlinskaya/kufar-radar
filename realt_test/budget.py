"""Read-only account-wide D1 budget; no telemetry means no promotion."""
import datetime as dt
import json
import os
import urllib.request

READ_LIMIT, WRITE_LIMIT, SAFETY_FRACTION = 5_000_000, 100_000, 0.80


def evaluate(groups):
    reads = sum(int(g["sum"]["rowsRead"]) for g in groups)
    writes = sum(int(g["sum"]["rowsWritten"]) for g in groups)
    if reads < 0 or writes < 0:
        raise ValueError("Invalid usage counters")
    return {"safe": reads < READ_LIMIT*SAFETY_FRACTION and writes < WRITE_LIMIT*SAFETY_FRACTION,
            "rows_read": reads, "rows_written": writes, "read_limit": READ_LIMIT,
            "write_limit": WRITE_LIMIT, "safety_fraction": SAFETY_FRACTION}


def read_budget(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    account, token = os.getenv("CF_ACCOUNT_ID", ""), os.getenv("CF_D1_API_TOKEN", "")
    if not account or not token:
        return {"safe": False, "reason": "Cloudflare analytics credential unavailable"}
    day = now.astimezone(dt.timezone.utc).date().isoformat()
    query = ('query {viewer{accounts(filter:{accountTag:"'+account+'"}){'
             'd1AnalyticsAdaptiveGroups(limit:1000,filter:{date_geq:"'+day+'",date_leq:"'+day+
             '"}){dimensions{databaseId}sum{rowsRead rowsWritten}}}}}')
    request = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql",
              data=json.dumps({"query":query}).encode(), headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=25) as response: payload=json.load(response)
        if payload.get("errors"): raise ValueError("Analytics rejected")
        accounts=payload["data"]["viewer"]["accounts"]
        if len(accounts)!=1 or not accounts[0]["d1AnalyticsAdaptiveGroups"]: raise ValueError("Missing telemetry")
        return {**evaluate(accounts[0]["d1AnalyticsAdaptiveGroups"]),"checked_at":now.isoformat(),"utc_date":day}
    except Exception:
        return {"safe":False,"reason":"Cloudflare analytics unavailable or permission missing"}
