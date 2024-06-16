import redis
import json
import time

from random import randrange
from bs4 import BeautifulSoup
from selenium import webdriver
from config import REDIS_HOST, REDIS_PORT
from datetime import datetime, timedelta


rs = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

UPDATE_FREQUENCY = timedelta(days=7)
SELENIUM_WAITING = 10  # waiting for loading in seconds


def _init_():
    url = 'https://moscowzoo.ru/about/guardianship/waiting-guardianship'
    date = datetime.now().date()
    previous_date = rs.hget('meta', 'update')
    if previous_date:
        previous_date = datetime.strptime(previous_date, '%Y-%m-%d').date()
    else:
        previous_date = datetime.strptime('2020-01-01', '%Y-%m-%d').date()

    if (date - previous_date) >= UPDATE_FREQUENCY:  # update frequency
        with webdriver.Firefox() as driver:
            driver.get(url)
            time.sleep(SELENIUM_WAITING)
            with open('zoo_guardianship', 'wt') as f:
                f.write(json.dumps(driver.page_source))
                soup = BeautifulSoup(driver.page_source, 'lxml')
            animals = soup.find_all('div', class_='waiting-for-guardian-animals__item animal')
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
    with open('zoo_animals2', 'rt') as f:
        data = json.loads(f.readline())
    rand = randrange(len(data))
    return data[rand]  # name и url животного


_init_()  # для подгрузки картинок при подключении модуля
