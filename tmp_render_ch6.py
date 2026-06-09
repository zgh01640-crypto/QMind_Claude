from pathlib import Path

import fitz


pdf = next(Path("mydoc").glob("*建筑消耗量标准2024.pdf"))
document = fitz.open(pdf)
output = Path("tmp_bs2024_pages")
output.mkdir(exist_ok=True)

for page_no in range(269, 274):
    pixmap = document[page_no - 1].get_pixmap(
        matrix=fitz.Matrix(2.5, 2.5),
        alpha=False,
    )
    pixmap.save(output / f"page_{page_no}_building.png")
