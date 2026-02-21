"""Document (PDF) handlers and multi-step flow (date, comment, warehouse)."""
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.services.pdf_parser import parse_invoice_pdf
from bot.services.iiko_client import IikoClient
from bot.services.product_mappings import get_mapping, remove_mapping
from bot.keyboards import (
    confirmation_keyboard,
    products_confirmation_keyboard,
    warehouse_keyboard,
    product_pick_keyboard,
)
from config import TEMP_DIR, IIKO_DEFAULT_STORE_ID

logger = logging.getLogger(__name__)

# Лимит Telegram — 4096 символов
_MAX_MESSAGE_LENGTH = 4000


def _split_message(text: str, max_len: int = _MAX_MESSAGE_LENGTH) -> list[str]:
    """Разбивает длинное сообщение на части по max_len символов (по границам строк)."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    rest = text
    while len(rest) > max_len:
        part = rest[: max_len + 1]
        idx = part.rfind("\n")
        if idx == -1:
            idx = max_len
        chunks.append(rest[:idx].rstrip())
        rest = rest[idx:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks


async def _send_long_message(
    bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    message_id_to_delete: int | None = None,
) -> list[int]:
    """
    Отправляет сообщение, разбивая на части при необходимости.
    Последняя часть получает reply_markup.
    Если message_id_to_delete задан — удаляет это сообщение перед отправкой.
    Возвращает список message_id отправленных сообщений.
    """
    if message_id_to_delete is not None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id_to_delete)
        except Exception:
            pass

    chunks = _split_message(text)
    message_ids = []
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        mk = reply_markup if is_last else None
        msg = await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            reply_markup=mk,
        )
        message_ids.append(msg.message_id)
    return message_ids


# Шаги ввода данных после PDF
PENDING_STEP_PRODUCTS = "products"  # ожидание подтверждения списка товаров
PENDING_STEP_DATE = "date"
PENDING_STEP_COMMENT = "comment"
PENDING_STEP_WAREHOUSE = "warehouse"
PENDING_STEP_EDIT_NUMBER = "edit_product_number"
PENDING_STEP_EDIT_SEARCH = "edit_product_search"


def format_confirmation_message(
    products: list[dict],
    iiko_matches: dict,
    supplier_from_pdf: str | None = None,
    supplier_matched: dict | None = None,
) -> str:
    """Формирует сообщение для проверки пользователем."""
    lines = ["📋 Распознанные товары (проверьте и нажмите Подтвердить или Отмена):\n"]

    if supplier_from_pdf:
        if supplier_matched:
            lines.append(f"🏢 Поставщик: {supplier_from_pdf} → {supplier_matched.get('name', '?')} ✓\n")
        else:
            lines.append(f"🏢 Поставщик из PDF: {supplier_from_pdf} (не найден в iiko, будет использован из .env)\n")

    for i, p in enumerate(products, 1):
        iiko_info = iiko_matches.get(i, {})
        if iiko_info:
            name_iiko = iiko_info.get("name", "❓ Не найден")
            code_iiko = iiko_info.get("productCode") or iiko_info.get("number", "-")
        else:
            name_iiko = "❓ Не найден в iiko"
            code_iiko = "-"

        lines.append(f"{i}. {p['name']}")
        lines.append(f"   Ед: {p['unit']} | Кол-во: {p['quantity']} | Цена с НДС: {p['price_with_vat']:,.2f}")
        lines.append(f"   В iiko: {name_iiko} (код: {code_iiko})")
        lines.append("")

    return "\n".join(lines)


def _parse_date_input(text: str) -> str | None:
    """
    Парсит дату/время из ввода пользователя.
    Возвращает строку в формате YYYY-MM-DDTHH:MM или None.
    """
    text = (text or "").strip()
    if not text:
        return None
    formats = [
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text[:20], fmt)
            return dt.strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue
    return None


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка полученного PDF документа."""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате PDF.")
        return

    await update.message.reply_text("⏳ Обрабатываю PDF...")

    try:
        file = await context.bot.get_file(doc.file_id)
        temp_path = TEMP_DIR / f"{update.effective_user.id}_{doc.file_id}.pdf"
        await file.download_to_drive(temp_path)

        parsed = parse_invoice_pdf(temp_path)
        temp_path.unlink(missing_ok=True)

        products = parsed.get("products", [])
        supplier_from_pdf = parsed.get("supplier_name")

        if not products:
            await update.message.reply_text("❌ Не удалось извлечь товары из PDF. Проверьте формат файла.")
            return

        # Поиск товаров и поставщика в iiko (с учётом сохранённых сопоставлений)
        iiko = IikoClient()
        all_products = await iiko.get_products()
        valid_ids = {p["id"] for p in all_products}

        iiko_matches: dict[int, dict] = {}
        for i, p in enumerate(products, 1):
            pdf_name = (p.get("name") or "").strip()
            saved = get_mapping(pdf_name)
            if saved and saved.get("id") and saved["id"] in valid_ids:
                iiko_matches[i] = {
                    "id": saved["id"],
                    "name": saved.get("name", ""),
                    "productCode": saved.get("productCode") or saved.get("number", ""),
                    "number": saved.get("productCode") or saved.get("number", ""),
                }
            else:
                if saved and saved.get("id") and saved["id"] not in valid_ids:
                    remove_mapping(pdf_name)
                matches = await iiko.search_product(pdf_name)
                if matches:
                    iiko_matches[i] = matches[0]
                else:
                    iiko_matches[i] = {}

        supplier_matched = None
        if supplier_from_pdf:
            suppliers = await iiko.get_suppliers()
            supplier_matched = iiko.match_supplier(supplier_from_pdf, suppliers)

        # Сохраняем в context для многошагового ввода
        context.user_data["pending_products"] = products
        context.user_data["pending_iiko_matches"] = iiko_matches
        context.user_data["pending_file_name"] = doc.file_name
        context.user_data["pending_supplier_id"] = supplier_matched["id"] if supplier_matched else None
        context.user_data["pending_supplier_name"] = supplier_from_pdf
        context.user_data["pending_supplier_matched"] = supplier_matched
        context.user_data["pending_step"] = PENDING_STEP_PRODUCTS

        text = format_confirmation_message(
            products, iiko_matches,
            supplier_from_pdf=supplier_from_pdf,
            supplier_matched=supplier_matched,
        )
        text += "\n\nПодтвердите список товаров и нажмите «Подтвердить» для продолжения."
        msg_ids = await _send_long_message(
            context.bot,
            update.effective_chat.id,
            text,
            reply_markup=products_confirmation_keyboard(),
        )
        context.user_data["pending_message_ids"] = msg_ids

    except FileNotFoundError as e:
        logger.exception("PDF file error")
        await update.message.reply_text(f"❌ Ошибка файла: {e}")
    except Exception as e:
        logger.exception("PDF processing error")
        await update.message.reply_text(f"❌ Ошибка при обработке: {str(e)}")


async def handle_extra_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода даты, комментария (многошаговый flow после PDF)."""
    if not update.message or not update.message.text:
        return
    step = context.user_data.get("pending_step")
    if not step:
        return

    text = (update.message.text or "").strip()

    if step == PENDING_STEP_EDIT_NUMBER:
        try:
            idx = int(text)
        except ValueError:
            idx = 0
        products = context.user_data.get("pending_products", [])
        n = len(products)
        if idx < 1 or idx > n:
            await update.message.reply_text(f"❌ Введите номер товара от 1 до {n}:")
            return
        context.user_data["editing_product_index"] = idx
        context.user_data["pending_step"] = PENDING_STEP_EDIT_SEARCH
        p = products[idx - 1]
        await update.message.reply_text(
            f"🔍 Введите поисковый запрос для товара {idx} («{p.get('name', '?')}»):"
        )
        return

    if step == PENDING_STEP_EDIT_SEARCH:
        idx = context.user_data.get("editing_product_index")
        if not idx:
            context.user_data.pop("pending_step", None)
            return
        if text.lower() in ("отмена", "cancel", "назад"):
            context.user_data.pop("editing_product_index", None)
            context.user_data.pop("edit_search_matches", None)
            context.user_data.pop("pending_step", None)
            if context.user_data.get("pending_date"):
                await _show_final_confirmation(update, context)
            else:
                await _show_products_confirmation(update, context)
            return
        iiko = IikoClient()
        matches = await iiko.search_product(text, limit=10)
        if not matches:
            await update.message.reply_text(
                "❌ Ничего не найдено. Введите другой поисковый запрос или «отмена» для выхода:"
            )
            return
        context.user_data["edit_search_matches"] = matches
        await update.message.reply_text(
            f"Выберите товар для позиции {idx}:",
            reply_markup=product_pick_keyboard(matches, idx),
        )
        return

    if step == PENDING_STEP_DATE:
        date_str = _parse_date_input(text)
        if not date_str:
            await update.message.reply_text(
                "❌ Неверный формат даты. Введите, например: 11.02.2026 14:30 или 11.02.2026"
            )
            return
        context.user_data["pending_date"] = date_str
        context.user_data["pending_step"] = PENDING_STEP_COMMENT
        await update.message.reply_text(
            "📝 Шаг 2/3. Введите комментарий к поставке (или «пропустить» для пропуска):"
        )
        return

    if step == PENDING_STEP_COMMENT:
        if text.lower() in ("пропустить", "пропуск", "-", "нет", "skip"):
            text = ""
        context.user_data["pending_comment"] = text[:500]
        context.user_data["pending_step"] = PENDING_STEP_WAREHOUSE

        iiko = IikoClient()
        stores = await iiko.get_stores()
        if not stores:
            context.user_data["pending_store_id"] = IIKO_DEFAULT_STORE_ID or None
            context.user_data["pending_store_name"] = "по умолчанию"
            context.user_data.pop("pending_step", None)
            await _show_final_confirmation(update, context)
            return

        await update.message.reply_text(
            "🏭 Шаг 3/3. Выберите склад для поставки:",
            reply_markup=warehouse_keyboard(stores),
        )
        context.user_data["pending_stores"] = stores
        return


def _format_products_message(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Формирует сообщение со списком товаров для подтверждения."""
    products = context.user_data.get("pending_products", [])
    iiko_matches = context.user_data.get("pending_iiko_matches", {})
    supplier_from_pdf = context.user_data.get("pending_supplier_name")
    supplier_matched = context.user_data.get("pending_supplier_matched")
    return format_confirmation_message(
        products, iiko_matches,
        supplier_from_pdf=supplier_from_pdf,
        supplier_matched=supplier_matched,
    )


async def _show_products_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit_message: bool = False
) -> None:
    """Показывает список товаров с кнопками подтверждения."""
    text = _format_products_message(context)
    text += "\n\nПодтвердите список товаров и нажмите «Подтвердить» для продолжения."
    chat_id = update.effective_chat.id
    bot = context.bot
    if edit_message and update.callback_query:
        msg_ids_to_del = context.user_data.get("pending_message_ids", [])
        for mid in msg_ids_to_del:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass
        context.user_data.pop("pending_message_ids", None)
        msg_ids = await _send_long_message(
            bot, chat_id, text,
            reply_markup=products_confirmation_keyboard(),
        )
        context.user_data["pending_message_ids"] = msg_ids
        await update.callback_query.answer()
    else:
        msg_ids = await _send_long_message(
            bot, chat_id, text,
            reply_markup=products_confirmation_keyboard(),
        )
        context.user_data["pending_message_ids"] = msg_ids


async def handle_confirm_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждение списка товаров — переход к вводу даты."""
    query = update.callback_query
    if not query or query.data != "confirm_products":
        return
    await query.answer()
    # Если уже введена дата — это итоговый экран, показываем его с правильной клавиатурой
    if context.user_data.get("pending_date"):
        await _show_final_confirmation(update, context, edit_message=True)
        return
    context.user_data["pending_step"] = PENDING_STEP_DATE
    chat_id = update.effective_chat.id
    for mid in context.user_data.get("pending_message_ids", []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    context.user_data.pop("pending_message_ids", None)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "📅 Шаг 1/3. Введите дату и время получения товара.\n"
            "Формат: ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ\n"
            "Например: 11.02.2026 14:30"
        ),
    )


async def handle_warehouse_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора склада."""
    query = update.callback_query
    if not query:
        return
    if not query.data or not query.data.startswith("warehouse:"):
        return

    store_id = query.data.replace("warehouse:", "").strip()
    stores = context.user_data.get("pending_stores", [])
    store_name = next((s.get("name") or s["id"][:8] for s in stores if s["id"] == store_id), store_id[:8])

    context.user_data["pending_store_id"] = store_id
    context.user_data["pending_store_name"] = store_name
    context.user_data.pop("pending_stores", None)
    context.user_data.pop("pending_step", None)

    await query.answer()
    await _show_final_confirmation(update, context, edit_message=True)


async def handle_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начало исправления товара: запрос номера позиции."""
    query = update.callback_query
    if not query or query.data != "edit_item":
        return
    products = context.user_data.get("pending_products", [])
    if not products:
        await query.answer("Нет данных для редактирования.", show_alert=True)
        return
    await query.answer()
    context.user_data["pending_step"] = PENDING_STEP_EDIT_NUMBER
    n = len(products)
    chat_id = update.effective_chat.id
    for mid in context.user_data.get("pending_message_ids", []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    context.user_data.pop("pending_message_ids", None)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✏️ Введите номер товара для исправления (1–{n}):",
    )


async def handle_pick_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор товара из результатов поиска для замены сопоставления."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("pick_product:"):
        return
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    try:
        product_index = int(parts[1])
        product_id = parts[2]
    except ValueError:
        return
    iiko_matches = context.user_data.get("pending_iiko_matches", {})
    products = context.user_data.get("pending_products", [])
    if product_index < 1 or product_index > len(products):
        await query.answer("Ошибка: неверный номер товара.", show_alert=True)
        return
    matches = context.user_data.get("edit_search_matches", [])
    chosen = next((p for p in matches if p.get("id") == product_id), None)
    if not chosen:
        await query.answer("Товар не найден.", show_alert=True)
        return
    iiko_matches[product_index] = {
        "id": chosen["id"],
        "name": chosen.get("name", "?"),
        "productCode": chosen.get("productCode") or chosen.get("number", ""),
        "number": chosen.get("productCode") or chosen.get("number", ""),
    }
    context.user_data["pending_iiko_matches"] = iiko_matches
    context.user_data.pop("editing_product_index", None)
    context.user_data.pop("edit_search_matches", None)
    context.user_data.pop("pending_step", None)
    await query.answer("✓ Товар обновлён")
    if context.user_data.get("pending_date"):
        await _show_final_confirmation(update, context, edit_message=True)
    else:
        await _show_products_confirmation(update, context, edit_message=True)


async def handle_cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмена режима исправления товара."""
    query = update.callback_query
    if not query or query.data != "cancel_edit":
        return
    context.user_data.pop("editing_product_index", None)
    context.user_data.pop("edit_search_matches", None)
    context.user_data.pop("pending_step", None)
    await query.answer()
    if context.user_data.get("pending_date"):
        await _show_final_confirmation(update, context, edit_message=True)
    else:
        await _show_products_confirmation(update, context, edit_message=True)


def _format_final_message(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Формирует итоговое сообщение с товарами и введёнными данными."""
    products = context.user_data.get("pending_products", [])
    iiko_matches = context.user_data.get("pending_iiko_matches", {})
    date_str = context.user_data.get("pending_date", "")
    comment = context.user_data.get("pending_comment", "")
    store_name = context.user_data.get("pending_store_name", "")

    lines = ["📋 Итоговая проверка. Нажмите Подтвердить или Отмена:\n"]
    date_display = date_str.replace("T", " ") if date_str else "—"
    lines.append(f"📅 Дата получения: {date_display}")
    lines.append(f"📝 Комментарий: {comment or '(нет)'}")
    lines.append(f"🏭 Склад: {store_name}\n")

    for i, p in enumerate(products, 1):
        iiko_info = iiko_matches.get(i, {})
        name_iiko = iiko_info.get("name", "❓") if iiko_info else "❓"
        code_iiko = (iiko_info.get("productCode") or iiko_info.get("number") or "-") if iiko_info else "-"
        lines.append(f"{i}. {p['name']} | {p['quantity']} × {p['price_with_vat']:,.2f}")
        lines.append(f"   → {name_iiko} (код: {code_iiko})\n")

    return "\n".join(lines)


async def _show_final_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit_message: bool = False
) -> None:
    """Показывает итоговое подтверждение с кнопками."""
    text = _format_final_message(context)
    chat_id = update.effective_chat.id
    bot = context.bot
    if edit_message and update.callback_query:
        msg_ids_to_del = context.user_data.get("pending_message_ids", [])
        for mid in msg_ids_to_del:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass
        context.user_data.pop("pending_message_ids", None)
        msg_ids = await _send_long_message(
            bot, chat_id, text,
            reply_markup=confirmation_keyboard(),
        )
        context.user_data["pending_message_ids"] = msg_ids
    else:
        msg_ids = await _send_long_message(
            bot, chat_id, text,
            reply_markup=confirmation_keyboard(),
        )
        context.user_data["pending_message_ids"] = msg_ids
