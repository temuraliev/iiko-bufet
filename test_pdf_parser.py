"""Тест парсера PDF без запуска бота."""
import sys
import io
from pathlib import Path

# Fix Windows console encoding for Cyrillic
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.services.pdf_parser import parse_invoice_pdf


def main():
    # Тестовый PDF - путь к файлу пользователя
    pdf_path = Path(r"c:\Users\Gonzo\Downloads\Telegram Desktop\Счет_фактура_без_акта_MF00_000000057061_от_09_02_2026_.pdf")
    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        print("Укажите путь к PDF в скрипте или передайте как аргумент.")
        if len(sys.argv) > 1:
            pdf_path = Path(sys.argv[1])
            if not pdf_path.exists():
                print(f"Файл не найден: {pdf_path}")
                return
        else:
            return

    print("Парсинг PDF...")
    try:
        parsed = parse_invoice_pdf(pdf_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return

    products = parsed.get("products", [])
    supplier = parsed.get("supplier_name")
    print(f"\nПоставщик из PDF: {supplier or '(не найден)'}")
    print(f"Найдено товаров: {len(products)}\n")
    for i, p in enumerate(products, 1):
        print(f"{i}. {p['name']}")
        print(f"   Ед: {p['unit']} | Кол-во: {p['quantity']} | Цена с НДС: {p['price_with_vat']}")
        code = (p.get("code_from_pdf") or "-")[:50]
        print(f"   Код из PDF: {code}")
        print()


if __name__ == "__main__":
    main()
