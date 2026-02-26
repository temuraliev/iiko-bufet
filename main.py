"""Main entry point for iiko invoice Telegram bot."""
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    TypeHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USERNAMES
from bot.handlers.document import (
    handle_document,
    handle_upload,
    handle_document_type_choice,
    handle_extra_input,
    handle_warehouse_selection,
    handle_confirm_products,
    handle_edit_product,
    handle_pick_product,
    handle_cancel_edit,
)
from bot.handlers.confirm import handle_confirm_supply, handle_cancel_supply
from bot.handlers.iiko_status import handle_iiko_status, handle_iiko_orgs
from bot.handlers.add_product import (
    handle_add_command,
    handle_add_unit_choice,
    handle_add_groups_page,
    handle_add_group_choice,
    handle_add_confirm,
    handle_add_cancel,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def auth_check(update: Update, context) -> None:
    """Проверка доступа: пропускает только разрешённых пользователей."""
    user = update.effective_user
    if user and (user.username or "").lower() in ALLOWED_USERNAMES:
        return
    if update.message:
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
    elif update.callback_query:
        await update.callback_query.answer("⛔ Нет доступа.", show_alert=True)
    raise ApplicationHandlerStop()


async def start(update: Update, context) -> None:
    """Команда /start."""
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Я бот для обработки счетов-фактур, договоров и Excel.\n\n"
        "Команда /upload — выбрать тип документа и загрузить PDF/Excel.\n"
        "• Извлеку товары из документа\n"
        "• Найду их в вашей базе iiko\n"
        "• Добавлю поставку после подтверждения\n\n"
        "Команда /add — добавить новый товар в номенклатуру iiko.\n"
        "Команда /iiko — проверка подключения и номенклатура."
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан! Создайте .env файл с токеном.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(TypeHandler(Update, auth_check), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", handle_upload))
    app.add_handler(CommandHandler("add", handle_add_command))
    app.add_handler(CommandHandler("iiko", handle_iiko_status))
    app.add_handler(CommandHandler("iiko_orgs", handle_iiko_orgs))
    app.add_handler(MessageHandler(
        filters.Document.PDF | filters.Document.MimeType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        handle_document,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_extra_input))
    app.add_handler(CallbackQueryHandler(handle_document_type_choice, pattern="^doc_type:"))
    app.add_handler(CallbackQueryHandler(handle_warehouse_selection, pattern="^warehouse:"))
    app.add_handler(CallbackQueryHandler(handle_confirm_supply, pattern="^confirm_supply$"))
    app.add_handler(CallbackQueryHandler(handle_confirm_products, pattern="^confirm_products$"))
    app.add_handler(CallbackQueryHandler(handle_cancel_supply, pattern="^cancel_supply$"))
    app.add_handler(CallbackQueryHandler(handle_edit_product, pattern="^edit_item$"))
    app.add_handler(CallbackQueryHandler(handle_pick_product, pattern="^pick_product:"))
    app.add_handler(CallbackQueryHandler(handle_cancel_edit, pattern="^cancel_edit$"))
    app.add_handler(CallbackQueryHandler(handle_add_unit_choice, pattern="^add_unit:"))
    app.add_handler(CallbackQueryHandler(handle_add_group_choice, pattern="^add_group:"))
    app.add_handler(CallbackQueryHandler(handle_add_groups_page, pattern="^add_groups_page:"))
    app.add_handler(CallbackQueryHandler(handle_add_confirm, pattern="^add_confirm$"))
    app.add_handler(CallbackQueryHandler(handle_add_cancel, pattern="^add_cancel$"))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
