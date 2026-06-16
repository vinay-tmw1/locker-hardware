"""
generate_qr_barcodes.py
-----------------------
Reads an inventory Excel file, removes empty rows, generates a unique
13-digit SKU_ID for each row, keeps all original columns, and adds a
QR_BARCODE column at the end embedding a scannable QR code for each
row's new SKU_ID.

Requirements:
    pip install pandas openpyxl qrcode pillow

Usage:
    python generate_qr_barcodes.py
"""

import io
import random
import pandas as pd
import qrcode
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_FILE  = "ALL_INV-TMW_TH__1_.xlsx"   # path to your source file
OUTPUT_FILE = "inventory_with_qr.xlsx"        # output file name
QR_COL_NAME = "QR_BARCODE"                    # header label for the new column
QR_SIZE_PX  = 80                              # pixel size of each embedded QR image
SKU_DIGITS   = 13                             # total length of generated SKU_ID
PREFIX_DIGITS = 10                             # same first 10 digits for all SKUs
SUFFIX_DIGITS = SKU_DIGITS - PREFIX_DIGITS     # last 3 digits, sequential 001,002,...
# ─────────────────────────────────────────────────────────────────────────────


def generate_sequential_skus(n: int) -> list:
    """Generate n SKU_IDs sharing the same random 10-digit prefix,
    with sequential 3-digit suffixes: 001, 002, 003, ..."""
    low    = 10 ** (PREFIX_DIGITS - 1)
    high   = (10 ** PREFIX_DIGITS) - 1
    prefix = str(random.randint(low, high))

    max_suffix = (10 ** SUFFIX_DIGITS) - 1
    if n > max_suffix:
        raise ValueError(f"Too many rows ({n}) for a {SUFFIX_DIGITS}-digit suffix.")

    return [f"{prefix}{str(i).zfill(SUFFIX_DIGITS)}" for i in range(1, n + 1)]


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
    # 1. Load data
    df = pd.read_excel(input_path)

    # 2. Remove fully empty rows (e.g. blank rows like 1243-1251)
    df = df.dropna(how="all").reset_index(drop=True)

    # 3. Also drop rows that have no PRODUCT_NAME (stray/blank-but-not-fully-empty rows)
    if "PRODUCT_NAME" in df.columns:
        df = df[df["PRODUCT_NAME"].notna()].reset_index(drop=True)

    # 4. Generate a unique 13-digit SKU_ID for every remaining row
    df["SKU_ID"] = generate_sequential_skus(len(df))

    # 5. Save cleaned data (all original columns kept, SKU_ID replaced)
    df.to_excel(output_path, index=False)

    wb = load_workbook(output_path)
    ws = wb.active

    # 6. QR column goes right after the last existing column
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    qr_col_idx    = ws.max_column + 1
    qr_col_letter = get_column_letter(qr_col_idx)

    # 7. Style the header cell
    header_cell = ws.cell(row=1, column=qr_col_idx, value=QR_COL_NAME)
    header_cell.font      = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    header_cell.fill      = PatternFill("solid", start_color="1F4E79")
    header_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions[qr_col_letter].width = 15   # wide enough for the image
    ws.row_dimensions[1].height = 20

    total_rows = len(df)
    print(f"Generating QR codes for {total_rows} rows...")

    sku_col_idx = headers.index("SKU_ID") + 1

    # 8. Embed a QR image for every data row (encodes the new unique SKU_ID)
    for row_num in range(2, total_rows + 2):
        sku_val = ws.cell(row=row_num, column=sku_col_idx).value
        if sku_val is None:
            continue

        sku_str = str(sku_val)

        xl_img        = XLImage(make_qr_bytes(sku_str))
        xl_img.width  = QR_SIZE_PX
        xl_img.height = QR_SIZE_PX
        xl_img.anchor = f"{qr_col_letter}{row_num}"

        ws.cell(row=row_num, column=qr_col_idx).alignment = Alignment(
            horizontal="center", vertical="center"
        )
        ws.row_dimensions[row_num].height = 62   # ~80px in points

        ws.add_image(xl_img)

        if row_num % 50 == 0:
            print(f"  ✓ {row_num - 1} / {total_rows} done")

    wb.save(output_path)
    print(f"\nSaved -> {output_path}")


if __name__ == "__main__":
    add_qr_column(INPUT_FILE, OUTPUT_FILE)