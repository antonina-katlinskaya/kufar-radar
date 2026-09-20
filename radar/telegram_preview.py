from radar.d1 import D1
from radar.telegram import Telegram

def main():
    db=D1(); tg=Telegram()
    chat=db.get_state('telegram_chat_id')
    if not chat:
        raise RuntimeError('Telegram chat is not configured')

    card1="""🧪 МАКЕТ — не реальное нарушение

🚨 Расхождения между Kufar и Bir
Дом: Эверест
Адрес: ул. Николы Теслы, 33
Помещение № 834
Квартира: 1-комн., 37,65 м², 12 этаж

Цена
Kufar: 57 900 €
Bir: 58 358 €
Спеццена Bir: 52 522 €

Площадь
Kufar: 37,66 м²
Bir: 37,65 м²

Kufar: https://kufar.by/
Bir: https://bir.by/search-by-parameters/"""

    card2="""🧪 МАКЕТ — не реальное нарушение

🚨 Объявление на Kufar не соответствует наличию на Bir
Дом: Медитерранеан
Адрес: ул. Игоря Лученка, 22
Помещение № 2.39
Квартира: 1-комн., 30,41 м², 2 этаж

Последний раз в выдаче Bir: 20.09.2026, 09:47

Kufar: https://kufar.by/
Bir: https://bir.by/search-by-parameters/"""

    tg.send(chat,card1)
    tg.send(chat,card2)

if __name__=='__main__':
    main()
