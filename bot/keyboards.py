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
    ])


def edit_item_keyboard(product_index: int) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования конкретного товара."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✏️ Исправить товар #{product_index}", callback_data=f"edit_item:{product_index}")],
    ])
