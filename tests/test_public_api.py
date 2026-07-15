from __future__ import annotations

import form7_pdf_parser


def test_public_version_and_exports() -> None:
    assert form7_pdf_parser.__version__ == "0.1.0"
    assert "parse_pdf" in form7_pdf_parser.__all__
    assert "annotate_pdf" in form7_pdf_parser.__all__
