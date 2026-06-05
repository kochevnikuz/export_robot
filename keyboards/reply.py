from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu(user_role: str) -> ReplyKeyboardMarkup:
    # Добавили кнопку "📋 Список инвойсов"
    buttons = [
        [KeyboardButton(text="📄 Новый инвойс"), KeyboardButton(text="📋 Список инвойсов")],
        [KeyboardButton(text="🏢 Добавить компанию"), KeyboardButton(text="📜 Добавить контракт")],
        [KeyboardButton(text="📊 Статистика")]
    ]

    if user_role == 'admin':
        buttons.append([KeyboardButton(text="👥 Добавить декларанта")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие 👇"
    )