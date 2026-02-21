"""Main entry point for iiko invoice Telegram bot."""
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from bot.handlers.document import (
    handle_document,
    handle_extra_input,
    handle_warehouse_selection,
    handle_confirm_products,
    handle_edit_product,
    handle_pick_product,
    handle_cancel_edit,
)
from bot.handlers.confirm import handle_confirm_supply, handle_cancel_supply
from bot.handlers.iiko_status import handle_iiko_status, handle_iiko_orgs

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context) -> None:
    """Команда /start."""
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Я бот для обработки счетов-фактур.\n\n"
        "Отправьте мне PDF файл счёта-фактуры, и я:\n"
        "• Извлеку товары из документа\n"
        "• Найду их в вашей базе iiko\n"
        "• Покажу результат для проверки\n"
        "• Добавлю поставку после вашего подтверждения\n\n"
        "📎 Отправьте PDF файл для начала.\n"
        "Команда /iiko — проверка подключения и номенклатура."
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан! Создайте .env файл с токеном.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("iiko", handle_iiko_status))
    app.add_handler(CommandHandler("iiko_orgs", handle_iiko_orgs))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_extra_input))
    app.add_handler(CallbackQueryHandler(handle_warehouse_selection, pattern="^warehouse:"))
    app.add_handler(CallbackQueryHandler(handle_confirm_supply, pattern="^confirm_supply$"))
    app.add_handler(CallbackQueryHandler(handle_confirm_products, pattern="^confirm_products$"))
    app.add_handler(CallbackQueryHandler(handle_cancel_supply, pattern="^cancel_supply$"))
    app.add_handler(CallbackQueryHandler(handle_edit_product, pattern="^edit_item$"))
    app.add_handler(CallbackQueryHandler(handle_pick_product, pattern="^pick_product:"))
    app.add_handler(CallbackQueryHandler(handle_cancel_edit, pattern="^cancel_edit$"))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
