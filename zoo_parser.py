import redis
import json
import time

from random import randrange
from bs4 import BeautifulSoup
from selenium import webdriver
from config import REDIS_HOST, REDIS_PORT, ZOO_PARSER_UPDATE_FREQUENCY, ZOO_PARSER_SELENIUM_WAITING_TIME
from datetime import datetime


rs = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)


def _init_():
    url = 'https://moscowzoo.ru/about/guardianship/waiting-guardianship'
    date = datetime.now().date()
    previous_date = rs.hget('meta', 'update')
    # previous_date = '2020-01-01'  # FIXME дебаг фича
    if previous_date:
        previous_date = datetime.strptime(previous_date, '%Y-%m-%d').date()
    else:
        previous_date = datetime.strptime('2020-01-01', '%Y-%m-%d').date()

    if (date - previous_date) >= ZOO_PARSER_UPDATE_FREQUENCY:  # update frequency
        with webdriver.Firefox() as driver:
            driver.get(url)
            time.sleep(ZOO_PARSER_SELENIUM_WAITING_TIME)
            with open('zoo_guardianship', 'wt') as f:
                f.write(json.dumps(driver.page_source))
                soup = BeautifulSoup(driver.page_source, 'lxml')
            animals = soup.find_all('a', class_='waiting-for-guardian-animals__item animal')
            data = []
            for animal in animals:
                name = animal.find_next(class_='animal__name').text
                img = animal.find_next(class_='animal__image').get('src')
                data.append((name, img))
            with open('zoo_animals', 'wt') as f:
                f.write(json.dumps(data))
            rs.hset('meta', 'update', str(datetime.now().date()))


def random_animal():
    """Возвращает кортеж (name, url) с именем и ссылкой на изображение животного"""
    with open('zoo_animals', 'rt') as f:
        data = json.loads(f.readline())
    rand = randrange(len(data))
    return data[rand]  # name и url животного


_init_()  # для подгрузки картинок при подключении модуля
