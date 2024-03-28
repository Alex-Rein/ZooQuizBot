#  Тема викторины — «Какое у вас тотемное животное?»

import telebot
from telebot import types
import redis
import time

import config
# from config import TOKEN, REDIS_HOST, REDIS_PORT, States
from quiz import Quiz

bot = telebot.TeleBot(config.TOKEN)
rs = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=0, decode_responses=True)


def get_user_question_number(uid):
    users_question = rs.hgetall('users_question')
    uid = str(uid)
    if uid in users_question:
        return int(users_question[uid])
    else:
        rs.hset('users_question', mapping={uid: '0'})
        return 0


def set_user_question_number(uid, value):
    uid, value = str(uid), str(value)
    rs.hset('users_question', mapping={uid: value})


# def set_user_state(uid, value):
#     rs.hset('users_state', mapping={uid: value})
#     return True


# def get_user_state(uid):
#     users_state = rs.hgetall('users_state')
#     if uid in users_state:
#         return users_state[uid]
#     else:
#         rs.hset('users_state', mapping={uid: 0})
#         return 0


# def listener(messages):
#     """
#     When new messages arrive TeleBot will call this function.
#     """
#     for message in messages:
#         if message.content_type == 'text':
#             # print the sent message to the console
#             print(str(message.chat.first_name) + " [" + str(message.chat.id) + "]: " + message.text)


# bot.set_update_listener(listener)  # register listener


@bot.message_handler(commands=['start', 'help'])
def cmd_start(message: types.Message):
    # cid = str(message.chat.id)
    # if cid not in rs.hget('users_question', cid):
    #     set_user_question_number(cid, 0)

    markup = telebot.util.quick_markup({'Начать викторину!': {'callback_data': 'quiz'},
                                        'Информация': {'callback_data': 'opeka_info'}})

    bot.send_message(message.chat.id, 'Привет, %s! Предлогаю поучавствовать '
                                      'в небольшой викторине «Какое у вас тотемное животное?» '
                                      'и попробовать выяснить какое животное тебе близко по духу! '
                                      'Делается это чисто в развлекательных целях и для того чтобы '
                                      'немного прикоснуться к миру братьев меньших, так что без обид!'
                                      % message.chat.first_name,
                     reply_markup=markup)


@bot.message_handler(commands=['reset'])
def cmd_reset(message: types.Message):
    cid = message.chat.id
    bot.send_message(cid, 'Хорошо! Давай начнем сначала.')
    set_user_question_number(cid, 0)
    next_question(message)


@bot.callback_query_handler(func=lambda callback: True)
def callback_handler(callback: types.CallbackQuery):
    bot.edit_message_reply_markup(chat_id=callback.message.chat.id,
                                  message_id=callback.message.message_id)
    if callback.data == 'start':
        # bot.answer_callback_query(callback.id, '<3')
        cmd_start(callback.message)
    elif callback.data == 'quiz':
        next_question(callback.message)
    elif callback.data == '1':
        # Работа с параметрами ответа
        # quiz(callback.message)
        pass
    elif callback.data == '2':
        # Работа с параметрами ответа
        # quiz(callback.message)
        pass
    elif callback.data == '3':
        # Работа с параметрами ответа
        # quiz(callback.message)
        pass
    elif callback.data == '4':
        # Работа с параметрами ответа
        # quiz(callback.message)
        pass


@bot.message_handler(content_types=['text'])
def text_handler(message: types.Message):
    """Обработка для всех сообщений кроме команд"""
    markup = telebot.util.quick_markup({'Начало!': {'callback_data': 'start'}})
    if message.text not in [x.command for x in bot.get_my_commands()]:
        bot.send_message(message.chat.id,
                         'Не знаешь с чего начать? Попробуй кликнуть тут!',
                         reply_markup=markup)


def next_question(message: types.Message):
    quiz = Quiz.quiz
    cid = message.chat.id
    quest_num = get_user_question_number(cid)
    text = ''
    try:
        text = quiz[quest_num].get()
    except Exception as e:
        print('Something goes wrong \n', e)
        pass

    markup = types.InlineKeyboardMarkup(row_width=2)
    # добавить кнопки с ответами
    bot.send_message(cid, text, reply_markup=markup)

    # !!! Добавить проверку наличия или создание нового пользователя.

    # for item in quiz:
    #     markup = types.InlineKeyboardMarkup(row_width=2)
    #     num = 1
    #     q = ''
    #     for question in item:
    #         q = question
    #         for answer_ in item[question]:
    #             markup.add(types.InlineKeyboardButton(text=answer_, callback_data=str(num)))
    #             num += 1
    #     bot.send_message(message.chat.id, q, reply_markup=markup)


def get_quiz_result(message: types.Message):
    pass


# @bot.message_handler(func=lambda message: get_user_state(message.chat.id) == config.States.ANSWER.value)
# def answer(message: types.Message):
#     pass


# @bot.message_handler(func=lambda m: True)
# def echo_all(message):
#     bot.reply_to(message, message.text)

bot.polling()
