"""Isolated owner-only townhouse notifications; do not touch employee violation delivery."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from notifications.radar_technical import send

STATE=Path(__file__).with_name('state.json')
RUN=os.environ.get('GITHUB_RUN_ID','')

def write(state):
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def daytime():
    return 8<=datetime.now(ZoneInfo('Europe/Minsk')).hour<22

def claim():
    state=json.loads(STATE.read_text(encoding='utf8'))
    if not daytime():
        print('TOWNHOUSE_ALERT_QUIET_HOURS: pending retained')
        return
    pending=[a for a in state['outbox'] if a['status']=='pending']
    if not pending:
        print('TOWNHOUSE_CLAIMED 0')
        return
    for a in pending:
        a.update(status='claimed',claimRun=RUN,claimedAt=datetime.now(ZoneInfo('Europe/Minsk')).isoformat())
    write(state)
    print('TOWNHOUSE_CLAIMED '+str(sum(x['status']=='claimed' and x.get('claimRun')==RUN for x in state['outbox'])))

def deliver():
    state=json.loads(STATE.read_text(encoding='utf8'))
    if not daytime():
        print('TOWNHOUSE_NO_DELIVERY_AT_NIGHT');return
    targets=[a for a in state['outbox'] if a['status']=='claimed' and a.get('claimRun')==RUN]
    for a in targets:
        verb='Новый таунхаус в выдаче Bir' if a['kind']=='new' else 'Таунхаус снова появился в выдаче Bir'
        message=('🏡 '+verb+'\n'+'Минск-Мир · '+a['unit']+'\n'
                 +'Площадь: '+str(a['area'])+' м²\n'
                 +('Специальная цена: {:,.0f} €\n'.format(a['priceFastEur']).replace(',',' ') if a.get('priceFastEur') else '')
                 +a['url']+'\n'
                 +'Источник: Bir.by; появление в выдаче не означает подтверждённую сделку.')
        receipt=send(message)  # verifies bot and private owner before sending
        a['status']='delivered';a['receipt']=receipt;a['deliveredAt']=datetime.now(ZoneInfo('Europe/Minsk')).isoformat()
        write(state)  # workflow persists receipt immediately after this step
        print('TOWNHOUSE_ALERT_DELIVERED '+a['id'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['claim','deliver']);args=parser.parse_args()
    if not RUN:raise SystemExit('GITHUB_RUN_ID is required')
    globals()[args.action]()
