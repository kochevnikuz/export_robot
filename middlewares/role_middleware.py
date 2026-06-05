# middlewares/role_middleware.py
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable
from sqlalchemy import select
from database.models import User
from config import ADMIN_ID


class RoleMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:

        # Получаем ID пользователя
        tg_id = event.from_user.id
        session = data['session']  # Сессия БД, которую мы передали в предыдущем Middleware

        # 1. Проверяем, это ли ГЛАВНЫЙ АДМИН (из файла .env)
        if tg_id == ADMIN_ID:
            # Проверяем, есть ли админ в базе. Если нет - создаем автоматически
            admin_user = await session.scalar(select(User).where(User.telegram_id == tg_id))
            if not admin_user:
                admin_user = User(telegram_id=tg_id, role='admin', full_name=event.from_user.full_name)
                session.add(admin_user)
                await session.commit()

            # Пропускаем админа дальше
            data['user_role'] = 'admin'
            data['user_db_id'] = admin_user.id
            return await handler(event, data)

        # 2. Если это не главный админ, ищем его в базе (Декларант)
        user = await session.scalar(select(User).where(User.telegram_id == tg_id))

        # Если пользователя нет в базе или он отключен (is_active=False)
        if not user or not user.is_active:
            await event.answer("⛔️ У вас нет доступа к этой системе. Обратитесь к администратору.")
            return  # Блокируем запрос, дальше он не пойдет!

        # 3. Пользователь найден, пускаем дальше
        data['user_role'] = user.role
        data['user_db_id'] = user.id

        return await handler(event, data)