from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import form7_pdf_parser


def test_public_version_and_exports() -> None:
    assert form7_pdf_parser.__version__ == version("form7-pdf-parser")
    assert "parse_pdf" in form7_pdf_parser.__all__
    assert "annotate_pdf" in form7_pdf_parser.__all__
    assert "PageValidationIssue" in form7_pdf_parser.__all__


def test_font_is_loaded_only_when_adding_labels(tmp_path: Path) -> None:
    # A fresh interpreter prevents other PDF tests from preloading the font.
    script = """
import sys
from pathlib import Path
from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames
from pypdf import PdfReader
from form7_pdf_parser import Overlay, annotate_pdf, parse_page, parse_pdf

source, copy, labelled = map(Path, sys.argv[1:])
assert "Form7NotoSansBold" not in getRegisteredFontNames()
assert not parse_page("", 1).is_valid
assert parse_pdf(source).page_count == 2
annotate_pdf(source, copy, [])
assert copy.read_bytes() == source.read_bytes()
assert "Form7NotoSansBold" not in getRegisteredFontNames()
annotate_pdf(source, labelled, [Overlay(1, "001234")])
assert "Form7NotoSansBold" in getRegisteredFontNames()
assert "Заказ № 001234" in PdfReader(labelled).pages[0].extract_text()
"""
    result = subprocess.run(  # noqa: S603 — fixed script and local synthetic PDF, no shell
        [
            sys.executable,
            "-c",
            script,
            str(Path(__file__).parent / "fixtures/synthetic-form7.pdf"),
            str(tmp_path / "copy.pdf"),
            str(tmp_path / "labelled.pdf"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
