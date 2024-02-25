#  Тема викторины — «Какое у вас тотемное животное?»

import telebot
from config import TOKEN

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=['start', 'help'])
def start(message: telebot.types.Message):
    bot.send_message(message.chat.id, 'Привет!')
    ...


@bot.message_handler(content_types=['text'])
def text_handler(message: telebot.types.Message):
    if message.text not in [x.command for x in bot.get_my_commands()]:
        bot.send_message(message.chat.id,
                         'Не значешь с чего начать? Начни с комманды /start !')


bot.polling(non_stop=True)
