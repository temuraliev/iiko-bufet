"""Handler for /add command — creating a new product in iiko nomenclature."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.services.iiko_client import IikoClient
from bot.keyboards import (
    unit_keyboard, group_keyboard, add_confirm_keyboard,
    inline_unit_keyboard, inline_group_keyboard, inline_confirm_keyboard,
)

logger = logging.getLogger(__name__)

ADD_STEP_NAME = "add_name"
ADD_STEP_UNIT = "add_unit"
ADD_STEP_GROUP = "add_group"
ADD_STEP_CONFIRM = "add_confirm"


def _clear_add_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "pending_step", "add_product_name", "add_product_unit",
        "add_product_group_id", "add_product_group_name", "add_groups_cache",
    ):
        context.user_data.pop(key, None)


async def handle_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add — начало создания нового товара."""
    _clear_add_state(context)
    context.user_data["pending_step"] = ADD_STEP_NAME
    await update.message.reply_text("📦 Введите название нового товара:")


async def handle_add_name_input(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обработка ввода названия товара. Возвращает True если обработано."""
    step = context.user_data.get("pending_step")
    if step != ADD_STEP_NAME:
        return False

    name = text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Слишком короткое название. Введите снова:")
        return True
    if len(name) > 150:
        await update.message.reply_text("❌ Слишком длинное название (макс. 150 символов). Введите снова:")
        return True

    context.user_data["add_product_name"] = name
    context.user_data["pending_step"] = ADD_STEP_UNIT
    await update.message.reply_text(
        f"📦 Товар: <b>{name}</b>\n\nВыберите единицу измерения:",
        reply_markup=unit_keyboard(),
        parse_mode="HTML",
    )
    return True


async def handle_add_unit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор единицы измерения."""
    query = update.callback_query
    if not query or not query.data:
        return
    unit = query.data.replace("add_unit:", "").strip()
    if unit not in ("кг", "шт", "л"):
        await query.answer("Неизвестная единица.", show_alert=True)
        return

    context.user_data["add_product_unit"] = unit
    context.user_data["pending_step"] = ADD_STEP_GROUP
    await query.answer()

    await query.edit_message_text("⏳ Загружаю список групп из iiko...")

    try:
        iiko = IikoClient()
        groups = await iiko.get_product_groups()
    except Exception as e:
        logger.exception("Failed to load groups")
        await query.edit_message_text(f"❌ Ошибка загрузки групп: {e}")
        _clear_add_state(context)
        return

    if not groups:
        await query.edit_message_text("❌ Не найдено ни одной группы товаров в iiko.")
        _clear_add_state(context)
        return

    context.user_data["add_groups_cache"] = groups
    name = context.user_data.get("add_product_name", "?")
    await query.edit_message_text(
        f"📦 Товар: <b>{name}</b> | Ед: <b>{unit}</b>\n\nВыберите группу (категорию):",
        reply_markup=group_keyboard(groups, page=0),
        parse_mode="HTML",
    )


async def handle_add_groups_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пагинация списка групп."""
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        page = int(query.data.replace("add_groups_page:", ""))
    except ValueError:
        return
    groups = context.user_data.get("add_groups_cache", [])
    if not groups:
        await query.answer("Нет данных.", show_alert=True)
        return
    await query.answer()
    name = context.user_data.get("add_product_name", "?")
    unit = context.user_data.get("add_product_unit", "?")
    await query.edit_message_text(
        f"📦 Товар: <b>{name}</b> | Ед: <b>{unit}</b>\n\nВыберите группу (категорию):",
        reply_markup=group_keyboard(groups, page=page),
        parse_mode="HTML",
    )


async def handle_add_group_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор группы для нового товара."""
    query = update.callback_query
    if not query or not query.data:
        return
    group_id = query.data.replace("add_group:", "").strip()
    groups = context.user_data.get("add_groups_cache", [])
    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        await query.answer("Группа не найдена.", show_alert=True)
        return

    context.user_data["add_product_group_id"] = group_id
    context.user_data["add_product_group_name"] = group["name"]
    context.user_data["pending_step"] = ADD_STEP_CONFIRM
    await query.answer()

    name = context.user_data.get("add_product_name", "?")
    unit = context.user_data.get("add_product_unit", "?")
    await query.edit_message_text(
        f"📦 Создать новый товар?\n\n"
        f"Название: <b>{name}</b>\n"
        f"Ед. изм.: <b>{unit}</b>\n"
        f"Группа: <b>{group['name']}</b>",
        reply_markup=add_confirm_keyboard(),
        parse_mode="HTML",
    )


async def handle_add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждение создания товара."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    name = context.user_data.get("add_product_name")
    unit = context.user_data.get("add_product_unit", "кг")
    group_id = context.user_data.get("add_product_group_id")
    group_name = context.user_data.get("add_product_group_name", "?")

    if not name or not group_id:
        await query.edit_message_text("❌ Данные потеряны. Начните заново: /add")
        _clear_add_state(context)
        return

    await query.edit_message_text("⏳ Создаю товар в iiko...")

    try:
        iiko = IikoClient()
        result = await iiko.create_product(
            name,
            parent_id=group_id,
            main_unit=unit,
        )
        _clear_add_state(context)
        await query.edit_message_text(
            f"✅ Товар создан в iiko!\n\n"
            f"Название: <b>{name}</b>\n"
            f"Ед. изм.: <b>{unit}</b>\n"
            f"Группа: <b>{group_name}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Product creation error")
        _clear_add_state(context)
        await query.edit_message_text(f"❌ Ошибка при создании товара: {e}")


async def handle_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмена создания товара."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _clear_add_state(context)
    await query.edit_message_text("❌ Создание товара отменено.")


# ---------------------------------------------------------------------------
#  Inline creation — создание товара прямо во время оформления поставки
# ---------------------------------------------------------------------------

def _clear_inline_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "inline_product_index", "inline_product_name", "inline_product_unit",
        "inline_group_id", "inline_group_name", "inline_groups_cache",
    ):
        context.user_data.pop(key, None)


async def _return_to_supply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возврат к экрану подтверждения товаров поставки."""
    from bot.handlers.document import _show_products_confirmation, _show_final_confirmation
    _clear_inline_state(context)
    context.user_data.pop("editing_product_index", None)
    context.user_data.pop("edit_search_matches", None)
    context.user_data.pop("pending_step", None)
    if context.user_data.get("pending_date"):
        await _show_final_confirmation(update, context, edit_message=True)
    else:
        await _show_products_confirmation(update, context, edit_message=True)


async def handle_inline_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начало создания товара из flow поставки."""
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        idx = int(query.data.replace("inline_create:", ""))
    except ValueError:
        return
    products = context.user_data.get("pending_products", [])
    if idx < 1 or idx > len(products):
        await query.answer("Неверный номер товара.", show_alert=True)
        return

    pdf_name = products[idx - 1].get("name", "Новый товар")
    context.user_data["inline_product_index"] = idx
    context.user_data["inline_product_name"] = pdf_name
    await query.answer()
    await query.edit_message_text(
        f"➕ Создание товара: <b>{pdf_name}</b>\n\nВыберите единицу измерения:",
        reply_markup=inline_unit_keyboard(),
        parse_mode="HTML",
    )


async def handle_inline_unit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор единицы измерения (inline)."""
    query = update.callback_query
    if not query or not query.data:
        return
    unit = query.data.replace("inline_unit:", "").strip()
    if unit not in ("кг", "шт", "л"):
        await query.answer("Неизвестная единица.", show_alert=True)
        return

    context.user_data["inline_product_unit"] = unit
    await query.answer()
    await query.edit_message_text("⏳ Загружаю список групп из iiko...")

    try:
        iiko = IikoClient()
        groups = await iiko.get_product_groups()
    except Exception as e:
        logger.exception("Failed to load groups (inline)")
        await query.edit_message_text(f"❌ Ошибка загрузки групп: {e}")
        _clear_inline_state(context)
        return

    if not groups:
        await query.edit_message_text("❌ Не найдено ни одной группы товаров.")
        _clear_inline_state(context)
        return

    context.user_data["inline_groups_cache"] = groups
    name = context.user_data.get("inline_product_name", "?")
    await query.edit_message_text(
        f"➕ Товар: <b>{name}</b> | Ед: <b>{unit}</b>\n\nВыберите группу:",
        reply_markup=inline_group_keyboard(groups, page=0),
        parse_mode="HTML",
    )


async def handle_inline_groups_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пагинация групп (inline)."""
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        page = int(query.data.replace("inline_groups_page:", ""))
    except ValueError:
        return
    groups = context.user_data.get("inline_groups_cache", [])
    if not groups:
        await query.answer("Нет данных.", show_alert=True)
        return
    await query.answer()
    name = context.user_data.get("inline_product_name", "?")
    unit = context.user_data.get("inline_product_unit", "?")
    await query.edit_message_text(
        f"➕ Товар: <b>{name}</b> | Ед: <b>{unit}</b>\n\nВыберите группу:",
        reply_markup=inline_group_keyboard(groups, page=page),
        parse_mode="HTML",
    )


async def handle_inline_group_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор группы (inline)."""
    query = update.callback_query
    if not query or not query.data:
        return
    group_id = query.data.replace("inline_group:", "").strip()
    groups = context.user_data.get("inline_groups_cache", [])
    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        await query.answer("Группа не найдена.", show_alert=True)
        return

    context.user_data["inline_group_id"] = group_id
    context.user_data["inline_group_name"] = group["name"]
    await query.answer()

    name = context.user_data.get("inline_product_name", "?")
    unit = context.user_data.get("inline_product_unit", "?")
    await query.edit_message_text(
        f"➕ Создать товар в iiko?\n\n"
        f"Название: <b>{name}</b>\n"
        f"Ед. изм.: <b>{unit}</b>\n"
        f"Группа: <b>{group['name']}</b>",
        reply_markup=inline_confirm_keyboard(),
        parse_mode="HTML",
    )


async def handle_inline_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждение создания товара (inline) и возврат к поставке."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    name = context.user_data.get("inline_product_name")
    unit = context.user_data.get("inline_product_unit", "кг")
    group_id = context.user_data.get("inline_group_id")
    group_name = context.user_data.get("inline_group_name", "?")
    idx = context.user_data.get("inline_product_index")

    if not name or not group_id or not idx:
        await query.edit_message_text("❌ Данные потеряны. Попробуйте снова.")
        _clear_inline_state(context)
        return

    await query.edit_message_text("⏳ Создаю товар в iiko...")

    try:
        iiko = IikoClient()
        await iiko.create_product(name, parent_id=group_id, main_unit=unit)

        products = await iiko.get_products()
        created = next((p for p in products if p["name"].lower() == name.lower()), None)

        if created:
            iiko_matches = context.user_data.get("pending_iiko_matches", {})
            iiko_matches[idx] = {
                "id": created["id"],
                "name": created["name"],
                "productCode": created.get("productCode") or created.get("number", ""),
                "number": created.get("productCode") or created.get("number", ""),
            }
            context.user_data["pending_iiko_matches"] = iiko_matches

        await query.edit_message_text(
            f"✅ Товар <b>{name}</b> создан в iiko (группа: {group_name}).\n"
            f"Возвращаю к списку поставки...",
            parse_mode="HTML",
        )
        await _return_to_supply(update, context)

    except Exception as e:
        logger.exception("Inline product creation error")
        _clear_inline_state(context)
        await query.edit_message_text(f"❌ Ошибка при создании товара: {e}")


async def handle_inline_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмена inline-создания — возврат к поставке."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("❌ Создание товара отменено. Возвращаю к списку...")
    await _return_to_supply(update, context)
