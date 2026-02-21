"""Configuration for iiko invoice bot."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env из папки проекта (где лежит config.py)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# iikoServer API (полная номенклатура, включая товары на складе GOODS)
IIKO_SERVER_URL = (os.getenv("IIKO_SERVER_URL") or "").strip().rstrip("/")
IIKO_SERVER_LOGIN = (os.getenv("IIKO_SERVER_LOGIN") or "").strip()
IIKO_SERVER_PASSWORD = (os.getenv("IIKO_SERVER_PASSWORD") or "").strip()
# Для создания поставок: склад и контрагент (поставщик)
IIKO_DEFAULT_STORE_ID = (os.getenv("IIKO_DEFAULT_STORE_ID") or "").strip()
IIKO_DEFAULT_COUNTERAGENT_ID = (os.getenv("IIKO_DEFAULT_COUNTERAGENT_ID") or "").strip()

# Склады для выбора (API может не возвращать). Формат: uuid1:Название1,uuid2:Название2
# Если пусто — используется список по умолчанию из incomingInvoice
_warehouses_env = (os.getenv("IIKO_WAREHOUSES") or "").strip()

# Склад → поставщик: для складов с привязкой к конкретному поставщику (iiko не принимает других)
STORE_SUPPLIER_OVERRIDE: dict[str, str] = {
    "0aba85a4-1f6c-4fdf-bdcc-e02f2b323654": "8b982543-e823-430c-8458-e7deb8cc9c39",  # Хоз товары → СП Bazelik Business
}


def get_warehouses_config() -> list[dict]:
    """Список складов для выбора. Сначала из .env, иначе дефолтный."""
    if _warehouses_env:
        result = []
        for part in _warehouses_env.split(","):
            part = part.strip()
            if ":" in part:
                uid, name = part.split(":", 1)
                uid, name = uid.strip(), name.strip()
                if uid:
                    result.append({"id": uid, "name": name or uid[:8]})
        if result:
            return result
    # Дефолтный список (из incomingInvoice.xml и скриншота iiko)
    return [
        {"id": "1239d270-1bbe-f64f-b7ea-5f00518ef508", "name": "Bufet 17 (Основной склад)"},
        {"id": "bc65b2d2-f440-4c56-b1cb-513775216d49", "name": "Bufet 17 (Склад Gonzo Gaming)"},
        {"id": "d4a7caed-7e9d-4be0-a2f2-d1d74f1a6e80", "name": "Bufet 17 (Услуги)"},
        {"id": "0aba85a4-1f6c-4fdf-bdcc-e02f2b323654", "name": "Bufet 17 (Хоз товары склад)"},
    ]
# Режим только чтение — бот не создаёт поставки в iiko
IIKO_READ_ONLY = os.getenv("IIKO_READ_ONLY", "true").lower() in ("true", "1", "yes")

# Temporary files
TEMP_DIR = Path(os.getenv("TEMP_DIR", "temp"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)
