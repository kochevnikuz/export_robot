# handlers/dictionaries.py
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select
from database.models import Company, Contract

dict_router = Router()

# Создаем Callback для выбора компании в контракте
class AddContractCompCb(CallbackData, prefix="addcont_comp"):
    company_id: int


# --- FSM для Компании ---
class AddCompanyStates(StatesGroup):
    company_type = State()
    name = State()
    tax_id = State()
    country_code = State()
    area_code = State()
    address = State()
    cmr_13 = State() # <--- Новый шаг


# --- FSM для Контракта ---
class AddContractStates(StatesGroup):
    company_id = State() # <--- Новый первый шаг
    number = State()
    date = State()
    incoterms = State()
    place = State()
    currency = State()


# ==========================================
#           ДОБАВЛЕНИЕ КОМПАНИИ
# ==========================================
@dict_router.message(Command("add_company"))
@dict_router.message(F.text == "🏢 Добавить компанию")
async def start_add_company(message: Message, state: FSMContext, user_role: str):
    if user_role not in ['admin', 'declarant']: return
    await state.clear()

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправитель"), KeyboardButton(text="Получатель")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "🏢 **Добавление новой компании**\n\n"
        "Выберите тип контрагента:",
        reply_markup=kb
    )
    await state.set_state(AddCompanyStates.company_type)


@dict_router.message(AddCompanyStates.company_type)
async def process_company_type(message: Message, state: FSMContext):
    comp_type = message.text.strip()

    if comp_type == "Отправитель":
        db_type = "sender"
    elif comp_type == "Получатель":
        db_type = "consignee"
    else:
        await message.answer("⚠️ Пожалуйста, используйте кнопки: 'Отправитель' или 'Получатель'.")
        return

    await state.update_data(company_type=db_type)
    await message.answer(
        "Введите **Название компании**:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AddCompanyStates.name)


@dict_router.message(AddCompanyStates.name)
async def process_company_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())

    data = await state.get_data()

    # ЕСЛИ ПОЛУЧАТЕЛЬ — Пропускаем ИНН и сразу спрашиваем Код Страны
    if data['company_type'] == 'consignee':
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="860"), KeyboardButton(text="792")]],
            resize_keyboard=True,
            input_field_placeholder="Введите 3 цифры..."
        )
        await message.answer(
            "🌍 Введите **Код страны** получателя (строго 3 цифры).\n"
            "Нажмите кнопку или введите вручную:",
            reply_markup=kb
        )
        await state.set_state(AddCompanyStates.country_code)

    # ЕСЛИ ОТПРАВИТЕЛЬ — Спрашиваем ИНН как обычно
    else:
        await message.answer("Введите **ИНН** (Tax ID) компании:")
        await state.set_state(AddCompanyStates.tax_id)


@dict_router.message(AddCompanyStates.tax_id)
async def process_company_tax(message: Message, state: FSMContext):
    await state.update_data(tax_id=message.text.strip())

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="860"), KeyboardButton(text="792")]],
        resize_keyboard=True,
        input_field_placeholder="Введите 3 цифры..."
    )
    await message.answer(
        "🌍 Введите **Код страны** отправителя (строго 3 цифры):",
        reply_markup=kb
    )
    await state.set_state(AddCompanyStates.country_code)


@dict_router.message(AddCompanyStates.country_code)
async def process_company_country(message: Message, state: FSMContext):
    code = message.text.strip()
    if not code.isdigit() or len(code) != 3:
        await message.answer("⚠️ Ошибка! Код должен состоять ровно из 3 цифр.")
        return

    await state.update_data(country_code=code)
    data = await state.get_data()

    # ЕСЛИ ПОЛУЧАТЕЛЬ — Пропускаем Код региона и сразу переходим к адресу
    if data['company_type'] == 'consignee':
        await message.answer(
            "Введите **Юридический адрес** получателя:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(AddCompanyStates.address)

    # ЕСЛИ ОТПРАВИТЕЛЬ — Спрашиваем Код региона
    else:
        await message.answer(
            "Введите **Код региона / Area code** (например: `1726`):",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(AddCompanyStates.area_code)


@dict_router.message(AddCompanyStates.area_code)
async def process_company_area(message: Message, state: FSMContext):
    await state.update_data(area_code=message.text.strip())
    await message.answer("Введите **Юридический адрес** компании:")
    await state.set_state(AddCompanyStates.address)


@dict_router.message(AddCompanyStates.address)
async def process_company_address(message: Message, state: FSMContext, session, user_db_id: int):
    address = message.text.strip()
    await state.update_data(address=address)

    data = await state.get_data()

    # ЕСЛИ ПОЛУЧАТЕЛЬ — Спрашиваем 13-ю графу CMR перед сохранением
    if data['company_type'] == 'consignee':
        await message.answer(
            "📝 Введите данные для **13 графы CMR** (Таможня назначения / Указания).\n"
            "Если данные не нужны, напишите `нет`:"
        )
        await state.set_state(AddCompanyStates.cmr_13)

    # ЕСЛИ ОТПРАВИТЕЛЬ — Сохраняем немедленно (13 графа ему не нужна)
    else:
        new_company = Company(
            name=data.get('name'),
            tax_id=data.get('tax_id'),
            country_code=data.get('country_code'),
            area_code=data.get('area_code'),
            legal_address=address,
            company_type="sender",
            cmr_13=None,
            created_by=user_db_id
        )
        session.add(new_company)
        await session.commit()

        await message.answer(f"✅ Отправитель **{new_company.name}** успешно добавлен!")
        await state.clear()


@dict_router.message(AddCompanyStates.cmr_13)
async def process_company_cmr13(message: Message, state: FSMContext, session, user_db_id: int):
    cmr_text = message.text.strip()
    cmr_13_data = "" if cmr_text.lower() == 'нет' else cmr_text

    data = await state.get_data()

    new_company = Company(
        name=data.get('name'),
        tax_id=None,  # Для получателя принудительно None
        country_code=data.get('country_code'),
        area_code=None,  # Для получателя принудительно None
        legal_address=data.get('address'),
        company_type="consignee",
        cmr_13=cmr_13_data,
        created_by=user_db_id
    )
    session.add(new_company)
    await session.commit()

    await message.answer(f"✅ Получатель **{new_company.name}** успешно добавлен!")
    await state.clear()

# ==========================================
#           ДОБАВЛЕНИЕ КОНТРАКТА
# ==========================================
@dict_router.message(Command("add_contract"))
@dict_router.message(F.text == "📜 Добавить контракт")
async def start_add_contract(message: Message, state: FSMContext, session, user_role: str):
    if user_role not in ['admin', 'declarant']: return
    await state.clear()
    # СТРОГИЙ ФИЛЬТР: Ищем только Отправителей
    stmt = select(Company).where(Company.company_type == 'sender')
    companies = (await session.scalars(stmt)).all()

    if not companies:
        await message.answer("⚠️ В базе нет Отправителей! Сначала добавьте их через /add_company")
        return

    # Выводим Inline-кнопки
    builder = []
    for comp in companies:
        builder.append([
            InlineKeyboardButton(
                text=f"📤 {comp.name}",
                callback_data=AddContractCompCb(company_id=comp.id).pack()
            )
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=builder)

    await message.answer(
        "📜 **Добавление нового контракта**\n\n"
        "Выберите **Отправителя**, к которому будет привязан контракт:",
        reply_markup=kb
    )
    await state.set_state(AddContractStates.company_id)

# 1. Ловим нажатие на компанию -> Спрашиваем номер
@dict_router.callback_query(AddContractStates.company_id, AddContractCompCb.filter())
async def process_contract_company(call: CallbackQuery, callback_data: AddContractCompCb, state: FSMContext):
    await state.update_data(company_id=callback_data.company_id)

    await call.message.edit_text("📝 Введите **Номер контракта**:")
    await state.set_state(AddContractStates.number)
    await call.answer()


# 2. Ловим номер -> Спрашиваем дату
@dict_router.message(AddContractStates.number)
async def process_contract_number(message: Message, state: FSMContext):
    await state.update_data(number=message.text.strip())
    await message.answer("📅 Введите **Дату контракта** в формате ДД.ММ.ГГГГ (например: `01.06.2026`):")
    await state.set_state(AddContractStates.date)


# 3. Ловим дату -> Спрашиваем Incoterms
@dict_router.message(AddContractStates.date)
async def process_contract_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        try:
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ:")
        return

    await state.update_data(date=parsed_date)
    await message.answer("Укажите **Условия поставки (Incoterms)** (например: `CIP`, `DAP`, `EXW`):")
    await state.set_state(AddContractStates.incoterms)


# 4. Ловим Incoterms -> Спрашиваем место
@dict_router.message(AddContractStates.incoterms)
async def process_contract_incoterms(message: Message, state: FSMContext):
    await state.update_data(incoterms=message.text.strip().upper())
    await message.answer("📍 Укажите **Место назначения (Incoterms Place)** (например: `Tashkent`):")
    await state.set_state(AddContractStates.place)


# 5. Ловим место -> Спрашиваем валюту
@dict_router.message(AddContractStates.place)
async def process_contract_place(message: Message, state: FSMContext):
    await state.update_data(place=message.text.strip())
    await message.answer("💵 Укажите **Валюту контракта** (например: `USD`, `EUR`, `RUB`):")
    await state.set_state(AddContractStates.currency)


# 6. Финал: Сохраняем в базу
@dict_router.message(AddContractStates.currency)
async def process_contract_currency(message: Message, state: FSMContext, session, user_db_id: int):
    data = await state.get_data()
    currency = message.text.strip().upper()

    new_contract = Contract(
        contract_number=data['number'],
        contract_date=data['date'],
        contract_type_code="02",
        incoterms=data['incoterms'],
        incoterms_place=data['place'],
        currency=currency,
        company_id=data['company_id'],  # <--- Сохраняем привязку к компании!
        created_by=user_db_id
    )
    session.add(new_contract)
    await session.commit()

    await message.answer(f"✅ Контракт № **{data['number']}** успешно привязан к Отправителю и сохранен!")
    await state.clear()