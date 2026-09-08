from pathlib import Path

import fitz
from PIL import Image, ImageDraw

pdf = fitz.open(r"C:\flashcardsmaker\RAZ词汇.pdf")
cards = []
for page_number, page in enumerate(pdf, start=1):
    pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    split = image.height // 2
    for position, (top, bottom) in enumerate(((10, split - 4), (split + 10, image.height - 10))):
        cards.append((f"P{page_number}-{'T' if position == 0 else 'B'}", image.crop((0, top, image.width, bottom))))

column_width, row_height = 560, 290
sheet = Image.new("RGB", (column_width * 2, ((len(cards) + 1) // 2) * row_height), "white")
draw = ImageDraw.Draw(sheet)
for index, (label, image) in enumerate(cards):
    image.thumbnail((column_width - 20, row_height - 42))
    x = (index % 2) * column_width
    y = (index // 2) * row_height
    draw.text((x + 12, y + 8), label, fill="black")
    sheet.paste(image, (x + 10, y + 30))

output = Path(r"C:\flashcardsmaker\outputs\raz-vocabulary-extracted\cards-audit.jpg")
sheet.save(output, quality=96)
print(output, len(cards))
