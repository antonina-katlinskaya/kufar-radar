from radar.collectors.kufar import KufarCollector, parse_ad_dict, contact_person

def test_real_kufar_shape():
    d={
      'adId':'1085820441','adViewLink':'https://re.kufar.by/vi/x/1085820441',
      'address':'Игоря Лученка ул, 22, Минск','title':'Mediterranean',
      'adParams':{
        'rooms':{'v':'1'},'size':{'v':30.4},'floor':{'v':[2]},
        'reDistrict':{'vl':'Минск-Мир'},
        'newBuildingsApartmentComplex':{'vl':'ЖК Minsk World'}
      },
      'accountParams':{'contactPerson':{'v':'Алёна'}},
      'calculator':[
        {'currency':'EUR','price':'4366900'},
        {'currency':'BYN','price':'15168864'}
      ]
    }
    x=parse_ad_dict(d,'11093294')
    assert x.ad_id=='1085820441'
    assert x.price_eur==43669
    assert x.area==30.4
    assert x.rooms==1
    assert x.floor==2
    assert x.address.startswith('Игоря Лученка')
    assert contact_person(x)=='Алёна'

def test_collector_can_target_an_individual_profile_without_name_filter():
    c=KufarCollector('11080367',None)
    assert c.profile_id=='11080367'
    assert c.contact_name is None
