import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Обязательно переводим ID в число, это важно для проверок aiogram
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))