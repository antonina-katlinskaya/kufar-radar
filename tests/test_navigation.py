import json,unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from radar.navigation import ensure_navigation,NAV_STATE_PREFIX,MAIN_KEYBOARD
from radar.telegram import Telegram

class DB:
    def __init__(self):self.state={}
    def get_state(self,k,default=None):return self.state.get(k,default)
    def set_state(self,k,v):self.state[k]=v
class TG:
    def __init__(self,fail=None):self.sent=[];self.configured=[];self.fail=fail
    def configure_navigation(self,c):self.configured.append(c)
    def send(self,c,text,**kwargs):
        if c==self.fail:raise RuntimeError('temporary failure')
        self.sent.append((c,kwargs));return {'ok':True,'result':{'message_id':12}}

class NavigationTests(unittest.TestCase):
    def setUp(self):self.now=datetime(2026,11,3,13,tzinfo=ZoneInfo('Europe/Minsk'))
    def test_failure_for_sister_is_retried_despite_owner_success(self):
        db=DB();tg=TG(fail='sister')
        self.assertTrue(ensure_navigation(db,tg,'owner',now=self.now))
        self.assertFalse(ensure_navigation(db,tg,'sister',now=self.now))
        self.assertNotIn('keyboard_date',json.loads(db.state[NAV_STATE_PREFIX+'sister']))
        tg.fail=None
        self.assertTrue(ensure_navigation(db,tg,'sister',now=self.now))
        self.assertEqual([c for c,_ in tg.sent],['owner','sister'])
    def test_no_message_spam_then_daily_keyboard_repair(self):
        db=DB();tg=TG()
        for _ in range(3):ensure_navigation(db,tg,'owner',now=self.now)
        self.assertEqual(len(tg.sent),1);self.assertEqual(len(tg.configured),1)
        ensure_navigation(db,tg,'owner',now=self.now.replace(day=4))
        self.assertEqual(len(tg.sent),2)
    def test_api_false_is_not_saved_as_keyboard_success(self):
        db=DB();tg=TG();tg.send=lambda *a,**kw:{'ok':False}
        self.assertFalse(ensure_navigation(db,tg,'owner',now=self.now))
        self.assertNotIn('keyboard_date',json.loads(db.state[NAV_STATE_PREFIX+'owner']))
    def test_keyboard_has_persistence_without_single_use(self):
        tg=Telegram.__new__(Telegram);calls=[]
        tg.call=lambda method,payload:calls.append((method,payload)) or {'ok':True}
        tg.send('owner','test',reply_keyboard=MAIN_KEYBOARD)
        markup=calls[0][1]['reply_markup']
        self.assertTrue(markup['is_persistent']);self.assertFalse(markup['one_time_keyboard'])
    def test_menu_is_verified_after_configuration(self):
        tg=Telegram.__new__(Telegram);calls=[]
        def call(method,payload):
            calls.append(method)
            return {'result':{'type':'commands'}} if method=='getChatMenuButton' else {'result':[{'command':'violations'}]}
        tg.call=call;tg.configure_navigation('owner')
        self.assertEqual(calls,['setMyCommands','setChatMenuButton','getChatMenuButton','getMyCommands'])
if __name__=='__main__':unittest.main()
