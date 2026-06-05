# database/engine.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Указываем путь к файлу базы данных (создастся в корне проекта)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'bot_database.db')}"

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=True) # echo=True покажет SQL-запросы в консоли

# Фабрика сессий (через нее будем делать запросы к БД)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Базовый класс для всех моделей
Base = declarative_base()

# Функция для инициализации базы данных (создание таблиц)
async def init_db():
    async with engine.begin() as conn:
        # В рабочей среде здесь используются миграции (Alembic),
        # но для начала мы просто создадим таблицы, если их нет.
        await conn.run_sync(Base.metadata.create_all)