"""Full trace of parse_invoice_pdf."""
import sys
import io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.services.pdf_parser import parse_invoice_pdf, _find_column_indices, _is_product_row

pdf_path = Path(r"c:\Users\Gonzo\Downloads\Telegram Desktop\Счет_фактура_без_акта_MF00_000000057061_от_09_02_2026_.pdf")

import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    for pi, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        print(f"Page {pi}: {len(tables)} tables")
        for ti, table in enumerate(tables):
            print(f"  Table {ti}: {len(table)} rows")
            col_indices = None
            for ri, row in enumerate(table):
                if not row:
                    continue
                non_empty = sum(1 for c in row if c and str(c).strip())
                row_str = " ".join(str(c or "").lower() for c in row)
                is_header = non_empty >= 4 and ("наименование" in row_str or "единица" in row_str) and ("количество" in row_str or "наименование" in row_str)
                is_product = _is_product_row(row)

                if is_header:
                    col_indices = _find_column_indices(row)
                    print(f"    Row {ri}: HEADER, indices={col_indices}")
                    continue
                if is_product and col_indices:
                    idx = col_indices
                    name = (row[idx["name"]] or "").strip().replace("\n", " ")
                    import re
                    name = re.sub(r"\s*\*[\d\w]+\s*$", "", name).strip()
                    skip_words = {"итого", "всего", "total", "сумма", "купля-продажа"}
                    if name and not any(s in name.lower() for s in skip_words):
                        print(f"    Row {ri}: PRODUCT name={name[:50]}...")
                    else:
                        print(f"    Row {ri}: SKIP (name={name!r})")
