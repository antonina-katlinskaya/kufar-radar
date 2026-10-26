"""Export the existing successful Bir refresh; never scan Bir or touch Kufar state."""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from realt_test.github_store import GitHubFile, REPO
from realt_test.export_bir import main as export_snapshot

STEP = 'Refresh BIR snapshot before comparison'

def stamp(value):
    out=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if out.tzinfo is None:raise RuntimeError('Source timestamp has no timezone')
    return out

def success_record(log, start, end):
    records=[]
    for line in log.splitlines():
        try:
            time,body=line.split(' ',1)
            if not stamp(start)<=stamp(time)<stamp(end)+timedelta(seconds=1):continue
            value=json.loads(body.strip())
        except (ValueError,TypeError):continue
        if isinstance(value,dict) and value.get('ok') is True and ((value.get('scanId') and 'sourceCount' in value) or (value.get('checked_at') and value.get('reason')=='fresh_snapshot')):
            records.append(value)
    if not records:raise RuntimeError('No successful Bir record in verified refresh step')
    return records[-1]

def eligible(run):
    return (run.get('name')=='Radar' and run.get('head_branch')=='main'
            and run.get('head_repository',{}).get('full_name')==REPO
            and run.get('status')=='completed')

def get(client,path):
    response=client.get('https://api.github.com/repos/'+REPO+path)
    if not response.is_success:raise RuntimeError(f'GitHub source evidence unavailable: HTTP {response.status_code}')
    return response.json()

def d1_lookup(scan_id):
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',str(scan_id)):
        raise RuntimeError('Invalid Bir scan identifier')
    endpoint=('https://api.cloudflare.com/client/v4/accounts/'+os.environ['CF_ACCOUNT_ID']+
              '/d1/database/'+os.environ['BIR_D1_DATABASE_ID']+'/query')
    with httpx.Client(timeout=60) as client:
        response=client.post(endpoint,headers={'Authorization':'Bearer '+os.environ['CF_D1_API_TOKEN']},
            json={'sql':'SELECT checked_at,status FROM bir_scans WHERE scan_id=? LIMIT 1','params':[scan_id]})
        if not response.is_success:raise RuntimeError(f'Bir metadata lookup failed: HTTP {response.status_code}')
        body=response.json()
    if not body.get('success') or not body.get('result'):raise RuntimeError('Bir metadata lookup failed')
    rows=body['result'][0].get('results',[])
    if len(rows)!=1 or rows[0].get('status')!='ok':raise RuntimeError('Bir scan is not successful')
    print(json.dumps({'bir_metadata_rows_read':body['result'][0].get('meta',{}).get('rows_read')}))
    return rows[0]['checked_at']

def main():
    now=datetime.now(timezone.utc)
    cached=GitHubFile('realt-bir-snapshot','realt_state/bir.json').read()
    age=now-stamp(cached['checked_at'])
    if cached.get('complete') is True and timedelta(minutes=-5)<=age<=timedelta(minutes=10):
        print(json.dumps({'bir_export_skipped':'existing GitHub snapshot is fresh'}));return
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    with httpx.Client(timeout=60,follow_redirects=True,headers={
        'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'], 'Accept':'application/vnd.github+json'}) as client:
        trigger=event.get('workflow_run')
        if trigger:
            if not eligible(trigger):raise RuntimeError('Untrusted source workflow')
            runs=[trigger]
        else:
            runs=[r for r in get(client,'/actions/runs?per_page=50')['workflow_runs'] if eligible(r)]
        record=None
        for run in runs:
            if now-stamp(run['created_at'])>timedelta(minutes=40):continue
            jobs=get(client,f"/actions/runs/{run['id']}/jobs")['jobs']
            for job in jobs:
                steps=[s for s in job.get('steps',[]) if s['name']==STEP and s.get('conclusion')=='success']
                if not steps:continue
                step=steps[0]
                response=client.get('https://api.github.com/repos/'+REPO+f"/actions/jobs/{job['id']}/logs")
                if not response.is_success:raise RuntimeError('Successful Bir source log is unavailable')
                record=success_record(response.text,step['started_at'],step['completed_at'])
                break
            if record:break
        if not record:raise RuntimeError('No recent successful existing Bir refresh; no new scan requested')
    checked=record.get('checked_at') or d1_lookup(record['scanId'])
    if not timedelta(minutes=-5)<=now-stamp(checked)<=timedelta(minutes=35):
        raise RuntimeError('Existing Bir scan is stale; export aborted')
    Path(os.environ['BIR_EXPORT_META_PATH']).write_text(json.dumps({'ok':True,'checked_at':checked}))
    export_snapshot()

if __name__=='__main__':main()
