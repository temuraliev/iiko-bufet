"""Сохранение и загрузка сопоставлений «название из PDF» → «товар в iiko»."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Файл для хранения сопоставлений (рядом с config.py)
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_MAPPINGS_FILE = _DATA_DIR / "product_mappings.json"


def _normalize_key(name: str) -> str:
    """Нормализация ключа: trim и схлопывание пробелов."""
    return " ".join((name or "").strip().split())


def _load_raw() -> dict:
    """Загружает сырые данные из JSON."""
    if not _MAPPINGS_FILE.exists():
        return {}
    try:
        with open(_MAPPINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Не удалось загрузить сопоставления: %s", e)
        return {}


def _save_raw(data: dict) -> None:
    """Сохраняет данные в JSON."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(_MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("Не удалось сохранить сопоставления: %s", e)


def get_mapping(pdf_name: str) -> dict | None:
    """
    Возвращает сохранённое сопоставление для названия из PDF.
    Возвращает None, если сопоставления нет.
    """
    key = _normalize_key(pdf_name)
    if not key:
        return None
    data = _load_raw()
    return data.get(key)


def remove_mapping(pdf_name: str) -> None:
    """Удаляет сопоставление (например, если товар больше не существует в iiko)."""
    key = _normalize_key(pdf_name)
    if not key:
        return
    data = _load_raw()
    if key in data:
        del data[key]
        _save_raw(data)


def save_mappings(mappings: dict[str, dict]) -> None:
    """
    Сохраняет сопоставления. Ключи — названия из PDF, значения — {id, name, productCode}.
    Объединяет с существующими данными.
    """
    if not mappings:
        return
    data = _load_raw()
    for pdf_name, iiko_product in mappings.items():
        key = _normalize_key(pdf_name)
        if not key or not iiko_product.get("id"):
            continue
        data[key] = {
            "id": iiko_product["id"],
            "name": iiko_product.get("name", ""),
            "productCode": iiko_product.get("productCode") or iiko_product.get("number", ""),
        }
    _save_raw(data)
