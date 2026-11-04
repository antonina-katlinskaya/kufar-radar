import unittest
from realt_test.notify import format_card

class VisualCardTests(unittest.TestCase):
    def test_kufar_style_multiline_card(self):
        item = {'person':'Дмитрий Спиридонов','rooms':'1','area':'30.91',
                'floor':'3','address':'Минск Игоря Лученка 22н',
                'price':'51465','currency':'978',
                'created_at':'2026-10-26T10:15:23+03:00',
                'bir_room_area_candidates': []}
        text = format_card(item,'2026-10-26T10:22:00+03:00')
        self.assertIn('\n👤 <b>Дмитрий Спиридонов</b>\n',text)
        self.assertIn('\n📍 Минск Игоря Лученка 22н\n',text)
        self.assertIn('\n🚪 1-комн. · 30,91 м² · 3 этаж\n',text)
        self.assertIn('Realt: 51 465 €',text)
        self.assertIn('🕒 публикация Realt 26.10 10:15 · BIR 26.10 10:22',text)
        self.assertNotIn('\\\\n',text)

    def test_byn_display_and_house_and_radar(self):
        item={'person':'Анна Зенкевич','rooms':'3','area':'52.5','floor':'5',
              'address':'Минск Брилевская ул.','house_number':'35','quarter':'Минск Мир',
              'price':'436000','currency':'933','created_at':'2026-10-23T15:48:40+03:00',
              'radar_checked_at':'2026-10-26T10:13:03+00:00',
              'bir_room_area_candidates':[{'regular_price_eur':'80000','special_price_eur':'75000'}]}
        text=format_card(item,'2026-10-26T10:00:00Z')
        self.assertIn('436 000 BYN',text)
        self.assertNotIn('436 000 933',text)
        self.assertIn('Брилевская ул. 35',text)
        self.assertIn('BIR: 80 000 €',text)
        self.assertIn('Спеццена BIR: 75 000 €',text)
        self.assertIn('проверка радара 26.10 13:13',text)

    def test_separate_publication_and_observed_backdated_edit(self):
        item = {'person':'Ольга Михальченко','status':'BACKDATED',
                'rooms':'3','area':'54.6','price':'474900','currency':'933',
                'created_at':'2026-07-16T16:50:00+03:00',
                'last_seen_at':'2026-11-04T12:04:17Z',
                'radar_checked_at':'2026-11-04T12:25:10Z',
                'material_edits':[{'observed_at':'2026-11-04T12:08:00Z',
                    'changes':[{'field':'цена','before':'485700','after':'474900'}]}]}
        message = format_card(item,'2026-11-04T12:15:23Z')
        self.assertIn('публикация Realt 16.07 16:50', message)
        self.assertIn('правка замечена 04.11 15:08', message)
        self.assertIn('проверка радара 04.11 15:25', message)
        self.assertIn('BIR 04.11 15:15', message)
        self.assertNotIn('снимок Realt', message)

    def test_realt_latest_snapshot_shown_for_new_listing(self):
        item = {'person':'Ирина Барашенко','rooms':'1','area':'29.71',
                'price':'44654','currency':'978',
                'created_at':'2026-11-04T09:32:00+03:00',
                'last_seen_at':'2026-11-04T12:04:17Z'}
        message = format_card(item,'2026-11-04T12:15:23Z')
        self.assertIn('публикация Realt 04.11 09:32', message)
        self.assertIn('снимок Realt 04.11 15:04', message)
