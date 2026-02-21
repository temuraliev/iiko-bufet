"""Отладка поиска в iiko — запустите для проверки поиска по названиям из PDF."""
import asyncio
import sys
import io
from pathlib import Path

# UTF-8 для корректного отображения кириллицы в Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.services.iiko_client import IikoClient
from bot.services.pdf_parser import parse_invoice_pdf

PDF_PATH = Path(r"c:\Users\Gonzo\Downloads\Telegram Desktop\Счет_фактура_без_акта_MF00_000000057061_от_09_02_2026_.pdf")


async def main():
    pdf_path = PDF_PATH if PDF_PATH.exists() else (Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    if not pdf_path or not pdf_path.exists():
        print("Укажите путь к PDF: python debug_iiko_search.py <path_to_pdf>")
        return

    parsed = parse_invoice_pdf(pdf_path)
    products = parsed.get("products", [])
    supplier = parsed.get("supplier_name")
    print(f"Поставщик из PDF: {supplier or '(не найден)'}")
    print(f"Из PDF: {len(products)} товаров\n")

    iiko = IikoClient()
    if iiko._use_stub:
        print("Укажите в .env: IIKO_SERVER_URL, IIKO_SERVER_LOGIN, IIKO_SERVER_PASSWORD")
        return

    all_products = await iiko.get_products()
    print(f"В iiko: {len(all_products)} товаров")

    # Ищем товары с "гриб" или "масло" в названии
    for kw in ["гриб", "шампиньон", "масло", "фритюр"]:
        found = [p for p in all_products if kw in (p.get("name") or "").lower()]
        if found:
            print(f"\n  По '{kw}': {len(found)} шт.")
            for p in found[:5]:
                print(f"    - {p.get('name')} (код: {p.get('productCode') or p.get('number') or '-'})")

    print("\n--- Поиск по каждому товару из PDF ---\n")
    for i, p in enumerate(products, 1):
        name = p.get("name", "")
        matches = await iiko.search_product(name)
        status = matches[0]["name"] if matches else "НЕ НАЙДЕНО"
        print(f"{i}. {name[:50]}...")
        print(f"   -> {status}")
        if matches:
            print(f"   Код: {matches[0].get('productCode') or matches[0].get('number', '-')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
