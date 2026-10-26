"""Read-only discovery of precisely the ten approved employees."""
import csv, io, json, re
from collections import defaultdict
from urllib.request import urlopen
from radar.d1 import D1
from realt_test.sources import REPOSITORY, fetch

NAMES=("Алёна Довгун","Ирина Барашенко","Хатковская","Анастасия Биянова","Анна Зенкевич","Жанна Вакуленчик","Дмитрий Спиридонов","Дарья Иванова","Ольга Михальченко")
def main():
    rows=list(csv.DictReader(io.StringIO(fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/main/data/analytics/current_listings.csv").decode("utf-8-sig"))))
    users=defaultdict(lambda:{"names":set(),"emails":set(),"count":0})
    for row in rows:
        info=users[row.get("userUuid") or ""];info["names"].add(row.get("contactName") or "");info["emails"].add(row.get("contactEmail") or "");info["count"]+=1
    candidates={}
    for name in NAMES:
        first=name.split()[0].casefold()
        candidates[name]=[{"uuid":k,"names":sorted(v["names"]),"emails":sorted(e for e in v["emails"] if e and e!="etagiinternational@gmail.com"),"current_ads":v["count"]} for k,v in users.items() if any(first==x.casefold() or name.casefold()==x.casefold() or (len(name.split())>1 and name.split()[-1].casefold() in x.casefold()) for x in v["names"])]
    db=D1()
    profiles=db.query("SELECT profile_id,account_id,contact_names,company FROM kufar_profiles")
    kufar={name:[{"profile_id":p.get("profile_id"),"account_id":p.get("account_id"),"contact_names":p.get("contact_names")} for p in profiles if name.casefold() in str(p.get("contact_names") or "").casefold() or (len(name.split())>1 and name.split()[-1].casefold() in str(p.get("contact_names") or "").casefold())] for name in NAMES}
    print(json.dumps({"realt_candidates":candidates,"kufar_candidates":kufar,"kufar_profile_rows":len(profiles)},ensure_ascii=False))
if __name__=="__main__":main()
