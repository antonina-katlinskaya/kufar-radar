"""Match Realt employees with monitored Kufar profiles via phone numbers.

Runs only in isolated test branch. No Telegram sends, no state changes and no
raw phone numbers written to logs or artifacts.
"""
import csv
import io
import json
import re
from collections import defaultdict
from urllib.request import urlopen
from radar.d1 import D1
from radar.config import KUFAR_PROFILES

URL="https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/analytics/current_listings.csv"
PROFILES={str(p["id"]):p["label"] for p in KUFAR_PROFILES}

def phones(value):
    out=set()
    def walk(v,key=""):
        if isinstance(v,dict):
            for k,x in v.items():
                if re.search(r"phone|telefon|телефон|mobile|msisdn",str(k),re.I):
                    if isinstance(x,(str,int,float)):
                        digits=re.sub(r"\D","",str(x))
                        if len(digits)>=9:out.add(digits[-9:])
                    else:walk(x,str(k))
                elif isinstance(x,(dict,list)):walk(x,str(k))
        elif isinstance(v,list):
            for x in v:walk(x,key)
        elif key and isinstance(v,(str,int)):
            digits=re.sub(r"\D","",str(v))
            if len(digits)>=9:out.add(digits[-9:])
    walk(value)
    return out

def run():
    with urlopen(URL,timeout=60) as req:
        rows=list(csv.DictReader(io.StringIO(req.read().decode("utf-8-sig"))))
    realt=defaultdict(lambda:{"phones":set(),"names":set(),"emails":set(),"count":0})
    for r in rows:
        uid=r.get("userUuid")
        if not uid:continue
        info=realt[uid];info["count"]+=1
        info["names"].add(r.get("contactName") or "")
        info["emails"].add(r.get("contactEmail") or "")
        info["phones"]|=phones({"contactPhone":r.get("contactPhone")})
    db=D1()
    matches=[];source_counts={}
    for profile,name in PROFILES.items():
        records=db.query("SELECT raw_json FROM kufar_ads_live WHERE profile_id=? AND present=1 LIMIT 200",[profile])
        numbers=set()
        for record in records:
            try:numbers|=phones(json.loads(record.get("raw_json") or "{}"))
            except(ValueError,TypeError):pass
        source_counts[name]={"kufar_rows":len(records),"phone_fingerprints":len(numbers)}
        for uid,entry in realt.items():
            common=numbers&entry["phones"]
            if common:
                matches.append({"profile_id":profile,"name":name,"realt_user_uuid":uid,
                    "realt_names":sorted(entry["names"]),"realt_emails":sorted(entry["emails"]),
                    "realt_active_ads":entry["count"],"matching_phone_count":len(common)})
    names_summary=[{"uuid":uid,"names":sorted(v["names"]),"emails":sorted(v["emails"]),"listings":v["count"],"has_realt_phone":bool(v["phones"])} for uid,v in realt.items()]\n    candidate_matches=[]\n    for p,full in PROFILES.items():\n        first=full.split()[0].casefold()\n        for v in names_summary:\n            if any(first == n.strip().casefold() or full.casefold() == n.strip().casefold() for n in v["names"]):\n                candidate_matches.append({"profile_id":p,"kufar_name":full,**v,"match_kind":"NAME_ONLY_UNVERIFIED"})\n    result={"realt_users":len(realt),"profiles":source_counts,"matches":matches,"name_candidates":candidate_matches,
            "verified_identity_count":len(matches),"no_phone_values_exported":True}
    import os
    os.makedirs("realt_test",exist_ok=True)
    with open("realt_test/identity_results.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":run()
