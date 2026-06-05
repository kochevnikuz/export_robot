# handlers/statistics.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func, delete
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from sqlalchemy.exc import IntegrityError
from database.models import User, Company, Contract, Invoice, InvoiceItem
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime


stats_router = Router()

# 1. Кнопки главного меню статистики
class StatsMenuCb(CallbackData, prefix="stat_menu"):
    action: str # 'senders', 'consignees', 'contracts'

# 2. Кнопки управления конкретной записью
class ManageItemCb(CallbackData, prefix="manage"):
    item_type: str # 'company' или 'contract'
    item_id: int
    action: str # 'view', 'edit', 'delete'

# --- КЛАСС ДЛЯ ВЫБОРА ПОЛЯ РЕДАКТИРОВАНИЯ ---
class EditFieldCb(CallbackData, prefix="edit_fld"):
    item_type: str
    item_id: int
    field: str

# --- FSM ДЛЯ ОЖИДАНИЯ НОВОГО ЗНАЧЕНИЯ ---
class EditItemStates(StatesGroup):
    waiting_for_value = State()

# Словарь для красивого вывода названий полей
FIELD_NAMES_RU = {
    "name": "Название",
    "country_code": "Код страны",
    "legal_address": "Юридический адрес",
    "tax_id": "ИНН",
    "area_code": "Код региона",
    "cmr_13": "13 графа CMR",
    "contract_number": "Номер контракта",
    "contract_date": "Дата контракта (ДД.ММ.ГГГГ)",
    "incoterms": "Incoterms",
    "incoterms_place": "Место назначения",
    "currency": "Валюта"
}


@stats_router.message(Command("stats"))
@stats_router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message, session, user_role: str):
    if user_role not in ['admin', 'declarant']:
        return

    # Запрашиваем количество данных (считаем по ID)
    users_count = await session.scalar(select(func.count(User.id)))

    # Считаем компании с разбивкой по типу
    senders = await session.scalar(select(func.count(Company.id)).where(Company.company_type == 'sender'))
    consignees = await session.scalar(select(func.count(Company.id)).where(Company.company_type == 'consignee'))

    contracts_count = await session.scalar(select(func.count(Contract.id)))

    # Статистика инвойсов
    total_invoices = await session.scalar(select(func.count(Invoice.id)))
    draft_invoices = await session.scalar(select(func.count(Invoice.id)).where(Invoice.status == 'draft'))
    completed_invoices = await session.scalar(select(func.count(Invoice.id)).where(Invoice.status == 'completed'))

    # Общее количество загруженных товарных позиций
    total_items = await session.scalar(select(func.count(InvoiceItem.id)))

    # Формируем красивое сообщение
    text = (
        "📊 **Сводная статистика системы:**\n\n"
        f"👥 Зарегистрировано сотрудников: **{users_count}**\n\n"
        "🏢 **Справочники:**\n"
        f"├ Отправителей: **{senders}**\n"
        f"├ Получателей: **{consignees}**\n"
        f"└ Контрактов: **{contracts_count}**\n\n"
        "📄 **Инвойсы:**\n"
        f"├ Всего создано: **{total_invoices}**\n"
        f"├ В процессе (черновики): **{draft_invoices}**\n"
        f"├ Готовые инвойсы: **{completed_invoices}**\n"
        f"└ Всего товаров: **{total_items}**\n"
    )

    # --- ДОБАВЛЯЕМ КНОПКИ УПРАВЛЕНИЯ ---
    builder = [
        [
            InlineKeyboardButton(text="📤 Отправители", callback_data=StatsMenuCb(action="senders").pack()),
            InlineKeyboardButton(text="📥 Получатели", callback_data=StatsMenuCb(action="consignees").pack())
        ],
        [InlineKeyboardButton(text="📜 Контракты", callback_data=StatsMenuCb(action="contracts").pack())]
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=builder)

    await message.answer(text, reply_markup=kb)


# --- ВЫВОД СПИСКОВ ИЗ БАЗЫ ---
@stats_router.callback_query(StatsMenuCb.filter())
async def show_items_list(call: CallbackQuery, callback_data: StatsMenuCb, session):
    action = callback_data.action
    builder = []

    if action == "senders":
        items = (await session.scalars(select(Company).where(Company.company_type == 'sender'))).all()
        text_header = "📤 **Список Отправителей:**"
        for item in items:
            builder.append([InlineKeyboardButton(text=item.name,
                                                 callback_data=ManageItemCb(item_type="company", item_id=item.id,
                                                                            action="view").pack())])

    elif action == "consignees":
        items = (await session.scalars(select(Company).where(Company.company_type == 'consignee'))).all()
        text_header = "📥 **Список Получателей:**"
        for item in items:
            builder.append([InlineKeyboardButton(text=item.name,
                                                 callback_data=ManageItemCb(item_type="company", item_id=item.id,
                                                                            action="view").pack())])

    elif action == "contracts":
        items = (await session.scalars(select(Contract))).all()
        text_header = "📜 **Список Контрактов:**"
        for item in items:
            builder.append([InlineKeyboardButton(text=f"№ {item.contract_number} ({item.currency})",
                                                 callback_data=ManageItemCb(item_type="contract", item_id=item.id,
                                                                            action="view").pack())])

    if not items:
        await call.answer("📭 В этой категории пока нет записей.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=builder)
    await call.message.edit_text(text_header, reply_markup=kb)
    await call.answer()


# --- ПРОСМОТР КАРТОЧКИ ОБЪЕКТА ---
@stats_router.callback_query(ManageItemCb.filter(F.action == "view"))
async def view_item_details(call: CallbackQuery, callback_data: ManageItemCb, session):
    item_type = callback_data.item_type
    item_id = callback_data.item_id

    if item_type == "company":
        item = await session.get(Company, item_id)
        if not item:
            await call.answer("❌ Компания не найдена.", show_alert=True)
            return

        text = (
            f"🏢 **Карточка компании:**\n\n"
            f"**Название:** {item.name}\n"
            f"**Тип:** {'Отправитель' if item.company_type == 'sender' else 'Получатель'}\n"
            f"**ИНН:** {item.tax_id or 'Нет'}\n"
            f"**Страна:** {item.country_code}\n"
            f"**Код региона:** {item.area_code or 'Нет'}\n"
            f"**Адрес:** {item.legal_address}\n"
            f"**13 Графа CMR:** {item.cmr_13 or 'Нет'}"
        )

    elif item_type == "contract":
        item = await session.get(Contract, item_id)
        if not item:
            await call.answer("❌ Контракт не найден.", show_alert=True)
            return

        text = (
            f"📜 **Карточка контракта:**\n\n"
            f"**Номер:** {item.contract_number}\n"
            f"**Дата:** {item.contract_date}\n"
            f"**Условия:** {item.incoterms} {item.incoterms_place}\n"
            f"**Валюта:** {item.currency}"
        )

    # Кнопки управления (Редактировать и Удалить)
    builder = [
        [
            InlineKeyboardButton(text="✏️ Редактировать",
                                 callback_data=ManageItemCb(item_type=item_type, item_id=item_id,
                                                            action="edit").pack()),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=ManageItemCb(item_type=item_type, item_id=item_id,
                                                                              action="delete").pack())
        ]
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=builder)

    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# --- УДАЛЕНИЕ ОБЪЕКТА ---
@stats_router.callback_query(ManageItemCb.filter(F.action == "delete"))
async def delete_item(call: CallbackQuery, callback_data: ManageItemCb, session):
    item_type = callback_data.item_type
    item_id = callback_data.item_id

    try:
        if item_type == "company":
            item = await session.get(Company, item_id)
            if not item:
                await call.message.edit_text("❌ Ошибка: Компания не найдена.")
                return
            name = item.name

            # --- ЗАПУСК КАСКАДА ДЛЯ КОМПАНИИ ---
            # 1. Находим ID всех инвойсов, связанных с этой компанией (как отправитель или получатель)
            inv_stmt = select(Invoice.id).where(
                (Invoice.company_id == item_id) | (Invoice.consignee_id == item_id)
            )
            invoice_ids = (await session.scalars(inv_stmt)).all()

            if invoice_ids:
                # 2. Удаляем все товары (InvoiceItem), которые лежат внутри этих инвойсов
                await session.execute(
                    delete(InvoiceItem).where(InvoiceItem.invoice_id.in_(invoice_ids))
                )
                # 3. Удаляем сами инвойсы
                await session.execute(
                    delete(Invoice).where(Invoice.id.in_(invoice_ids))
                )

            # 4. Удаляем саму компанию
            await session.delete(item)
            text_result = f"🗑 **Каскадное удаление завершено!**\n\nУдалена компания: **{name}**\nУдалено связанных инвойсов: **{len(invoice_ids)}** (вместе со всеми товарами)."

        elif item_type == "contract":
            item = await session.get(Contract, item_id)
            if not item:
                await call.message.edit_text("❌ Ошибка: Контракт не найден.")
                return
            name = item.contract_number

            # --- ЗАПУСК КАСКАДА ДЛЯ КОНТРАКТА ---
            # 1. Находим ID всех инвойсов, привязанных к этому контракту
            inv_stmt = select(Invoice.id).where(Invoice.contract_id == item_id)
            invoice_ids = (await session.scalars(inv_stmt)).all()

            if invoice_ids:
                # 2. Удаляем товары из этих инвойсов
                await session.execute(
                    delete(InvoiceItem).where(InvoiceItem.invoice_id.in_(invoice_ids))
                )
                # 3. Удаляем инвойсы
                await session.execute(
                    delete(Invoice).where(Invoice.id.in_(invoice_ids))
                )

            # 4. Удаляем сам контракт
            await session.delete(item)
            text_result = f"🗑 **Каскадное удаление завершено!**\n\nУдален контракт № **{name}**\nУдалено связанных инвойсов: **{len(invoice_ids)}** (вместе со всеми товарами)."

        # Фиксируем все удаления в базе данных одной транзакцией
        await session.commit()
        await call.message.edit_text(text_result)

    except Exception as e:
        await session.rollback()
        await call.message.edit_text(f"❌ Произошла системная ошибка при удалении:\n`{e}`")


# --- МЕНЮ ВЫБОРА ПОЛЯ ДЛЯ РЕДАКТИРОВАНИЯ ---
@stats_router.callback_query(ManageItemCb.filter(F.action == "edit"))
async def show_edit_options(call: CallbackQuery, callback_data: ManageItemCb, session):
    item_type = callback_data.item_type
    item_id = callback_data.item_id

    builder = []

    if item_type == "company":
        item = await session.get(Company, item_id)
        # Общие поля
        builder.append([InlineKeyboardButton(text="🏢 Название",
                                             callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                       field="name").pack())])
        builder.append([InlineKeyboardButton(text="🌍 Код страны",
                                             callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                       field="country_code").pack())])
        builder.append([InlineKeyboardButton(text="🏠 Адрес",
                                             callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                       field="legal_address").pack())])

        # Уникальные поля по типу
        if item.company_type == "sender":
            builder.append([
                InlineKeyboardButton(text="📑 ИНН", callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                             field="tax_id").pack()),
                InlineKeyboardButton(text="📍 Код региона",
                                     callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                               field="area_code").pack())
            ])
        else:
            builder.append([InlineKeyboardButton(text="📝 13 графа CMR",
                                                 callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                           field="cmr_13").pack())])

    elif item_type == "contract":
        builder.append([
            InlineKeyboardButton(text="🔢 Номер", callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                           field="contract_number").pack()),
            InlineKeyboardButton(text="📅 Дата", callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                          field="contract_date").pack())
        ])
        builder.append([
            InlineKeyboardButton(text="🤝 Incoterms", callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                               field="incoterms").pack()),
            InlineKeyboardButton(text="📍 Место", callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                           field="incoterms_place").pack())
        ])
        builder.append([InlineKeyboardButton(text="💵 Валюта",
                                             callback_data=EditFieldCb(item_type=item_type, item_id=item_id,
                                                                       field="currency").pack())])

    # Кнопка возврата к карточке
    builder.append([InlineKeyboardButton(text="🔙 Назад к карточке",
                                         callback_data=ManageItemCb(item_type=item_type, item_id=item_id,
                                                                    action="view").pack())])

    kb = InlineKeyboardMarkup(inline_keyboard=builder)
    await call.message.edit_text("🛠 **Выберите поле для изменения:**", reply_markup=kb)
    await call.answer()


# --- ЗАПРОС НОВОГО ЗНАЧЕНИЯ ---
@stats_router.callback_query(EditFieldCb.filter())
async def ask_for_new_value(call: CallbackQuery, callback_data: EditFieldCb, state: FSMContext):
    # Сохраняем, что именно мы редактируем
    await state.update_data(
        item_type=callback_data.item_type,
        item_id=callback_data.item_id,
        field=callback_data.field
    )

    field_ru = FIELD_NAMES_RU.get(callback_data.field, callback_data.field)

    # Заменяем сообщение на запрос ввода
    await call.message.edit_text(
        f"✏️ Введите новое значение для поля **«{field_ru}»**:\n\n"
        f"*(Чтобы отменить, просто выберите любое другое действие в нижнем меню)*"
    )
    await state.set_state(EditItemStates.waiting_for_value)
    await call.answer()


# --- СОХРАНЕНИЕ НОВОГО ЗНАЧЕНИЯ В БАЗУ ---
@stats_router.message(EditItemStates.waiting_for_value)
async def save_edited_value(message: Message, state: FSMContext, session):
    data = await state.get_data()
    item_type = data['item_type']
    item_id = data['item_id']
    field = data['field']
    new_value = message.text.strip()

    try:
        if item_type == "company":
            item = await session.get(Company, item_id)
            # Если это 13 графа и ввели "нет"
            if field == "cmr_13" and new_value.lower() == 'нет':
                new_value = ""
            # Функция setattr заменяет item.field = new_value
            setattr(item, field, new_value)

        elif item_type == "contract":
            item = await session.get(Contract, item_id)

            # Обработка даты контракта
            if field == "contract_date":
                try:
                    parsed_date = datetime.strptime(new_value, "%d.%m.%Y").date()
                except ValueError:
                    try:
                        parsed_date = datetime.strptime(new_value, "%Y-%m-%d").date()
                    except ValueError:
                        await message.answer("⚠️ Неверный формат! Попробуйте еще раз в формате ДД.ММ.ГГГГ:")
                        return
                setattr(item, field, parsed_date)
            else:
                # Переводим Incoterms и Валюту в верхний регистр (usd -> USD)
                if field in ["incoterms", "currency"]:
                    new_value = new_value.upper()
                setattr(item, field, new_value)

        await session.commit()

        # Кнопка для быстрого возврата к обновленной карточке
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Посмотреть карточку",
                                  callback_data=ManageItemCb(item_type=item_type, item_id=item_id,
                                                             action="view").pack())]
        ])

        await message.answer(
            f"✅ Поле **«{FIELD_NAMES_RU.get(field, field)}»** успешно обновлено!",
            reply_markup=kb
        )
        await state.clear()

    except Exception as e:
        await session.rollback()
        await message.answer(f"❌ Ошибка при сохранении: {e}")
        await state.clear()