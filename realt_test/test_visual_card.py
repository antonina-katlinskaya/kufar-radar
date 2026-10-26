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
