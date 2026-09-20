from radar.collectors.kufar import parse_ad_dict, contact_person

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
