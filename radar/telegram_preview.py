from radar.d1 import D1
from radar.telegram import Telegram

def main():
    db=D1()
    tg=Telegram()
    chat=db.get_state('telegram_chat_id')
    if not chat:
        raise RuntimeError('Telegram chat is not configured')

    cards=[
"""🧪 ТЕСТ

🚨 Цена на Kufar не совпадает с Bir
Дом: Манхэттен
Адрес: Жореса Алфёрова, 4
Квартира: 1-комн., 30,40 м², 10 этаж

Kufar: 71 900 €
Bir: 73 200 €
Спеццена Bir: 72 400 €

https://re.kufar.by/vi/1077861881""",

"""🧪 ТЕСТ

🚨 Расхождение по площади между Kufar и Bir
Дом: Манхэттен
Адрес: Жореса Алфёрова, 4
Квартира: 1-комн., 30,41 м², 10 этаж

Kufar: 30,41 м²
Bir: 30,40 м²

https://re.kufar.by/vi/1077861881""",

"""🧪 ТЕСТ

🚨 Объявление на Kufar не соответствует наличию на Bir
Дом: Манхэттен
Адрес: Жореса Алфёрова, 4
Квартира: 1-комн., 30,40 м², 10 этаж

На момент проверки соответствующий объект на Bir не найден.

https://re.kufar.by/vi/1077861881"""
    ]
    for card in cards:
        tg.send(chat,card)
    tg.send(chat,'🧪 ТЕСТ завершён. Эти сообщения не записаны как реальные расхождения.')

if __name__=='__main__':
    main()
