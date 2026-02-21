"""Команды /iiko и /iiko_orgs — проверка подключения и список организаций."""
import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

from bot.services.iiko_client import IikoClient
from config import (
    IIKO_DEFAULT_COUNTERAGENT_ID,
    IIKO_DEFAULT_STORE_ID,
    IIKO_SERVER_LOGIN,
    IIKO_SERVER_URL,
)

logger = logging.getLogger(__name__)


async def handle_iiko_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка подключения к iikoServer и показ номенклатуры."""
    if not update.message:
        return

    msg = update.message
    await msg.reply_text("⏳ Проверяю подключение к iikoServer...")

    iiko = IikoClient()

    if iiko._use_stub:
        url_preview = f"'{IIKO_SERVER_URL[:35]}...'" if IIKO_SERVER_URL else "пусто"
        login_preview = f"'{IIKO_SERVER_LOGIN[:20]}...'" if IIKO_SERVER_LOGIN else "пусто"
        await msg.reply_text(
            "⚠️ iikoServer не настроен\n\n"
            "Укажите в .env:\n"
            f"IIKO_SERVER_URL: {url_preview}\n"
            f"IIKO_SERVER_LOGIN: {login_preview}\n"
            "IIKO_SERVER_PASSWORD=ваш_пароль\n\n"
            "Пример: https://bufet-17-co.iiko.it\n"
            "Логин и пароль — от учётной записи iiko Office.",
        )
        return

    try:
        await msg.reply_text("🔑 Получаю токен...")
        token = await iiko.get_token()
        if not token:
            await msg.reply_text("❌ Не удалось получить токен. Проверьте логин и пароль.")
            return

        await msg.reply_text("📦 Загружаю номенклатуру...")
        products = await iiko.get_products()

        lines = [
            "✅ Подключение к iikoServer успешно\n",
            f"Товаров в номенклатуре: {len(products)}\n",
            "Примеры товаров (что бот видит в iiko):\n",
        ]

        for i, p in enumerate(products[:15], 1):
            name = (p.get("name") or "-")[:50]
            code = p.get("productCode") or p.get("number") or "-"
            prod_id = p.get("id", "")[:8]
            lines.append(f"{i}. {name}\n   Код: {code} | ID: {prod_id}...")

        if not products:
            lines.append("Номенклатура пуста или структура ответа API отличается.")

        # Склады и поставщики для создания поставок
        try:
            stores = await iiko.get_stores()
            suppliers = await iiko.get_suppliers()
            lines.append("\n📋 Для создания поставок (IIKO_READ_ONLY=false):")
            if stores:
                lines.append(f"Склады: {len(stores)} шт.")
                for s in stores[:5]:
                    mark = " ← текущий" if s["id"] == IIKO_DEFAULT_STORE_ID else ""
                    lines.append(f"  • {s['name'][:40]}: {s['id']}{mark}")
                if not IIKO_DEFAULT_STORE_ID:
                    lines.append("  Добавьте IIKO_DEFAULT_STORE_ID в .env")
            else:
                lines.append("Склады: не найдены (проверьте /resto/api/departments)")
            if suppliers:
                lines.append(f"Поставщики: {len(suppliers)} шт.")
                for s in suppliers[:5]:
                    mark = " ← текущий" if s["id"] == IIKO_DEFAULT_COUNTERAGENT_ID else ""
                    lines.append(f"  • {s['name'][:40]}: {s['id']}{mark}")
                if not IIKO_DEFAULT_COUNTERAGENT_ID:
                    lines.append("  Добавьте IIKO_DEFAULT_COUNTERAGENT_ID в .env")
            else:
                lines.append("Поставщики: не найдены (проверьте /resto/api/employees)")
        except Exception:
            lines.append("\n(Склады/поставщики: не удалось загрузить)")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (обрезано)"
        await msg.reply_text(text)

        # Файл со всеми товарами
        if products:
            file_lines = ["№\tНазвание\tКод\tID"]
            for i, p in enumerate(products, 1):
                name = (p.get("name") or "-").replace("\t", " ").replace("\n", " ")
                code = (p.get("productCode") or p.get("number") or "-").replace("\t", " ")
                prod_id = p.get("id", "-")
                file_lines.append(f"{i}\t{name}\t{code}\t{prod_id}")
            file_content = "\n".join(file_lines).encode("utf-8")
            bio = BytesIO(file_content)
            bio.seek(0)
            await msg.reply_document(
                document=bio,
                filename="iiko_nomenclature.txt",
                caption=f"Полный список товаров ({len(products)} шт.)",
            )

    except Exception as e:
        logger.exception("iiko status error")
        err_text = str(e)
        # Извлекаем тело ответа при HTTP ошибках
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.text
                if body and len(body) < 300:
                    err_text = f"{err_text}\n\nОтвет API: {body}"
            except Exception:
                pass
        if len(err_text) > 800:
            err_text = err_text[:800] + "..."
        await msg.reply_text(
            f"❌ Ошибка подключения к iiko\n\n{err_text}\n\n"
            "Проверьте учётные данные и связь с API.",
        )


async def handle_iiko_orgs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /iiko_orgs — в iikoServer организации не применимы."""
    if not update.message:
        return

    msg = update.message
    await msg.reply_text(
        "ℹ️ iikoServer API не использует организации.\n\n"
        "Номенклатура загружается с сервера целиком. "
        "Используйте команду /iiko для проверки подключения и просмотра товаров.",
    )
