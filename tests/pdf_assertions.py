from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PageObject


def drawn_label(page: PageObject) -> str:
    """Read the ordered glyph references in a vector label's drawing commands."""
    characters = []

    def visit(operator, operands, cm, tm):
        if operator == b"Do" and str(operands[0]).startswith("/FormXob.g"):
            codepoint = str(operands[0]).removeprefix("/FormXob.g").split("-")[0]
            characters.append(chr(int(codepoint)))

    page.extract_text(visitor_operand_before=visit)
    return "".join(characters).replace("Заказ№", "Заказ № ")


def render_page(path: Path, page_number: int = 0) -> bytes:
    with (
        pdfium.PdfDocument(str(path)) as document,
        closing(document[page_number]) as page,
        closing(page.render(scale=2, grayscale=True)) as bitmap,
    ):
        return bytes(bitmap.buffer)
