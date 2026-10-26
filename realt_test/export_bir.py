"""Export once after the existing Bir scan. One SELECT, no D1 writes or new source scan."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta
from realt_test.github_store import GitHubFile
from realt_test.bir_snapshot import decode

SQL = """SELECT id, house,
json_extract(detail_json,'$.nomerPomeschenia') AS unit_no,
json_extract(detail_json,'$.cena') AS regular_price,
json_extract(detail_json,'$.Rassrochka10_cena') AS special_price,
json_extract(detail_json,'$.obschPloschad') AS area,
json_extract(detail_json,'$.comnat') AS rooms,
json_extract(detail_json,'$.etaj') AS floor,
json_extract(detail_json,'$.adres') AS address
FROM bir_objects WHERE present=1"""

def payload(rows, checked_at):
    items = [{'object_key':str(r['id']),'building_name':r['house'],
              'official_address':r.get('address'),'unit_no':str(r['unit_no']) if r.get('unit_no') is not None else None,
              'price_regular_eur':r['regular_price'],'price_fast_eur':r['special_price'],
              'area':r['area'],'rooms':r['rooms'],'floor':r['floor']} for r in rows]
    out = {'schema':1,'complete':True,'checked_at':checked_at,'exported_at':datetime.now(timezone.utc).isoformat(),
           'source':'existing Bir history scan','items':items}
    decode(out)
    return out

def main():
    meta=json.loads(Path(os.environ['BIR_EXPORT_META_PATH']).read_text())
    checked=meta['checked_at']
    # Stop before querying if the original scan was not successful/fresh.
    stamp=datetime.fromisoformat(checked.replace('Z','+00:00'))
    age=datetime.now(timezone.utc)-stamp
    if not meta.get('ok') or not timedelta(minutes=-5)<=age<=timedelta(minutes=35):
        raise RuntimeError('Original Bir scan is not fresh/successful')
    file=GitHubFile('realt-bir-snapshot','realt_state/bir.json')
    previous=file.read()
    if previous.get('checked_at','')>=checked:
        print(json.dumps({'export_skipped':'already exported','checked_at':checked}));return
    account=os.environ['CF_ACCOUNT_ID'];db=os.environ['BIR_D1_DATABASE_ID']
    req=Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{db}/query',
                data=json.dumps({'sql':SQL}).encode(),method='POST',headers={
                'Authorization':'Bearer '+os.environ['CF_D1_API_TOKEN'],'Content-Type':'application/json'})
    with urlopen(req,timeout=60) as response:
        result=json.load(response)
    if not result.get('success') or len(result.get('result',[]))!=1 or not result['result'][0].get('success'):
        raise RuntimeError('Bir export query failed')
    block=result['result'][0]
    out=payload(block['results'],checked)
    file.write(out)
    print(json.dumps({'exported':len(out['items']),'checked_at':checked,
                      'd1_rows_read':block.get('meta',{}).get('rows_read'),
                      'd1_rows_written':block.get('meta',{}).get('rows_written')}))

if __name__=='__main__': main()
