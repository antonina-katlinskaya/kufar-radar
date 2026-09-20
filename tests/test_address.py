from radar.matcher import address_equal

def test_russian_address_variants():
    assert address_equal('Жореса Алфёрова ул, 4, Минск','улица Жореса Алфёрова, дом 4')
    assert address_equal('Михаила Савицкого ул, 9, Минск','улица Михаила Савицкого, дом 9')
    assert not address_equal('Жореса Алфёрова ул, 4, Минск','улица Михаила Савицкого, дом 9')
