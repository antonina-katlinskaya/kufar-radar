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
        self.assertIn('🕒 Realt 26.10 10:15 · BIR 26.10 10:22',text)
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
        self.assertIn('радар 26.10 13:13',text)
