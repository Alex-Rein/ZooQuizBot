import os
from dotenv import load_dotenv


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

TOKEN = os.getenv('TOKEN')
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = os.getenv('REDIS_PORT')
VKTOKEN = os.getenv('VKTOKEN')
VK_APP_ID = os.getenv('VK_APP_ID')
VK_SERVICE_KEY = os.getenv('VK_SERVICE_KEY')
VK_SECRET_KEY = os.getenv('VK_SECRET_KEY')
VK_REQUEST = os.getenv('VK_REQUEST')
