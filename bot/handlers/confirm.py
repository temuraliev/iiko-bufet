"""Confirmation and callback handlers."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import IIKO_READ_ONLY, STORE_SUPPLIER_OVERRIDE
from bot.services.iiko_client import IikoClient, ProductGroupError
from bot.services.product_mappings import save_mappings
from bot.keyboards import fix_product_keyboard

logger = logging.getLogger(__name__)


async def handle_confirm_supply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка подтверждения поставки."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    products = context.user_data.get("pending_products")
    iiko_matches = context.user_data.get("pending_iiko_matches", {})

    if not products:
        await query.edit_message_text("❌ Нет данных для поставки. Отправьте PDF заново.")
        return

    if not context.user_data.get("pending_date"):
        await query.edit_message_text(
            "❌ Сначала введите дату. Нажмите «Отмена» и начните заново."
        )
        return

    if IIKO_READ_ONLY:
        context.user_data.pop("pending_products", None)
        context.user_data.pop("pending_iiko_matches", None)
        context.user_data.pop("pending_file_name", None)
        context.user_data.pop("pending_supplier_id", None)
        context.user_data.pop("pending_supplier_name", None)
        context.user_data.pop("pending_supplier_matched", None)
        context.user_data.pop("pending_date", None)
        context.user_data.pop("pending_comment", None)
        context.user_data.pop("pending_store_id", None)
        context.user_data.pop("pending_store_name", None)
        context.user_data.pop("pending_step", None)
        context.user_data.pop("editing_product_index", None)
        context.user_data.pop("edit_search_matches", None)
        await query.edit_message_text(
            "📖 Режим только чтение. Поставка не создана.\n\n"
            "Проверьте сопоставление товаров. Чтобы включить создание поставок, "
            "добавьте в .env: IIKO_READ_ONLY=false"
        )
        return

    iiko = IikoClient()
    items = []
    for i, p in enumerate(products, 1):
        match = iiko_matches.get(i, {})
        product_id = match.get("id")
        if not product_id:
            await query.edit_message_text(
                f"❌ Товар «{p['name']}» не найден в iiko. Добавьте его в номенклатуру или исправьте сопоставление.",
                reply_markup=fix_product_keyboard(),
            )
            return
        items.append({
            "productId": product_id,
            "amount": p["quantity"],
            "price": p["price_with_vat"],
            "sum": round(p["quantity"] * p["price_with_vat"], 2),
        })

    try:
        store_id = context.user_data.get("pending_store_id")
        supplier_id = (
            STORE_SUPPLIER_OVERRIDE.get(store_id or "")
            or context.user_data.get("pending_supplier_id")
        )
        date_incoming = context.user_data.get("pending_date")
        comment = context.user_data.get("pending_comment")

        result = await iiko.create_supply(
            items,
            counteragent_id=supplier_id,
            store_id=store_id or None,
            date_incoming=date_incoming,
            comment=comment,
        )
        # Сохраняем сопоставления для следующих раз
        mappings_to_save = {}
        for i, p in enumerate(products, 1):
            match = iiko_matches.get(i, {})
            if match.get("id"):
                pdf_name = (p.get("name") or "").strip()
                if pdf_name:
                    mappings_to_save[pdf_name] = {
                        "id": match["id"],
                        "name": match.get("name", ""),
                        "productCode": match.get("productCode") or match.get("number", ""),
                        "number": match.get("productCode") or match.get("number", ""),
                    }
        if mappings_to_save:
            save_mappings(mappings_to_save)

        context.user_data.pop("pending_products", None)
        context.user_data.pop("pending_iiko_matches", None)
        context.user_data.pop("pending_file_name", None)
        context.user_data.pop("pending_supplier_id", None)
        context.user_data.pop("pending_supplier_name", None)
        context.user_data.pop("pending_supplier_matched", None)
        context.user_data.pop("pending_date", None)
        context.user_data.pop("pending_comment", None)
        context.user_data.pop("pending_store_id", None)
        context.user_data.pop("pending_store_name", None)
        context.user_data.pop("pending_step", None)
        context.user_data.pop("editing_product_index", None)
        context.user_data.pop("edit_search_matches", None)
        context.user_data.pop("pending_message_ids", None)

        msg = "✅ Поставка успешно создана!"
        if result.get("documentNumber"):
            msg += f"\nНомер документа: {result['documentNumber']}"
        await query.edit_message_text(msg)
    except ProductGroupError as e:
        await query.edit_message_text(
            f"❌ {e}",
            reply_markup=fix_product_keyboard(),
        )
    except Exception as e:
        logger.exception("Supply creation error")
        await query.edit_message_text(f"❌ Ошибка при создании поставки: {str(e)}")


async def handle_cancel_supply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка отмены."""
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.pop("pending_products", None)
        context.user_data.pop("pending_iiko_matches", None)
        context.user_data.pop("pending_file_name", None)
        context.user_data.pop("pending_supplier_id", None)
        context.user_data.pop("pending_supplier_name", None)
        context.user_data.pop("pending_supplier_matched", None)
        context.user_data.pop("pending_date", None)
        context.user_data.pop("pending_comment", None)
        context.user_data.pop("pending_store_id", None)
        context.user_data.pop("pending_store_name", None)
        context.user_data.pop("pending_step", None)
        context.user_data.pop("pending_stores", None)
        context.user_data.pop("editing_product_index", None)
        context.user_data.pop("edit_search_matches", None)
        context.user_data.pop("pending_message_ids", None)
        await query.edit_message_text("❌ Поставка отменена. Отправьте новый PDF для обработки.")
