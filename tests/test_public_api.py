from __future__ import annotations

from importlib.metadata import version

import form7_pdf_parser


def test_public_version_and_exports() -> None:
    assert form7_pdf_parser.__version__ == version("form7-pdf-parser")
    assert "parse_pdf" in form7_pdf_parser.__all__
    assert "annotate_pdf" in form7_pdf_parser.__all__
    assert "PageValidationIssue" in form7_pdf_parser.__all__
