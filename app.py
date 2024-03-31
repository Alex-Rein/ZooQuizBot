#  Тема викторины — «Какое у вас тотемное животное?»
#  Redis data names: 'user_question', 'user_data', message.chat.id for user messages to handle

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
    clear(message)
    if not rs.hget('user_data', cid):
        rs.hset('user_data', cid, '0000')

    markup = telebot.util.quick_markup({'Начать викторину!': {'callback_data': 'quiz'},
                                        'Информация': {'callback_data': 'opeka_info'}})

    m = bot.send_message(message.chat.id, 'Привет, %s! Предлогаю поучавствовать '
                                          'в небольшой викторине «Какое у вас тотемное животное?» '
                                          'Делается это чисто в развлекательных целях и для того чтобы '
                                          'немного прикоснуться к миру братьев меньших, так что без обид!'
                         % message.chat.first_name,
                         reply_markup=markup, disable_notification=True)
    rs.lpush(str(cid), m.message_id)


@bot.message_handler(commands=['reset'])
def cmd_reset(message: types.Message):
    clear(message)
    cid = message.chat.id
    bot.send_message(cid, 'Хорошо! Давай начнем сначала.', disable_notification=True)
    set_user_question_number(cid, 0)
    rs.hset('user_data', str(cid), '0000')
    next_question(message)


@bot.message_handler(commands=['score'])  # ДЕБАГ КОМАНДА
def dbg_score(message: types.Message):
    bot.send_message(message.chat.id, message.from_user.username, disable_notification=True)
    if message.from_user.username == 'Darkozavr':
        var = rs.hget('user_data', str(message.chat.id))
        bot.send_message(message.chat.id, var, disable_notification=True)


@bot.message_handler(commands=['clear'])
def clear(message: types.Message):
    cid = str(message.chat.id)
    if rs.llen(cid):
        for _ in range(rs.llen(cid)):
            m = rs.lpop(cid)
            # bot.delete_message(str(cid), int(m))
            try:
                bot.edit_message_reply_markup(chat_id=int(cid),
                                              message_id=int(m),
                                              reply_markup=None)
            except telebot.apihelper.ApiTelegramException as e:
                pass


@bot.callback_query_handler(func=lambda callback: True)
def callback_handler(callback: types.CallbackQuery):
    cm = callback.message
    try:
        bot.edit_message_reply_markup(chat_id=cm.chat.id,
                                      message_id=cm.message_id,
                                      reply_markup=None)
    except telebot.apihelper.ApiTelegramException as e:
        pass
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
        m = bot.send_message(message.chat.id,
                             'Не знаешь с чего начать? Попробуй кликнуть тут!',
                             reply_markup=markup, disable_notification=True)
        rs.lpush(cid, m.message_id)
    else:
        markup = telebot.util.quick_markup({'Начало!': {'callback_data': 'start'},
                                            'К викторине': {'callback_data': 'quiz'}})
        m = bot.send_message(message.chat.id, 'Что то не так? Мы можем вернуться в начало или же '
                                              'к последнему вопросу викторины.', reply_markup=markup,
                             disable_notification=True)
        rs.lpush(cid, m.message_id)


def next_question(message: types.Message):
    quiz = Quiz.quiz.copy()
    cid = message.chat.id
    q_num = get_user_question_number(cid)

    if q_num >= len(quiz):
        bot.send_message(message.chat.id, 'Это был последний вопрос, а сейчас посмотрим'
                                          ' что у нас получилось :) Чтобы попробовать еще раз'
                                          ' восользуйтесь командой /reset', disable_notification=True)
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
    m = bot.send_message(cid, text, reply_markup=markup, disable_notification=True)
    rs.lpush(str(cid), m.message_id)


def after_answer_react(message: types.Message, answer_num):
    cid = message.chat.id
    q_num = get_user_question_number(cid)
    quiz = Quiz.quiz.copy()

    if q_num >= len(quiz):
        # bot.send_message(cid, 'Ошибка', disable_notification=True)
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
    bot.send_message(cid, 'Победа! Картинка будет тут', disable_notification=True)  # ДЕБАГ ТЕКСТ


bot.polling()
