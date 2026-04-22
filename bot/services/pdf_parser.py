"""PDF invoice parser for extracting products and supplier from счет-фактура."""
import re
from decimal import Decimal
from pathlib import Path

import pdfplumber


def _extract_supplier_from_text(text: str) -> str | None:
    """
    Извлекает название поставщика (продавца) из текста счёт-фактуры.
    Поддерживает: Продавец, Seller, Поставщик (рус), Етказиб берувчи (узб).
    """
    if not text or len(text) < 5:
        return None
    markers = [
        # Узбекский: "Етказиб берувчи: ... Сотиб олувчи: ..." — обрываем на покупателе
        r"етказиб\s+берувчи\s*[:\s]+(.+?)(?=\s+сотиб\s+олувчи|\n|$)",
        r"продавец\s*[:\s]+([^\n]+)",
        r"seller\s*[:\s]+([^\n]+)",
        r"поставщик\s*[:\s]+([^\n]+)",
        r"продавец\s*\n\s*([^\n]+)",
        r'["«]([^"»]+)["»]\s*[^\n]*именуемое[^\n]*исполнитель',
        r"исполнитель[^\n]*[«\"]([^»\"]+)[»\"]",
    ]
    for pattern in markers:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Убираем блок "Покупатель: XXX" / "Сотиб олувчи: ..." если попал в захват
            name = re.sub(r"\s*[;,]?\s*покупатель\s*:.*$", "", name, flags=re.I)
            name = re.sub(r"\s*[;,]?\s*buyer\s*:.*$", "", name, flags=re.I)
            name = re.sub(r"\s*[;,]?\s*сотиб\s+олувчи\s*:.*$", "", name, flags=re.I)
            # Убираем ИНН, КПП, адрес
            name = re.sub(r"\s*[,;]\s*и[\sн]+\.?\s*\d+.*", "", name, flags=re.I)
            name = re.sub(r"\s*[,;]\s*к[\sп]+п\.?\s*\d+.*", "", name, flags=re.I)
            name = re.sub(r"\s*,\s*[\d\s\-]+.*", "", name)
            name = re.sub(r"\"", "", name).strip()
            if len(name) >= 3 and not re.match(r"^[\d\s\-\.]+$", name):
                return name[:120]
    return None


def normalize_unit(unit: str) -> str:
    """Преобразует единицы измерения в шт/л/кг."""
    if not unit:
        return "шт"
    u = unit.lower().replace("\n", " ").strip()
    if "тонн" in u or "tonna" in u:
        return "кг"
    if "кг" in u or "kilogram" in u or "килограмм" in u:
        return "кг"
    if "литр" in u or "liter" in u or re.fullmatch(r"л\.?", u):
        return "л"
    # "dona", "dona (puchok)" — узб. «штука/пучок»
    return "шт"


def _unit_quantity_multiplier(unit: str) -> float:
    """
    Множитель количества при нормализации единицы измерения.
    tonna → кг: количество × 1000 (цена в PDF за тонну, итог пересчитываем в кг).
    """
    if not unit:
        return 1.0
    u = unit.lower().replace("\n", " ").strip()
    if "тонн" in u or "tonna" in u:
        return 1000.0
    return 1.0


def _parse_number(s: str) -> Decimal | None:
    """Парсит число из строки (убирает пробелы, запятые)."""
    if not s:
        return None
    s = str(s).replace(" ", "").replace(",", ".").strip()
    try:
        return Decimal(s)
    except Exception:
        return None


def _is_product_row(row: list, num_col: int = 0) -> bool:
    """Проверяет, является ли строка строкой товара (не заголовок, не итого)."""
    if not row or len(row) < 5:
        return False
    try:
        val = str(row[num_col] or "").strip()
        if not val:
            return False
        num = int(val)
        return num > 0
    except (ValueError, TypeError):
        return False


def _find_column_indices(header_row: list) -> dict:
    """Определяет индексы колонок по заголовку (рус/узб)."""
    indices = {
        "num": 0,
        "name": 1,
        "code": 2,
        "unit": 3,
        "quantity": 4,
        "price": 5,
        "cost_vat": 9,
    }
    row_lower = [str(c or "").lower().replace("\n", " ") for c in header_row]
    for i, cell in enumerate(row_lower):
        if cell.strip() == "№" or (len(cell) <= 3 and "№" in cell):
            indices["num"] = i
        elif "наименование" in cell and ("товар" in cell or "услуг" in cell):
            indices["name"] = i
        elif "маҳсулот номи" in cell or "махсулот номи" in cell:
            indices["name"] = i
        elif ("ўлчов" in cell and "бирлиги" in cell) or ("улчов" in cell and "бирлиги" in cell):
            indices["unit"] = i
        elif "ед" in cell or "измер" in cell:
            indices["unit"] = i
        elif "миқдор" in cell or "микдор" in cell:
            indices["quantity"] = i
        elif "количество" in cell or "кол-во" in cell:
            indices["quantity"] = i
        elif "нарҳ" in cell or "нарх" in cell:
            indices["price"] = i
        elif "цена" in cell and "ндс" not in cell:
            indices["price"] = i
        # Узбекский: "Етказиб беришнинг ҚҚСни ҳисобга олган ҳолда қиймати"
        elif ("ҳисобга" in cell or "хисобга" in cell) and ("қиймати" in cell or "киймати" in cell):
            indices["cost_vat"] = i
        elif "ндс" in cell and "учетом" in cell:
            indices["cost_vat"] = i
        elif "стоимость" in cell and "ндс" in cell:
            indices["cost_vat"] = i
        elif "стоимость" in cell and "поставки" in cell and "учётом" in cell:
            indices["cost_vat"] = i
        elif "идентификацион" in cell or "идентификация" in cell:
            indices["code"] = i
        elif "код" in cell and "штрих" not in cell:
            indices["code"] = i
    return indices


def parse_invoice_pdf(pdf_path: str | Path) -> dict:
    """
    Извлекает товары и поставщика из PDF счёт-фактуры.
    Возвращает: {"products": [...], "supplier_name": str | None}
    products: [{"name", "unit", "quantity", "price_with_vat", "code_from_pdf"}, ...]
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    products: list[dict] = []
    supplier_name: str | None = None
    skip_words = {"итого", "всего", "total", "сумма", "купля-продажа", "жами"}

    with pdfplumber.open(pdf_path) as pdf:
        # Извлекаем поставщика из текста первой страницы
        if pdf.pages:
            first_page_text = pdf.pages[0].extract_text() or ""
            supplier_name = _extract_supplier_from_text(first_page_text)

        for page in pdf.pages:
            tables = page.extract_tables()
            col_indices = None

            for table in tables:
                for row_idx, row in enumerate(table):
                    if not row:
                        continue

                    # Заголовок: строка с маркером названия и количества (рус/узб).
                    # Требуем несколько колонок, чтобы не принять объединённую ячейку договора.
                    non_empty = sum(1 for c in row if c and str(c).strip())
                    row_str = " ".join(str(c or "").lower().replace("\n", " ") for c in row)
                    has_name = (
                        "наименование" in row_str
                        or "маҳсулот номи" in row_str
                        or "махсулот номи" in row_str
                    )
                    has_qty = (
                        "количество" in row_str
                        or "кол-во" in row_str
                        or "миқдор" in row_str
                        or "микдор" in row_str
                    )
                    if non_empty >= 3 and has_name and has_qty:
                        col_indices = _find_column_indices(row)
                        continue

                    if col_indices is None:
                        continue

                    num_col = col_indices.get("num", 0)
                    if not _is_product_row(row, num_col=num_col):
                        continue

                    # Индексы по умолчанию для типичной счет-фактуры
                    idx = col_indices or {
                        "num": 0,
                        "name": 1,
                        "code": 2,
                        "unit": 3,
                        "quantity": 4,
                        "price": 5,
                        "cost_vat": 9,
                    }

                    name = (row[idx["name"]] or "").strip().replace("\n", " ")
                    # Убираем артикул из названия (например "Высший *10013")
                    name = re.sub(r"\s*\*[\d\w]+\s*$", "", name).strip()
                    if not name or any(s in name.lower() for s in skip_words):
                        continue

                    # Код из отдельной колонки. Узб. формат: "01003001001000000 - Арпа".
                    code = (row[idx["code"]] if idx["code"] < len(row) else "")
                    code = (code or "").replace("\n", " ").strip()
                    code = re.sub(r"\s+", " ", code)

                    raw_unit = ""
                    if idx["unit"] < len(row):
                        raw_unit = (row[idx["unit"]] or "").strip()
                    unit = normalize_unit(raw_unit)
                    qty_multiplier = _unit_quantity_multiplier(raw_unit)

                    qty = _parse_number(row[idx["quantity"]] if idx["quantity"] < len(row) else "")
                    cost_vat = _parse_number(row[idx["cost_vat"]] if idx["cost_vat"] < len(row) else "")
                    price = _parse_number(row[idx["price"]] if idx["price"] < len(row) else "")

                    if qty is None or qty <= 0:
                        continue

                    qty_normalized = float(qty) * qty_multiplier

                    # Цена с НДС = стоимость с НДС / нормализованное количество
                    if cost_vat and cost_vat > 0 and qty_normalized > 0:
                        price_with_vat = float(cost_vat) / qty_normalized
                    elif price:
                        # Цена в PDF — за исходную единицу, приводим к нормализованной
                        price_with_vat = float(price) / qty_multiplier if qty_multiplier else float(price)
                    else:
                        price_with_vat = 0.0

                    product = {
                        "name": name,
                        "unit": unit,
                        "quantity": round(qty_normalized, 6),
                        "price_with_vat": round(price_with_vat, 2),
                        "code_from_pdf": (code or "")[:80],
                    }
                    products.append(product)

    return {"products": products, "supplier_name": supplier_name}
