import httpx, os
from .config import settings

class Telegram:
    def __init__(self):
        if not settings.telegram_token: raise RuntimeError('TELEGRAM_BOT_TOKEN missing')
        self.base=f'https://api.telegram.org/bot{settings.telegram_token}'
    def get_updates(self,offset=None):
        p={'timeout':0,'allowed_updates':['message','callback_query']}
        if offset is not None: p['offset']=offset
        r=httpx.get(self.base+'/getUpdates',params=p,timeout=30)
        r.raise_for_status()
        data=r.json()
        if not data.get('ok'):
            raise RuntimeError(f"Telegram getUpdates failed: {data.get('description')}")
        return data.get('result',[])
    def send(self,chat_id,text,keyboard=None,parse_mode=None,reply_keyboard=None):
        payload={'chat_id':chat_id,'text':text,'disable_web_page_preview':True}
        if keyboard: payload['reply_markup']={'inline_keyboard':keyboard}
        if reply_keyboard:
            payload['reply_markup']={
              'keyboard':reply_keyboard,
              'resize_keyboard':True,
              'is_persistent':True,
            }
        if parse_mode: payload['parse_mode']=parse_mode
        r=httpx.post(self.base+'/sendMessage',json=payload,timeout=30); r.raise_for_status(); return r.json()
    def photo(self,chat_id,path,caption=''):
        with open(path,'rb') as f:
            r=httpx.post(self.base+'/sendPhoto',data={'chat_id':chat_id,'caption':caption[:1024]},files={'photo':f},timeout=60)
        r.raise_for_status(); return r.json()
    def answer_callback(self,cqid,text='Принято'):
        try: httpx.post(self.base+'/answerCallbackQuery',json={'callback_query_id':cqid,'text':text},timeout=15)
        except: pass
