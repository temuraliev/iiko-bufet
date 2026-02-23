"""Скрипт для анализа структуры PDF — извлекает текст и таблицы."""
import json
import sys
from pathlib import Path

import pdfplumber

OUTPUT_FILE = Path(__file__).parent / "debug_pdf_output.txt"


def analyze_pdf(pdf_path: str | Path) -> None:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        return

    lines = [f"=== Анализ: {pdf_path.name} ===\n"]

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            lines.append(f"--- Страница {i + 1} ---")

            text = page.extract_text()
            if text:
                lines.append("ТЕКСТ (первые 2000 символов):")
                lines.append(text[:2000])
                lines.append("")

            tables = page.extract_tables()
            if tables:
                lines.append(f"ТАБЛИЦЫ: {len(tables)} шт.")
                for t_idx, table in enumerate(tables):
                    lines.append(f"\nТаблица {t_idx + 1} ({len(table)} строк):")
                    for r_idx, row in enumerate(table[:20]):
                        lines.append(f"  {r_idx}: {row}")
                    if len(table) > 20:
                        lines.append(f"  ... и ещё {len(table) - 20} строк")
                lines.append("")
            else:
                lines.append("Таблицы не найдены.")
            lines.append("")

    result = "\n".join(lines)
    OUTPUT_FILE.write_text(result, encoding="utf-8")
    print(f"Результат сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Gonzo\Downloads\Telegram Desktop\Договор (НК)_ 43_622 от 16.02.2026 .pdf"
    analyze_pdf(path)
