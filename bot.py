# bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from config import BOT_TOKEN
from keyboards.reply import get_main_menu

import database.models
from database.engine import init_db, AsyncSessionLocal
from aiogram import BaseMiddleware
from middlewares.role_middleware import RoleMiddleware

# === ИСПРАВЛЕНИЕ: ИМПОРТИРУЕМ РОУТЕР АДМИНА ===
from handlers.admin import admin_router
from handlers.declarant import declarant_router
from handlers.dictionaries import dict_router
from handlers.statistics import stats_router

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with AsyncSessionLocal() as session:
            data['session'] = session
            return await handler(event, data)

dp.update.middleware(DbSessionMiddleware())
dp.message.middleware(RoleMiddleware())

# === ПОДКЛЮЧАЕМ РОУТЕР К ДИСПЕТЧЕРУ ===
dp.include_router(admin_router)
dp.include_router(declarant_router)
dp.include_router(dict_router)
dp.include_router(stats_router)

# Замени функцию cmd_start на эту:
@dp.message(CommandStart())
async def cmd_start(message: Message, user_role: str):
    # Генерируем клавиатуру под роль пользователя
    kb = get_main_menu(user_role)

    if user_role == 'admin':
        await message.answer(
            "👑 Привет, Администратор!\n"
            "Выберите нужное действие в меню ниже:",
            reply_markup=kb
        )
    else:
        await message.answer(
            "👋 Привет, Декларант!\n"
            "Добро пожаловать в систему логистики. Выберите действие:",
            reply_markup=kb
        )

async def main():
    print("Инициализация базы данных...")
    await init_db()
    print("Запускаем бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")