#  Тема викторины — «Какое у вас тотемное животное?»
#  Редис ключи: 'user_question' - какой вопрос следующий, 'user_data' - итог опроса, 'user_id' - id пользователя
#  Редис ключи: cid - простое сообщение, cid+'media' - медиа сообщение
#  При первом запуске (и раз в неделю) подтягиваются картинки через selenium,
#  в конфиге выставлено 10 секунд ожидания для их прогрузки
import datetime

import telebot.util
from telebot import types, asyncio_helper, asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_storage import StateRedisStorage
import asyncio
# import vk_api
import redis
import logging
import os.path
from pathlib import Path
from random import randrange

from config import (TOKEN, REDIS_HOST, REDIS_PORT, MANAGER_ID, States,
                    VKTOKEN, VK_APP_ID, VK_SERVICE_KEY, VK_SECRET_KEY, VK_REQUEST)  # VK эксперименты
from quiz import Quiz, Animals


bot = AsyncTeleBot(TOKEN, state_storage=StateRedisStorage())
rs = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
log = telebot.logger
log.setLevel(logging.INFO)

try:
    import zoo_parser
except redis.exceptions.ConnectionError as e:
    log.error('-----------Нет подключения к редис!------------', e)
    # print('Нет подключения к редис!', e)

STATIC_DIR = os.path.join(Path(__file__).resolve().parent, 'static')  # Папка с картинками опроса
REVIEW_DIR = os.path.join(Path(__file__).resolve().parent, 'review')  # Папка с файлами отзывов
MANAGER_ID = int(MANAGER_ID)  # Присвоить интовый айди сотрудника для связи

quiz = Quiz()  # Копия опроса викторины, чтобы можно было делать обновления, но не реализовано


def get_user_question_number(cid) -> int:
    """Получить текущий номер вопроса викторины пользователя"""
    cid = str(cid)
    users_question = rs.hget('user_question', cid)
    if users_question is None:
        rs.hset('user_question', mapping={cid: '0'})
        return 0
    return int(users_question)


def set_user_question_number(cid, value):
    """Установить текущий номер вопроса викторины пользователя"""
    cid, value = str(cid), str(value)
    rs.hset('user_question', mapping={cid: value})


@bot.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Команда для начала основного взаимодействия с ботом"""
    cid = str(message.chat.id)

    rs.hset('user_id', cid, str(message.from_user.id))  # возможно забагается если смениться id чата

    # Блок очистки лишних данных
    await bot.delete_state(rs.hget('user_id', cid), message.chat.id)
    if rs.llen(cid):
        try:
            await bot.delete_message(cid, int(rs.lindex(cid, 0)))
        except asyncio_helper.ApiTelegramException as e:
            log.info('Нечего удалять', e)
            rs.ltrim(cid, 0, rs.llen(cid))  # Если нечего удалять то очистить список очистки
    await clean(cid)
    if rs.llen(cid + 'media') > 0:
        await clean_media(cid)

    # Проверка знаком ли пользователь
    if rs.hget('user_data', cid) is None:
        rs.hset('user_data', cid, '0000')  # Если нет - создаем его данные

    # Настройка сообщения
    markup = telebot.util.quick_markup({
        'Викторина!': {'callback_data': 'quiz'},
        'Картинки!': {'callback_data': 'animal'},
    })
    caption = ('Привет, %s! Предлагаю поучавствовать '
               'в небольшой викторине <strong>«Какое у вас тотемное животное?»</strong> '
               'Это носит развлекательный характер и делается для того чтобы '
               'немного прикоснуться к миру братьев меньших.'
               % message.chat.first_name)
    pic = os.path.join(STATIC_DIR, 'MZoo-logo-hor-rus-preview-RGB.jpg')
    with open(pic, 'rb') as logo:
        m = await bot.send_photo(
            message.chat.id,
            photo=logo,
            caption=caption,
            parse_mode='HTML',
            reply_markup=markup,
            disable_notification=True
        )
    rs.lpush(f'{cid}media', m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


@bot.message_handler(commands=['reset'])
async def reset(message: types.Message, not_silent=True):
    """Сброс данных пользователя к началу"""
    cid = str(message.chat.id)

    # Блок очистки лишних данных
    try:
        await bot.delete_message(
            chat_id=cid,
            message_id=int(rs.lindex(cid+'media', 0))
        )
    except asyncio_helper.ApiTelegramException as e:
        log.info(e)
    await clean(cid)
    await clean_media(cid)

    if not_silent:  # Готовим сообщение если надо
        text = 'Хорошо! Давайте начнем сначала. Подготавливаюсь!'

        m = await bot.send_message(
            chat_id=cid,
            text=text,
            disable_notification=True
        )
        await bot.send_chat_action(cid, 'typing', timeout=2)
        rs.lpush(cid, m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)

    # Сброс данных
    set_user_question_number(cid, 0)
    rs.hset('user_data', cid, '0000')
    await bot.delete_state(rs.hget('user_id', cid), message.chat.id)

    await asyncio.sleep(3)
    await next_question(message)


@bot.message_handler(commands=['score'])  # FIXME DEBUG КОМАНДА
def dbg_score(message: types.Message):
    bot.send_message(message.chat.id, message.from_user.username, disable_notification=True)
    if message.from_user.username == 'Darkozavr':
        var = rs.hget('user_data', str(message.chat.id))
        bot.send_message(message.chat.id, var, disable_notification=True)


async def clean(cid):
    """Очищает инлайн кнопки из сообщений простого списка"""
    # Возможно переделать
    length = rs.llen(cid)
    if length:
        for _ in range(length):
            m = rs.lpop(cid)
            try:
                await bot.edit_message_reply_markup(chat_id=cid,
                                                    message_id=int(m),
                                                    reply_markup=None)
            except asyncio_helper.ApiTelegramException as e:
                log.debug('Ошибка в очистке инлайн кнопок', e)


async def clean_media(cid):
    """Очищает инлайн кнопки из сообщений списка медиа файлов"""
    # Возможно переделать
    length = rs.llen(cid + 'media')
    if length:
        for _ in range(length):
            m = rs.lpop(cid + 'media')
            try:
                await bot.edit_message_reply_markup(chat_id=cid,
                                                    message_id=int(m),
                                                    reply_markup=None)
            except asyncio_helper.ApiTelegramException as e:
                log.debug('Ошибка в очистке инлайн кнопок', e)


async def next_question(message: types.Message):
    """Главная функция викторины, которая проводит по вопросам"""
    cid = str(message.chat.id)
    q_num = get_user_question_number(cid)

    await clean_media(cid)  # Чистим излишки

    if q_num == -1:  # Если тест пройден до конца
        await get_quiz_result(message)
        return

    if q_num >= quiz.get_length():  # Если закончились вопросы
        await bot.send_chat_action(cid, 'typing', timeout=1)
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=int(rs.lindex(cid, 0)),
            text='Это был последний вопрос, а сейчас посмотрим'
            ' что у нас получилось :)',
        )
        set_user_question_number(cid, '-1')  # Метка что опрос пройден до конца
        await asyncio.sleep(2)
        await get_quiz_result(message)  # Получаем результат
        return

    # Подготовка сообщения с вопросом
    question = quiz.get_question(q_num)
    char_list = ['A', 'B', 'C', 'D']  # Литеры вариантов ответа
    btn_num = 0
    char_num = 0
    text = f'{question["text"]}\n\n'
    for answer in question['answers']:  # Добавления ответов после текста с вопросом
        text += f'{char_list[char_num]}. {answer}\n'
        char_num += 1

    btns = {}
    for i in char_list:  # Делаем инлайн кнопки
        if btn_num < len(question['answers']):
            btn_num += 1
            btns[i] = {'callback_data': str(btn_num)}

    markup = telebot.util.quick_markup(btns, row_width=2)

    await bot.send_chat_action(cid, 'typing', timeout=1)

    length = rs.llen(cid)  # Есть ли сообщение для изменения.
    # Должен быть 0 при запуске викторины, но бывает ломается.
    if length:
        try:
            await bot.edit_message_text(
                chat_id=cid,
                message_id=int(rs.lindex(cid, 0)),
                text=text,
                reply_markup=markup
            )
        except asyncio_helper.ApiTelegramException as e:
            log.debug('Ошибка с изменением сообщения в next_question', e)
            await get_quiz_result(message)
            # await reset(message, not_silent=False)
    else:  # Если первый вопрос, то создаем сообщение
        m = await bot.send_message(
            chat_id=cid,
            text=text,
            reply_markup=markup,
            disable_notification=True
        )
        rs.lpush(cid, m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


async def answer_handle(message: types.Message, answer_num: int):
    """Метод обработчик полученных ответов"""
    cid = message.chat.id
    q_num = get_user_question_number(cid)

    if q_num >= quiz.get_length():
        log.debug('Ошибка превышения индекса номера вопроса')
        return

    q = quiz.get_question(q_num)
    num = 1

    for par, val in q['answers'].values():
        if num != answer_num:
            num += 1
            continue

        result = int(rs.hget('user_data', str(cid)))
        if par == 'group':
            if result < 1000 and int(val) == 1:
                result += 1000
        elif par == 'feature':
            if (0 <= result - 1000 < 100) or (0 <= result < 100):
                if int(val) == 1:
                    result += 100
        elif par == 'var':
            result += int(val)

        rs.hset('user_data', str(cid), str(result))
        set_user_question_number(cid, q_num + 1)
        break

    await next_question(message)


async def get_quiz_result(message: types.Message):
    """Метод с демонстрацией результата прохождения теста"""
    cid = str(message.chat.id)
    result = int(rs.hget('user_data', cid))

    data = Animals.get_animal_data(result)  # Получаем данные о тотемном животном на основании результата теста

    # Готовим сообщение
    markup = telebot.util.quick_markup({
        'Узнать об опеке!': {'callback_data': 'opeka_info'},
        'Оставить отзыв': {'callback_data': 'review'},
        'Пройти заново!': {'callback_data': 'reset'},
    })

    caption = (f'Поздравляем! По итогам теста мы выявили, что ваше тотемное животное «{data["name"]}»\n\n'
               f'{data["description"]}')

    if rs.llen(cid):  # Удаление крайнего сообщения
        await bot.delete_message(
            chat_id=cid,
            message_id=int(rs.lindex(cid, 0))
        )

    link = os.path.join(STATIC_DIR, data['image'])
    with open(link, 'rb') as pic:
        m = await bot.send_photo(
            chat_id=cid,
            photo=pic,
            caption=caption,
            parse_mode='HTML',
            reply_markup=markup,
            disable_notification=True
        )
    rs.lpush(f'{cid}media', m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


async def show_animal(message: types.Message):
    """Метод демонстрации изображений случайных животных  из списка нуждающихся в опеке"""
    cid = str(message.chat.id)
    animal_name, animal_pic_url = zoo_parser.random_animal()  # Получаем рандомное животное

    # Готовим сообщение
    if not animal_pic_url:
        animal_pic_url = os.path.join(STATIC_DIR, 'Нет_фото.png')

    kind_words = ('красивый', 'интересный', 'необычный', 'забавный', 'дикий')  # Для разнообразия)
    rand = randrange(len(kind_words))

    caption = (f'Вот этот {kind_words[rand]} обитатель "{animal_name}" ждет своего опекуна. '
               f'Более подробно о программе опеки можно узнать после прохождения викторины. ' + u'😉')

    markup = telebot.util.quick_markup({
        'К викторине!': {'callback_data': 'quiz'},
        'Еще!': {'callback_data': 'animal'},
    })

    media = types.InputMediaPhoto(
        media=animal_pic_url,
        caption=caption,
        parse_mode='HTML'
    )
    if media:  # Порой zoo_parser.random_animal() возвращает пустой объект FIXME
        await bot.edit_message_media(
            media=media,
            chat_id=cid,
            message_id=int(rs.lindex(cid + 'media', 0)),
            reply_markup=markup
        )


async def opeka_info(message: types.Message):
    """Метод с демонстрацией информации о программе опеки"""
    cid = str(message.chat.id)
    await clean_media(cid)  # Очистка лишних данных

    text = ('<strong>Московский Зоопарк</strong> представляет программу опеки, благодаря которой '
            'вы можете оказать помощь в содержании различных видов животных. '
            'Стать участником программы <i>«Клуб друзей зоопарка»</i> значит '
            'позаботиться о ком то из его обитателей, помочь зоопарку в развитии '
            'и внести личный вклад в их дело сохранения природы и биоразнообразия Земли. '
            'Подробнее можно посмотреть <a href="https://moscowzoo.ru/about/guardianship">тут</a>.\n'
            'Заявку но связь с сотрудником зоопарка можно оставить по кнопке "Связаться с нами".')

    markup = telebot.util.quick_markup({
        'Связаться с нами': {'callback_data': 'contact'},
        'В начало': {'callback_data': 'start'},

    })
    m = await bot.send_message(
        chat_id=cid,
        text=text,
        disable_notification=True,
        reply_markup=markup,
        parse_mode='HTML',
    )
    rs.lpush(cid, m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


async def contact_email(message: types.Message):  # TODO можно сделать переделку емайл после проверки по запросу
    # TODO или проверку корректности ввода
    """Метод запроса Email для обратной связи с сотрудником"""
    cid = str(message.chat.id)
    markup = telebot.util.quick_markup({'В начало': {'callback_data': 'start'}})

    await clean_media(cid)  # Очистка лишних данных

    if rs.get(cid+'var') == '1':  # Если есть метка об уже оставленном сообщении
        text = 'Вы уже оставили заявку на связь с вами. Следующую заявку можно сделать через сутки.'
        await bot.edit_message_text(
            chat_id=cid,
            message_id=int(rs.lindex(cid, 0)),
            text=text,
            reply_markup=markup
        )
    else:  # Если нет метки, делаем запрос на емайл
        await bot.set_state(rs.hget('user_id', cid), States.contact_response, message.chat.id)
        await bot.edit_message_text(
            chat_id=cid,
            message_id=int(rs.lindex(cid, 0)),
            text='Напишите ваш емайл для обратной связи. Будьте аккуратны! '
                 'В случае ошибки, повторный запрос можно будет сделать только через сутки.',
        )


@bot.message_handler(state=States.contact_response)
async def contact(message: types.Message):
    """Метод обработки полученного Email от пользователя и отправки заявки"""
    cid = str(message.chat.id)

    # Готовим сообщение для менеджера по связям
    user_name = f'@{message.chat.username}'  # Как обращаться
    if not user_name:
        user_name = message.chat.first_name

    markup = telebot.util.quick_markup({'В начало': {'callback_data': 'start'}})
    result = int(rs.hget('user_data', cid))
    animal = Animals.get_animal_data(result)

    text = (f'Пользователь {user_name} оставил заявку на связь. Адрес электронной почты - {message.text}. '
            f'Результат теста - {result} {animal["name"]}.')

    await bot.send_message(  # Сообщение для менеджера
        chat_id=MANAGER_ID,
        text=text,
        disable_notification=True
    )

    await bot.edit_message_text(  # Сообщение для польователя
        chat_id=cid,
        message_id=int(rs.lindex(cid, 0)),
        text='Ваша заявка на связь отправлена сотруднику.',
        reply_markup=markup
    )
    rs.set(cid+'var', '1', ex=86400)  # Установка значения, чтобы не было повторных отправок FIXME (не проверено)

    await bot.delete_state(rs.hget('user_id', cid), message.chat.id)


async def ask_review(message: types.Message):
    """Метод запроса на получение отзыва от пользователя"""
    cid = str(message.chat.id)

    await clean_media(cid)  # Очистка лишних данных

    await bot.set_state(rs.hget('user_id', cid), States.review_response, message.chat.id)
    m = await bot.send_message(
        chat_id=cid,
        text='Напишите свой отзыв о нас. Нам интересно узнать ваше мнение! ' + u'🐹',
        disable_notification=True,
    )
    rs.lpush(cid, m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


@bot.message_handler(state=States.review_response)
async def review(message: types.Message):
    """Метод обработки полученного отзыва пользователя"""
    cid = str(message.chat.id)
    markup = telebot.util.quick_markup({'В начало': {'callback_data': 'start'}})

    date = str(datetime.datetime.now().date()) + '.txt'
    url = os.path.join(REVIEW_DIR, date)  # Название и путь к файлу

    with open(url, 'at') as f:
        f.writelines(message.text + '\n\n')

    m = await bot.send_message(
        chat_id=cid,
        text='Спасибо ' + u'☺️',
        reply_markup=markup,
        disable_notification=True
    )
    await bot.delete_state(rs.hget('user_id', cid), message.chat.id)
    rs.lpush(cid, m.message_id)  # Добавляем в список на очистку от кнопок(возможно переделать)


# @bot.message_handler(commands=['repost'])  # FIXME дебаг команда, убрать после настройки
# async def vk_repost(message: types.Message):
#     url = VK_REQUEST

    # session = vk_api.VkApi(
    #     app_id=VK_APP_ID,
    #     client_secret=VK_SECRET_KEY,
    # )

    # vk = session.get_api()
    # vk_id = vk.account.getProfileInfo()['id']
    # print(vk_id)

    # text = f'{message.from_user.username} Hello from backend!'
    # attachments = 'https://t.me/sf_learn_bot'

    # https: // t.me / sf_learn_bot
    # id46353511
    # vk.wall.post(
    #     owner_id=vk_id,
    #     message=text,
    #     attachments=attachments
    # )


@bot.callback_query_handler(func=lambda callback: True)
async def callback_handler(callback: types.CallbackQuery):
    """Обработка callback полученных от инлайн кнопок"""
    msg = callback.message
    data = callback.data
    if data == 'start':
        await cmd_start(msg)
    elif data == 'quiz':
        await next_question(msg)
    elif data == 'reset':
        await reset(msg)
    elif data == 'animal':
        await show_animal(msg)
    elif data == 'review':
        await ask_review(msg)
    elif data == 'contact':
        await contact_email(msg)
    elif data == 'opeka_info':
        await opeka_info(msg)
    else:  # должны быть цифровые call
        try:
            data = int(data)
        except TypeError as e:
            log.debug(e)
        await answer_handle(msg, data)


bot.add_custom_filter(asyncio_filters.StateFilter(bot))


if __name__ == '__main__':
    asyncio.run(bot.infinity_polling())


# TODO можно переделать привязку chat.id на user.id
