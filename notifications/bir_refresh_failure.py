"""Report an incomplete night sweep only to the radar owner's saved chat."""
import json,os,urllib.request
account=os.environ['CF_ACCOUNT_ID']
token=os.environ['CF_D1_API_TOKEN']
def request(url,body,headers=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
r=request(f'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/43422bcb-fce7-4ddc-adc7-e9bf457f2837/query',{'sql':"SELECT value FROM state WHERE key='telegram_chat_id'"},{'Authorization':'Bearer '+token})
assert r.get('success'),r.get('errors')
rows=r['result'][0]['results']
assert len(rows)==1,'Owner chat is not configured'
text='⚠️ BIR: полное ночное обновление карточек не завершено. Свежесть всех карточек не подтверждена. Проверьте журнал запуска: https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']
sent=request('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',{'chat_id':rows[0]['value'],'text':text,'disable_web_page_preview':True})
assert sent.get('ok'),'Telegram did not confirm delivery'
