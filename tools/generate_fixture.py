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
    parser.add_argument("--layout", choices=("form7", "waybill"), default="form7")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("FixtureSans", args.font))

    canvas = Canvas(
        str(args.output),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    title = (
        "Synthetic waybill test fixture"
        if args.layout == "waybill"
        else "Synthetic Form 7 test fixture"
    )
    canvas.setTitle(title)
    canvas.setAuthor("form7-pdf-parser contributors")
    canvas.setSubject("Generated fictional data for parser tests")
    if args.layout == "waybill":
        source = Path(__file__).resolve().parents[1] / "tests/fixtures/synthetic-waybill.txt"
        positions = [
            (12.5, 400, 9),
            (81.457, 783.42, 9),
            (45, 720.42, 12),
            (14.5, 706.17, 9),
            (12.5, 688.92, 9),
            (12.5, 676.92, 9),
            (12.5, 664.92, 9),
            (12.5, 652.92, 9),
            (94.5, 639.42, 12),
            (150, 703.17, 9),
            (14.5, 620.67, 9),
            (12.5, 603.42, 9),
            (12.5, 591.42, 9),
            (12.5, 579.42, 9),
            (12.5, 567.42, 9),
            (228.6, 553.92, 12),
        ]
        for line, (x, y, size) in zip(
            source.read_text(encoding="utf-8").splitlines(), positions, strict=True
        ):
            canvas.setFont("FixtureSans", size)
            canvas.drawString(x, y, line)
        canvas.line(8, 835, 280, 835)
        canvas.line(8, 793, 280, 793)
        canvas.showPage()
    else:
        draw_page(canvas, PAGE_ONE_LINES, "FixtureSans")
        draw_page(canvas, PAGE_TWO_LINES, "FixtureSans")
    canvas.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
