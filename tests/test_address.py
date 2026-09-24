from radar.matcher import address_equal

def test_russian_address_variants():
    assert address_equal('Жореса Алфёрова ул, 4, Минск','улица Жореса Алфёрова, дом 4')
    assert address_equal('Михаила Савицкого ул, 9, Минск','улица Михаила Савицкого, дом 9')
    assert not address_equal('Жореса Алфёрова ул, 4, Минск','улица Михаила Савицкого, дом 9')

def test_missing_house_number_is_not_an_address_match():
    assert not address_equal('Игоря Лученка ул, Минск','Игоря Лученка ул, 22, Минск')
    assert not address_equal('квартал Старый Аэропорт','площадь Старый Аэропорт, 2, Минск')

def test_house_suffix_is_compared_together_with_number():
    assert address_equal('Кижеватова 1А','Кижеватова ул, дом 1а, Минск')
    assert not address_equal('Кижеватова 1','Кижеватова ул, дом 1А, Минск')
