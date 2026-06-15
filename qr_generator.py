"""
generate_qr_barcodes.py
-----------------------
Reads an inventory Excel file and adds a QR_BARCODE column (col H)
right after PRODUCT_QUANTITY, embedding a scannable QR code image
for each row's SKU_ID.

Requirements:
    pip install pandas openpyxl qrcode pillow

Usage:
    python generate_qr_barcodes.py
    # or change INPUT_FILE / OUTPUT_FILE below as needed
"""

import io
import pandas as pd
import qrcode
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_FILE  = "ALL_INV-TMW_TH__1_.xlsx"   # path to your source file
OUTPUT_FILE = "inventory_with_qr.xlsx"     # output file name
QR_COL_NAME = "QR_BARCODE"                # header label for the new column
QR_SIZE_PX  = 80                          # pixel size of each embedded QR image
# ─────────────────────────────────────────────────────────────────────────────


def make_qr_bytes(value: str) -> io.BytesIO:
    """Generate a high-contrast QR code and return it as a PNG BytesIO object."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # highest error correction
        box_size=10,
        border=2,
    )
    qr.add_data(value)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((QR_SIZE_PX, QR_SIZE_PX), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def add_qr_column(input_path: str, output_path: str) -> None:
    # 1. Load data into a fresh workbook copy
    df = pd.read_excel(input_path)
    df.to_excel(output_path, index=False)

    wb = load_workbook(output_path)
    ws = wb.active

    # 2. Locate PRODUCT_QUANTITY column; QR goes right after it
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

    if "PRODUCT_QUANTITY" not in headers:
        raise ValueError("Column 'PRODUCT_QUANTITY' not found in the file.")
    if "SKU_ID" not in headers:
        raise ValueError("Column 'SKU_ID' not found in the file.")

    qty_col_idx = headers.index("PRODUCT_QUANTITY") + 1   # 1-based
    qr_col_idx  = qty_col_idx + 1                         # insert right after
    qr_col_letter = get_column_letter(qr_col_idx)

    # 3. Style the header cell
    header_cell = ws.cell(row=1, column=qr_col_idx, value=QR_COL_NAME)
    header_cell.font      = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    header_cell.fill      = PatternFill("solid", start_color="1F4E79")
    header_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions[qr_col_letter].width = 15   # wide enough for the image
    ws.row_dimensions[1].height = 20

    total_rows = len(df)
    print(f"Generating QR codes for {total_rows} rows...")

    # 4. Embed a QR image for every data row
    for row_num in range(2, total_rows + 2):
        sku_val = ws.cell(row=row_num, column=headers.index("SKU_ID") + 1).value
        if sku_val is None:
            continue

        # Normalise SKU to a clean string (handles int/float stored as float)
        sku_str = str(int(sku_val)) if isinstance(sku_val, float) else str(sku_val)

        # Generate QR and wrap in openpyxl Image
        xl_img        = XLImage(make_qr_bytes(sku_str))
        xl_img.width  = QR_SIZE_PX
        xl_img.height = QR_SIZE_PX
        xl_img.anchor = f"{qr_col_letter}{row_num}"

        # Align cell and set row height to fit the image
        ws.cell(row=row_num, column=qr_col_idx).alignment = Alignment(
            horizontal="center", vertical="center"
        )
        ws.row_dimensions[row_num].height = 62   # ~80px in points

        ws.add_image(xl_img)

        if row_num % 50 == 0:
            print(f"  ✓ {row_num - 1} / {total_rows} done")

    wb.save(output_path)
    print(f"\nSaved → {output_path}")


if __name__ == "__main__":
    add_qr_column(INPUT_FILE, OUTPUT_FILE)