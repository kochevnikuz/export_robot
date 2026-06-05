# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .engine import Base
from sqlalchemy import Date, Float, Numeric


# 1. Таблица Пользователей (Роли и доступ)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)

    # Роль: 'admin' или 'declarant'
    role = Column(String, default='declarant', nullable=False)

    # Активен ли пользователь (админ может отключить доступ)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи (один пользователь может создать много компаний и инвойсов)
    companies = relationship("Company", back_populates="creator")
    # invoices = relationship("Invoice", back_populates="creator") # Добавим позже


# 2. Таблица Компаний (Пример, как перенести модель из Django)
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    tax_id = Column(String, nullable=True)       # <-- СДЕЛАТЬ NULLABLE
    legal_address = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    area_code = Column(String, nullable=True)     # <-- СДЕЛАТЬ NULLABLE
    company_type = Column(String, default="sender")
    cmr_13 = Column(String, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    creator = relationship("User", back_populates="companies")

# 3. Таблица Контрактов
class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    contract_number = Column(String, nullable=False)
    contract_date = Column(Date, nullable=True)
    contract_type_code = Column(String, default="02")
    incoterms = Column(String, nullable=True)
    incoterms_place = Column(String, nullable=True)
    currency = Column(String, default="USD")

    # --- НОВЫЕ ПОЛЯ ---
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False) # Привязка к компании
    company = relationship("Company") # Связь с объектом Company

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User")
    invoices = relationship("Invoice", back_populates="contract")


# 4. Таблица Инвойсов (Главный документ)
class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, nullable=False)
    invoice_date = Column(Date, nullable=True)
    status = Column(String, default="draft")  # draft, completed и т.д.

    # Внешние ключи (Связи с другими таблицами)
    company_id = Column(Integer, ForeignKey("companies.id"))  # Отправитель
    consignee_id = Column(Integer, ForeignKey("companies.id"))  # Получатель
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    created_by = Column(Integer, ForeignKey("users.id"))

    # Транспорт для CMR
    transport_number = Column(String, nullable=True)
    transport_driver = Column(String, nullable=True)
    transport_tir_carnet = Column(String, nullable=True)
    final_destination = Column(String, nullable=True)

    # Итоги
    grand_total = Column(Float, default=0.0)
    grand_total_words = Column(String, nullable=True)

    # Настройка связей (relationship)
    company = relationship("Company", foreign_keys=[company_id])
    consignee = relationship("Company", foreign_keys=[consignee_id])
    contract = relationship("Contract", back_populates="invoices")
    creator = relationship("User")

    # cascade="all, delete-orphan" значит, что при удалении инвойса, удалятся и его товары
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


# 5. Таблица Товаров (InvoiceItem)
class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    item_number = Column(Integer)

    item_name = Column(String, nullable=False)
    hs_code = Column(String, nullable=True)

    quantity = Column(Float, default=0.0)
    unit = Column(String, default="шт")
    price = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    # Упаковка
    package_quantity = Column(Integer, default=0)
    package_type = Column(String, nullable=True)
    package_code = Column(String, nullable=True)  # <--- НОВОЕ ПОЛЕ ДЛЯ КОДА УПАКОВКИ
    piece_quantity = Column(Integer, default=0)

    # Вес
    net_weight = Column(Float, default=0.0)
    gross_weight = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="items")