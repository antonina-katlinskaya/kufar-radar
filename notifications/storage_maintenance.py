"""Bounded retention of redundant source metadata; keep prices and audit history.

Historical Kufar versions retain all typed price/apartment columns, source
currency/calculator, publication time, paid promotions and contact metadata.
Full active-card payloads are never compacted. No price or violation rows are
deleted. Each daily run has at most 2,000 candidate rows across both databases.
"""
import json,os,urllib.request

TASKS=[
 ('43422bcb-fce7-4ddc-adc7-e9bf457f2837',"UPDATE kufar_versions SET raw_json=json_remove(raw_json,'$.ad_parameters') WHERE id IN (SELECT id FROM kufar_versions WHERE observed_at<date('now','-14 days') AND json_type(raw_json,'$.ad_parameters')='array' ORDER BY id LIMIT 500)"),
 ('d8dd0219-8070-4f48-980d-312eba26209e',"UPDATE kufar_ads_live SET raw_json=json_remove(raw_json,'$.ad_parameters') WHERE ad_id IN (SELECT ad_id FROM kufar_ads_live WHERE present=0 AND last_seen<date('now','-30 days') AND json_type(raw_json,'$.ad_parameters')='array' ORDER BY ad_id LIMIT 500)"),
 ('43422bcb-fce7-4ddc-adc7-e9bf457f2837',"DELETE FROM source_diagnostics WHERE id IN (SELECT id FROM source_diagnostics WHERE observed_at<date('now','-30 days') ORDER BY id LIMIT 1000)"),
]

def run():
    total_read=total_written=0
    for database,sql in TASKS:
        url=f'https://api.cloudflare.com/client/v4/accounts/{os.environ["CF_ACCOUNT_ID"]}/d1/database/{database}/query'
        req=urllib.request.Request(url,data=json.dumps({'sql':sql}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['CF_D1_API_TOKEN']})
        with urllib.request.urlopen(req,timeout=60) as response:result=json.load(response)
        if not result.get('success'):raise RuntimeError(result.get('errors'))
        meta=result['result'][0]['meta'];total_read+=meta.get('rows_read',0);total_written+=meta.get('rows_written',0)
        print(json.dumps({'database':database,'changes':meta.get('changes'), 'rows_read':meta.get('rows_read'),'rows_written':meta.get('rows_written'),'size_after':meta.get('size_after')}),flush=True)
        if total_written>=5000:raise RuntimeError('Storage maintenance write budget reached; paused')
    print(json.dumps({'maintenanceUsage':{'rowsRead':total_read,'rowsWritten':total_written}}))

if __name__=='__main__':run()
