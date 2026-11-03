"""Restore navigation only to the established owner and invited sister."""
import json
from radar.d1 import D1
from radar.telegram import Telegram
from radar.navigation import ensure_navigation

def main():
    db=D1();tg=Telegram()
    assert tg.call('getMe',{})['result']['username']=='kufar_radarr_bot','Unexpected bot identity'
    owner=str(db.get_state('telegram_chat_id') or '')
    subscribers=list(dict.fromkeys(str(v) for v in json.loads(db.get_state('telegram_chat_ids_v1','[]'))))
    assert owner and owner in subscribers and len(subscribers)==2,'Established owner/sister audience changed; refusing to guess recipients'
    # Verify every destination before changing either chat.
    for chat in subscribers:
        info=tg.call('getChat',{'chat_id':chat})['result']
        assert str(info['id'])==chat and info['type']=='private','Unexpected chat'
    results=[]
    for chat in subscribers:
        ok=ensure_navigation(db,tg,chat,force=True)
        results.append({'recipient':'owner' if chat==owner else 'invited_sister','restored':ok})
    print(json.dumps({'navigationRestore':results}),flush=True)
    if not all(r['restored'] for r in results):raise RuntimeError('Navigation was not confirmed for every recipient')

if __name__=='__main__':main()
