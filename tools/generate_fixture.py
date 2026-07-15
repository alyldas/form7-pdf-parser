#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

PAGE_ONE_LINES = [
    "Synthetic Form 7 fixture",
    "Оплачивается при вручении",
    "000000",
    "00",
    "00000",
    "0",
    "100 руб 00 коп",
    "Тестов Тест Тестович",
    "000000, г. Примерск, ул. Макетная,",
    "д. 0",
    "+7 (000) 000-00-00",
]

PAGE_TWO_LINES = [
    "Synthetic invalid page",
    "No recipient, phone, address, payment, or tracking data.",
]


def draw_page(canvas: Canvas, lines: list[str], font_name: str) -> None:
    canvas.setFont(font_name, 12)
    y = A4[1] - 56
    for line in lines:
        canvas.drawString(56, y, line)
        y -= 24
    canvas.showPage()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic Form 7 PDF fixture")
    parser.add_argument("--font", required=True, type=Path, help="Path to an OFL font")
    parser.add_argument("--output", required=True, type=Path, help="Output fixture path")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("FixtureSans", args.font))

    canvas = Canvas(
        str(args.output),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    canvas.setTitle("Synthetic Form 7 test fixture")
    canvas.setAuthor("form7-pdf-parser contributors")
    canvas.setSubject("Generated fictional data for parser tests")
    draw_page(canvas, PAGE_ONE_LINES, "FixtureSans")
    draw_page(canvas, PAGE_TWO_LINES, "FixtureSans")
    canvas.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
