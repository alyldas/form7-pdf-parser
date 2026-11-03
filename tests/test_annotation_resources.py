from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import closing
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pdf_assertions import drawn_label
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject
from reportlab.pdfgen.canvas import Canvas

from form7_pdf_parser import Overlay, annotate_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-form7.pdf"


def test_vector_labels_embed_no_fonts_and_reuse_glyphs(tmp_path: Path) -> None:
    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=400, height=300)
    writer.write(source)
    output = tmp_path / "vector.pdf"

    annotate_pdf(source, output, [Overlay(i, "00123456789") for i in range(1, 4)])

    pages = PdfReader(output).pages
    first = pages[0]["/Resources"]["/XObject"]
    for page in pages:
        assert page.extract_text() == ""
        assert not page["/Resources"].get("/Font")
        assert drawn_label(page) == "Заказ № 00123456789"
        forms = page["/Resources"]["/XObject"]
        for name, reference in forms.items():
            assert reference == first.raw_get(name)
            assert not reference.get_object()["/Resources"]["/Font"]
    assert output.stat().st_size - source.stat().st_size < 15_000


def test_vector_label_matches_text_reference_visually(tmp_path: Path) -> None:
    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=300)
    writer.write(source)
    output = tmp_path / "vector.pdf"
    annotate_pdf(source, output, [Overlay(1, "00123456789")])

    reference = tmp_path / "reference.pdf"
    canvas = Canvas(str(reference), pagesize=(400, 300))
    canvas.setFont("Form7NotoSansBold", 12)
    canvas.drawRightString(360, 272, "Заказ № 00123456789")
    canvas.save()
    masks = []
    for path in (reference, output):
        with (
            pdfium.PdfDocument(str(path)) as document,
            closing(document[0]) as page,
            closing(page.render(scale=4, grayscale=True)) as bitmap,
        ):
            masks.append({i for i, value in enumerate(bitmap.buffer) if value < 128})
    assert len(masks[0] & masks[1]) / len(masks[0] | masks[1]) > 0.9


def _dense_document(path: Path) -> None:
    # Synthetic line art exercises large content streams without private PDFs.
    drawing = BytesIO()
    canvas = Canvas(drawing, pagesize=(595, 842), invariant=1)
    for index in range(2000):
        canvas.rect(20 + index % 100 * 5, 30 + index // 100 * 10, 2, 2)
    canvas.save()
    page = PdfReader(FIXTURE).pages[0]
    writer = PdfWriter()
    prepared = writer.add_page(page)
    prepared.merge_page(PdfReader(drawing).pages[0])
    content = prepared.get_contents().get_data()
    page = prepared
    # Each source page has its own compressed stream, as a normal PDF producer
    # would write, while fonts remain shared across all 500 pages.
    writer = PdfWriter()
    for index in range(500):
        target = writer.add_page(page)
        stream = DecodedStreamObject()
        stream.set_data(content + f"\n% page {index}\n".encode())
        del target["/Contents"]
        target.replace_contents(stream.flate_encode())
    writer.write(path)


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS requires native Linux")
def test_500_page_cli_annotation_with_512_mib_address_space(tmp_path: Path) -> None:
    source = tmp_path / "500-pages.pdf"
    _dense_document(source)
    overlays = tmp_path / "overlays.json"
    overlays.write_text(
        json.dumps(
            {"overlays": [{"page_number": i, "order_label": str(i)} for i in range(1, 501)]}
        ),
        encoding="utf-8",
    )
    output = tmp_path / "annotated.pdf"
    runner = """
import resource
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
assert resource.getrlimit(resource.RLIMIT_AS) == (536870912, 536870912)
from form7_pdf_parser.cli import main
raise SystemExit(main())
"""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            runner,
            "annotate",
            "--input",
            str(source),
            "--overlay",
            str(overlays),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONFAULTHANDLER": "1"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # A small fixed glyph set plus short drawing commands per page, not copies
    # of source fonts or uncompressed page content. Percentages depend on input.
    assert output.stat().st_size <= source.stat().st_size + 15_000 + 500 * 1024
    pages = PdfReader(output).pages
    assert len(pages) == 500
    assert [drawn_label(page) for page in pages] == [f"Заказ № {i}" for i in range(1, 501)]
