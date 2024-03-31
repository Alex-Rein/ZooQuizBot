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


@bot.message_handler(commands=['start', 'help'])
def cmd_start(message: types.Message):
    cid = str(message.chat.id)
    if not rs.hget('user_data', cid):
        rs.hset('user_data', str(cid), '0000')

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
    rs.hset('user_data', str(cid), '0000')
    next_question(message)


@bot.message_handler(commands=['score'])  # ДЕБАГ КОМАНДА
def dbg_score(message: types.Message):
    bot.send_message(message.chat.id, message.from_user.username)
    if message.from_user.username == 'Darkozavr':
        var = rs.hget('user_data', str(message.chat.id))
        bot.send_message(message.chat.id, var)


@bot.message_handler(commands=['clear'])  # ДЕБАГ КОМАНДА
def dbg_clear(message: types.Message):
    bot.edit_message_reply_markup(chat_id=message.chat.id)
    # ДОБАВИТЬ ЛИСТЕНЕР ДЛЯ УДАЛЕНИЯ ПРЕДЫДУЩИХ СООБЩЕНИЙ ПО ИХ АЙДИ
    # ИЛИ УДАЛЯТЬ ПРИ ПЕРЕЗАПУСКЕ ВОПРОСОВ

@bot.callback_query_handler(func=lambda callback: True)
def callback_handler(callback: types.CallbackQuery):
    bot.edit_message_reply_markup(chat_id=callback.message.chat.id,
                                  message_id=callback.message.message_id)
    bot.delete_message()
    cm = callback.message
    if callback.data == 'start':
        cmd_start(callback.message)
    elif callback.data == 'quiz':
        next_question(callback.message)
    elif callback.data == '1':
        after_answer_react(cm, 1)
    elif callback.data == '2':
        after_answer_react(cm, 2)
    elif callback.data == '3':
        after_answer_react(cm, 3)
    elif callback.data == '4':
        after_answer_react(cm, 4)


@bot.message_handler(content_types=['text'])
def text_handler(message: types.Message):
    """Обработка для всех сообщений кроме команд"""
    cid = str(message.chat.id)
    if not rs.hget('user_data', cid):
        markup = telebot.util.quick_markup({'Начало!': {'callback_data': 'start'}})
        bot.send_message(message.chat.id,
                         'Не знаешь с чего начать? Попробуй кликнуть тут!',
                         reply_markup=markup)
    else:
        markup = telebot.util.quick_markup({'Начало!': {'callback_data': 'start'},
                                   'К викторине': {'callback_data': 'quiz'}})
        bot.send_message(message.chat.id,
                         'Что то не так? Мы можем вернуться в начало или же '
                         'к последнему вопросу викторины.',
                         reply_markup=markup)

    # if message.text not in [x.command for x in bot.get_my_commands()]:
    #     bot.send_message(message.chat.id,
    #                      'Не знаешь с чего начать? Попробуй кликнуть тут!',
    #                      reply_markup=markup)


def next_question(message: types.Message):
    quiz = Quiz.quiz.copy()
    cid = message.chat.id
    q_num = get_user_question_number(cid)

    if q_num >= len(quiz):
        bot.send_message(message.chat.id, 'Это был последний вопрос, а сейчас посмотрим'
                                          ' что у нас получилось :) Чтобы попробовать еще раз'
                                          ' восользуйтесь командой /reset')
        get_quiz_result(message)
        return

    text = ''
    btns = {}
    for question in quiz[q_num]:
        text = question
        num = 1
        for answer in quiz[q_num][question]:
            btns[answer] = {'callback_data': str(num)}
            num += 1

    markup = telebot.util.quick_markup(btns, row_width=2)
    bot.send_message(cid, text, reply_markup=markup)


def after_answer_react(message: types.Message, answer_num):
    cid = message.chat.id
    q_num = get_user_question_number(cid)
    quiz = Quiz.quiz.copy()

    if q_num >= len(quiz):
        bot.send_message(cid, 'Ошибка')
        return

    for que in quiz[q_num]:
        num = 1
        for ans in quiz[q_num][que]:
            if num != answer_num:
                num += 1
                continue

            for par, val in quiz[q_num][que][ans]:
                vars_ = int(rs.hget('user_data', str(cid)))
                if par == 'group':
                    if vars_ < 1000:
                        vars_ += 1000
                elif par == 'feature':
                    if (0 <= vars_ - 1000 < 100) or (0 <= vars_ < 100):
                        vars_ += 100
                elif par == 'var':
                    vars_ += val
                rs.hset('user_data', str(cid), str(vars_))
    set_user_question_number(cid, q_num + 1)
    next_question(message)


def get_quiz_result(message: types.Message):
    cid = message.chat.id
    bot.send_message(cid, 'Победа! Картинка будет тут')  # ДЕБАГ ТЕКСТ


bot.polling()
