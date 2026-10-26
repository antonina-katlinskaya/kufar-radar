"""Read-only cross-source candidate evidence for the retained profile.

Matches area/rooms/price between separate platforms. These are clues,
not proof of person identity. No notifications or state updates.
"""
import csv, io, json
from collections import defaultdict, Counter
from decimal import Decimal
from radar.d1 import D1
from realt_test.sources import fetch, REPOSITORY

PROFILES={"Алёна Довгун":"11093294"}
def number(x):
    try: return Decimal(str(x))
    except Exception: return None
def main():
    rows=list(csv.DictReader(io.StringIO(fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/main/data/analytics/current_listings.csv").decode("utf-8-sig"))))
    index=defaultdict(list)
    for row in rows:
        area,rooms,price=number(row.get("areaTotal")),number(row.get("rooms")),number(row.get("price"))
        if None not in (area,rooms,price) and str(row.get("priceCurrency")) in ("978","EUR"):
            index[(area,rooms,price)].append(row)
    db=D1()
    result={}
    for name,pid in PROFILES.items():
        ads=db.query("SELECT ad_id,area,rooms,price_eur FROM kufar_ads_live WHERE profile_id=? AND present=1 LIMIT 1500",[pid])
        evidence=defaultdict(lambda:{"count":0,"examples":[]})
        for ad in ads:
            key=(number(ad.get("area")),number(ad.get("rooms")),number(ad.get("price_eur")))
            if None in key:continue
            for hit in index.get(key,[]):
                uid=str(hit.get("userUuid") or "")
                item=evidence[uid];item["count"]+=1
                if len(item["examples"])<3:item["examples"].append({"realt_code":hit.get("code"),"kufar_ad":ad.get("ad_id"),"name":hit.get("contactName")})
        result[name]={"profile_id":pid,"kufar_ads":len(ads),"candidates":dict(evidence)}
    print("CROSS_SOURCE_EVIDENCE="+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
