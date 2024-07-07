import os
from dotenv import load_dotenv
from telebot.asyncio_handler_backends import State, StatesGroup
from datetime import timedelta


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# bot token
TOKEN = os.getenv('TOKEN')

# redis settings
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = os.getenv('REDIS_PORT')

# vk keys
VKTOKEN = os.getenv('VKTOKEN')
VK_APP_ID = os.getenv('VK_APP_ID')
VK_SERVICE_KEY = os.getenv('VK_SERVICE_KEY')
VK_SECRET_KEY = os.getenv('VK_SECRET_KEY')
VK_REQUEST = os.getenv('VK_REQUEST')

# communications manager
MANAGER_ID = os.getenv('MANAGER_ID')

# zoo parser settings
ZOO_PARSER_UPDATE_FREQUENCY = timedelta(days=7)
ZOO_PARSER_SELENIUM_WAITING_TIME = 10


class States(StatesGroup):
    contact_response = State()
    review_response = State()
