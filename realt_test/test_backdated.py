import unittest
from realt_test.backdated import material_change
from realt_test.dedup import select_new_reviews

class BackdatedTests(unittest.TestCase):
    def setUp(self):
        self.before={'uuid':'x','createdAt':'2026-10-23T09:00:00+03:00',
                     'price':'60000','priceCurrency':'978','rooms':1,
                     'areaTotal':'40.00','storey':5,'address':'old'}
    def test_material_price_change_older_than_24h(self):
        current={**self.before,'price':'58000','storey':6}
        result=material_change(self.before,current,'2026-10-25T10:00:00+03:00')
        self.assertEqual([e['field'] for e in result['changes']],['цена','этаж'])
    def test_only_floor_is_not_alerted(self):
        self.assertIsNone(material_change(self.before,{**self.before,'storey':9},
                                           '2026-10-25T10:00:00+03:00'))
    def test_new_listing_not_backdated(self):
        self.assertIsNone(material_change(self.before,{**self.before,'price':'59000'},
                                           '2026-10-23T12:00:00+03:00'))
    def test_distinct_backdated_alert_is_sent_once(self):
        item={'uuid':'x','person':'Ирина','status':'BACKDATED','material_edits':[{'changes':[{'field':'цена','before':'60000','after':'58000'}]}]}
        pending,state=select_new_reviews({'items':[item]}, {})
        self.assertEqual(len(pending),1)
        pending2,_=select_new_reviews({'items':[item]},state)
        self.assertEqual(pending2,[])
