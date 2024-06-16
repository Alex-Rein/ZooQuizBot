#  Тема викторины — «Какое у вас тотемное животное?»
#  Redis data names: 'user_question', 'user_data', (message.chat.id) ключи для работы с редисом
#  При первом запуске (и раз в неделю) подтягиваются картинки через selenium,
#  выставлено 10 секунд ожидания для их прогрузки

import telebot.util
from telebot import types, logger, asyncio_helper
from telebot.async_telebot import AsyncTeleBot
from telebot.custom_filters import IsAdminFilter
import requests
import asyncio
import vk_api
import redis
from redis.exceptions import RedisError

import logging
try:
    import zoo_parser
except redis.exceptions.ConnectionError as e:
    print('Нет подключения к редис', e)
import os.path
from pathlib import Path
from random import randrange


from config import TOKEN, REDIS_HOST, REDIS_PORT, VKTOKEN, VK_APP_ID, VK_SERVICE_KEY, VK_SECRET_KEY, VK_REQUEST
from quiz import Quiz, Animal


bot = AsyncTeleBot(TOKEN)
rs = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
log = logger
logger.setLevel(logging.DEBUG)
STATIC_DIR = os.path.join(Path(__file__).resolve().parent, 'static')

quiz = Quiz()


def get_user_question_number(uid):
    users_question = rs.hget('user_question', uid)
    if users_question is None:
        rs.hset('user_question', mapping={uid: '0'})
        return 0
    return int(users_question)


def set_user_question_number(uid, value):
    uid, value = str(uid), str(value)
    rs.hset('user_question', mapping={uid: value})


@bot.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    cid = str(message.chat.id)

    if rs.llen(cid + 'media') > 0:
        await clean(cid)
        await clean_media(cid)
    await asyncio.sleep(0.2)

    if rs.hget('user_data', cid) is None:
        rs.hset('user_data', cid, '0000')

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

    with open(pic, 'rb') as logo:  # будет ли работать как и должно?
        m = await bot.send_photo(
            message.chat.id,
            photo=logo,
            caption=caption,
            parse_mode='HTML',
            reply_markup=markup,
            disable_notification=True
        )
    rs.lpush('{0}media'.format(cid), m.message_id)


@bot.message_handler(commands=['reset'])
async def reset(message: types.Message, quiz_end=False, not_silent=True):
    cid = str(message.chat.id)

    await clean(cid)
    await clean_media(cid)

    if not_silent:
        if quiz_end:
            text = 'Ух ты! Вы уже прошли тест до конца в прошлый раз. Тогда перезапускаю!'
        else:
            text = 'Хорошо! Давайте начнем сначала. Подготавливаюсь!'

        m = await bot.send_message(
            chat_id=cid,
            text=text,
            disable_notification=True
        )
        await bot.send_chat_action(cid, 'typing', timeout=2)
        rs.lpush(cid, m.message_id)

    set_user_question_number(cid, 0)
    rs.hset('user_data', cid, '0000')

    await asyncio.sleep(3)
    await next_question(message)


@bot.message_handler(commands=['score'])  # FIXME DEBUG КОМАНДА
def dbg_score(message: types.Message):
    bot.send_message(message.chat.id, message.from_user.username, disable_notification=True)
    if message.from_user.username == 'Darkozavr':
        var = rs.hget('user_data', str(message.chat.id))
        bot.send_message(message.chat.id, var, disable_notification=True)


async def clean(cid):
    length = rs.llen(cid)
    if length:
        for _ in range(length):
            m = rs.lpop(cid)
            try:
                await bot.edit_message_reply_markup(chat_id=cid,
                                                    message_id=int(m),
                                                    reply_markup=None)
            except Exception as e:
                log.debug(e)


async def clean_media(cid):
    length = rs.llen(cid + 'media')
    if length:
        for _ in range(length):
            m = rs.lpop(cid + 'media')
            try:
                await bot.edit_message_reply_markup(chat_id=cid,
                                                    message_id=int(m),
                                                    reply_markup=None)
            except Exception as e:
                log.debug(e)


async def next_question(message: types.Message):
    cid = str(message.chat.id)
    q_num = get_user_question_number(cid)

    await clean_media(cid)

    if q_num >= quiz.get_length():  # Когда закончились вопросы
        await bot.send_chat_action(cid, 'typing', timeout=1)
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=rs.lindex(cid, -1),
            text='Это был последний вопрос, а сейчас посмотрим'
            ' что у нас получилось :)',
        )
        # await bot.send_message(
        #     chat_id=message.chat.id,
        #     text='Это был последний вопрос, а сейчас посмотрим'
        #     ' что у нас получилось :) Чтобы попробовать еще раз'
        #     ' восользуйтесь командой /reset',
        #     disable_notification=True,
        # )

        set_user_question_number(cid, '-1')  # Метка что опрос пройден до конца
        await asyncio.sleep(2)
        await get_quiz_result(message)
        return

    question = quiz.get_question(q_num)
    num = 1
    text = question['text']
    btns = {}  # TODO переделать ответы в текст вопроса, а кнопки по вариантам ответов

    for answer in question['answers']:
        btns[answer] = {'callback_data': str(num)}
        num += 1

    markup = telebot.util.quick_markup(btns, row_width=2)

    await bot.send_chat_action(cid, 'typing', timeout=1)

    length = rs.llen(cid)
    if length:
        try:
            await bot.edit_message_text(
                chat_id=cid,
                message_id=rs.lindex(cid, -1),
                text=text,
                reply_markup=markup
            )
        except asyncio_helper.ApiTelegramException:
            await get_quiz_result(message)
            # await reset(message, not_silent=False)
    else:
        m = await bot.send_message(
            chat_id=cid,
            text=text,
            reply_markup=markup,
            disable_notification=True
        )
        rs.lpush(cid, m.message_id)


async def answer_handle(message: types.Message, answer_num: int):
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
    cid = message.chat.id
    result = int(rs.hget('user_data', str(cid)))

    data = Quiz.get_animal(result)
    markup = telebot.util.quick_markup({
        'Пройти заново!': {'callback_data': 'quiz'},
        'Оставить отзыв': {'callback_data': 'animal'},  # TODO сделать прием отзыва!!!
    })

    with open(data['image'], 'rb') as pic:
        await bot.send_photo(
            chat_id=cid,
            photo=pic,
    )

    text = (f'Поздравляем! По итогам теста мы выявили, что ваше тотемное животное «{data["name"]}»\n\n'
            f'{data["description"]}')

    await bot.send_message(
        cid,
        f'Победа! Картинка будет тут. Счет {result}',
        disable_notification=True
    )

# =========================================================
"""

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

    with open(pic, 'rb') as logo:  # будет ли работать как и должно?
        m = await bot.send_photo(
            message.chat.id,
            photo=logo,
            caption=caption,
            parse_mode='HTML',
            reply_markup=markup,
            disable_notification=True
        )
    rs.lpush('{0}media'.format(cid), m.message_id)
    
"""
#   =================================================



async def show_animal(message: types.Message):
    cid = str(message.chat.id)
    animal_name, animal_pic_url = zoo_parser.random_animal()

    kind_words = ('красивый', 'интересный', 'необычный', 'забавный', 'дикий')
    rand = randrange(len(kind_words))

    caption = (f'Вот этот {kind_words[rand]} обитатель "{animal_name}" ждет своего опекуна. '
               f'Более подробно о программе опеки можно узнать после прохождения викторины. ' + u'😉')

    markup = telebot.util.quick_markup({
        'Викторина!': {'callback_data': 'quiz'},
        'Хочу еще!': {'callback_data': 'animal'},
    })

    media = types.InputMediaPhoto(
        media=animal_pic_url,
        caption=caption,
        parse_mode='HTML'
    )
    await bot.edit_message_media(
        media=media,
        chat_id=cid,
        message_id=rs.lindex(cid + 'media', -1),
        reply_markup=markup
    )


async def opeka_info(message: types.Message):  # TODO разделить текст опеки и картинку с примером
    cid = str(message.chat.id)

    text = ('<strong>Московский Зоопарк</strong> представляет программу опеки, благодаря которой '
            'вы можете оказать помощь в содержании различных видов животных. '
            'Стать участником программы <i>«Клуб друзей зоопарка»</i> значит '
            'позаботиться о ком то из его обитателей, помочь зоопарку в развитии '
            'и внести личный вклад в их дело сохранения природы и биоразнообразия Земли. '
            'Подробнее можно посмотреть <a href="https://moscowzoo.ru/about/guardianship">тут</a>.')

    markup = telebot.util.quick_markup({  # TODO Проверить и переделать кнопки
        'Перейти к викторине!': {'callback_data': 'quiz'},
        'Показать другое животное :)': {'callback_data': 'opeka_info'},
    })
    m = await bot.send_message(
        chat_id=cid,
        text=text,
        disable_notification=True,
        reply_markup=markup,
        parse_mode='HTML',
    )
    rs.lpush(cid, m.message_id)


@bot.message_handler(commands=['repost'])  # FIXME дебаг команда, убрать после настройки
async def vk_repost(message: types.Message):
    url = VK_REQUEST

    # session = vk_api.VkApi(
    #     app_id=VK_APP_ID,
    #     client_secret=VK_SECRET_KEY,
    # )

    # vk = session.get_api()
    # vk_id = vk.account.getProfileInfo()['id']
    # print(vk_id)

    text = f'{message.from_user.username} Hello from backend!'
    attachments = 'https://t.me/sf_learn_bot'
    # https: // t.me / sf_learn_bot
    # id46353511
    # vk.wall.post(
    #     owner_id=vk_id,
    #     message=text,
    #     attachments=attachments
    # )


@bot.callback_query_handler(func=lambda callback: True)
async def callback_handler(callback: types.CallbackQuery):
    msg = callback.message
    data = callback.data
    if data == 'start':
        await cmd_start(msg)
    elif data == 'quiz':
        val = get_user_question_number(msg.chat.id)
        if val == -1:
            await reset(msg, True)
        else:
            await next_question(msg)
    elif data == 'animal':
        await show_animal(msg)
    elif data == 'opeka_info':
        await opeka_info(msg)
    else:
        try:
            data = int(data)
        except Exception as e:
            log.debug(e)
        await answer_handle(msg, data)


if __name__ == '__main__':
    asyncio.run(bot.infinity_polling())


# TODO команда reset: переделать в cmd? или запускать после полного прохождения?
# TODO команда start: сделать картинку зоопарка в основу текста
# TODO сделать парсер животных для опеки с сайта зоопарка и сделать вывод случайного животного по кнопке
