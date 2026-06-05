# handlers/admin.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from database.models import User

# Создаем роутер для админских команд
admin_router = Router()


# Описываем состояния для Машины Состояний (FSM)
class AddDeclarantStates(StatesGroup):
    waiting_for_tg_id = State()
    waiting_for_name = State()


# 1. Начало процесса добавления (Доступно только админу)
@admin_router.message(Command("add_declarant"))
@admin_router.message(F.text == "👥 Добавить декларанта")
async def start_add_declarant(message: Message, state: FSMContext, user_role: str):
    if user_role != 'admin':
        await message.answer("⚠️ Эта команда доступна только администратору.")
        return

    await message.answer(
        "📝 Начинаем добавление декларанта.\n"
        "Отправьте мне его **Telegram ID** (только цифры).\n\n"
        "Для отмены отправьте команду /cancel"
    )
    await state.set_state(AddDeclarantStates.waiting_for_tg_id)


# Хэндлер отмены в любой момент
@admin_router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=ReplyKeyboardRemove())


# 2. Ловим Telegram ID
@admin_router.message(AddDeclarantStates.waiting_for_tg_id)
async def process_tg_id(message: Message, state: FSMContext, session):
    # Проверяем, что введены именно цифры
    if not message.text.isdigit():
        await message.answer("⚠️ ID должен состоять только из цифр. Попробуйте еще раз:")
        return

    tg_id = int(message.text)

    # Проверяем, нет ли уже такого пользователя в базе
    existing_user = await session.scalar(select(User).where(User.telegram_id == tg_id))
    if existing_user:
        await message.answer(f"⚠️ Пользователь с ID {tg_id} уже есть в базе данных с ролью {existing_user.role}.")
        await state.clear()
        return

    # Сохраняем ID во временную память FSM
    await state.update_data(tg_id=tg_id)

    await message.answer("Отлично! Теперь введите **ФИО** декларанта:")
    await state.set_state(AddDeclarantStates.waiting_for_name)


# 3. Ловим ФИО и сохраняем в базу данных
@admin_router.message(AddDeclarantStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext, session):
    full_name = message.text.strip()

    # Извлекаем ранее сохраненный ID из памяти FSM
    user_data = await state.get_data()
    tg_id = user_data['tg_id']

    try:
        # Создаем нового пользователя в базе данных
        new_declarant = User(
            telegram_id=tg_id,
            full_name=full_name,
            role='declarant',
            is_active=True
        )
        session.add(new_declarant)
        await session.commit()  # Фиксируем транзакцию асинхронно

        await message.answer(
            f"✅ Декларант успешно добавлен!\n\n"
            f"🆔 ID: `{tg_id}`\n"
            f"👤 ФИО: {full_name}\n"
            f"💼 Роль: Декларант"
        )
    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Ошибка при сохранении в базу данных: {e}")
    finally:
        await state.clear()  # Очищаем состояние в конце