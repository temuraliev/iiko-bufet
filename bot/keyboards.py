"""Inline keyboards for the bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def warehouse_keyboard(stores: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура выбора склада."""
    buttons = []
    for s in stores[:10]:  # макс 10 складов
        name = (s.get("name") or s.get("id", "")[:8])[:30]
        buttons.append([InlineKeyboardButton(name, callback_data=f"warehouse:{s['id']}")])
    return InlineKeyboardMarkup(buttons)


def products_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения списка товаров (перед вводом даты)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_products"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_supply"),
        ],
        [InlineKeyboardButton("✏️ Исправить товар", callback_data="edit_item")],
    ])


def confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура итогового подтверждения поставки."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_supply"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_supply"),
        ],
        [InlineKeyboardButton("✏️ Исправить товар", callback_data="edit_item")],
    ])


def product_pick_keyboard(matches: list[dict], product_index: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора товара из результатов поиска iiko."""
    buttons = []
    for m in matches[:10]:
        name = (m.get("name") or "?")[:40]
        prod_id = m.get("id", "")
        buttons.append([InlineKeyboardButton(name, callback_data=f"pick_product:{product_index}:{prod_id}")])
    buttons.append([InlineKeyboardButton("➕ Создать новый товар в iiko", callback_data=f"inline_create:{product_index}")])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit")])
    return InlineKeyboardMarkup(buttons)


def fix_product_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура при ошибке «товар не найден» — вернуться и исправить."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Исправить сопоставление", callback_data="edit_item")],
    ])


def document_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа документа после /upload."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Счёт-фактура", callback_data="doc_type:invoice")],
        [InlineKeyboardButton("📋 Договор", callback_data="doc_type:contract")],
        [InlineKeyboardButton("📊 Эксель", callback_data="doc_type:excel")],
    ])


def unit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора единицы измерения для нового товара."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("кг", callback_data="add_unit:кг"),
            InlineKeyboardButton("шт", callback_data="add_unit:шт"),
            InlineKeyboardButton("л", callback_data="add_unit:л"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")],
    ])


def group_keyboard(groups: list[dict], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    """Клавиатура выбора группы (категории) для нового товара с пагинацией."""
    start = page * page_size
    end = start + page_size
    page_groups = groups[start:end]
    buttons = []
    for g in page_groups:
        label = (g.get("name") or "?")[:40]
        buttons.append([InlineKeyboardButton(label, callback_data=f"add_group:{g['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"add_groups_page:{page - 1}"))
    if end < len(groups):
        nav.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"add_groups_page:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="add_cancel")])
    return InlineKeyboardMarkup(buttons)


def add_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания нового товара."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Создать", callback_data="add_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="add_cancel"),
        ],
    ])


def inline_unit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура ед. изм. при создании товара из поставки."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("кг", callback_data="inline_unit:кг"),
            InlineKeyboardButton("шт", callback_data="inline_unit:шт"),
            InlineKeyboardButton("л", callback_data="inline_unit:л"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="inline_cancel")],
    ])


def inline_group_keyboard(groups: list[dict], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    """Клавиатура групп при создании товара из поставки (с пагинацией)."""
    start = page * page_size
    end = start + page_size
    page_groups = groups[start:end]
    buttons = []
    for g in page_groups:
        label = (g.get("name") or "?")[:40]
        buttons.append([InlineKeyboardButton(label, callback_data=f"inline_group:{g['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"inline_groups_page:{page - 1}"))
    if end < len(groups):
        nav.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"inline_groups_page:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="inline_cancel")])
    return InlineKeyboardMarkup(buttons)


def inline_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания товара из поставки."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Создать", callback_data="inline_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="inline_cancel"),
        ],
    ])


def edit_item_keyboard(product_index: int) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования конкретного товара."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✏️ Исправить товар #{product_index}", callback_data=f"edit_item:{product_index}")],
    ])
