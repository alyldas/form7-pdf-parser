from __future__ import annotations

from importlib.metadata import version

import form7_pdf_parser


def test_public_version_and_exports() -> None:
    assert form7_pdf_parser.__version__ == version("form7-pdf-parser")
    assert set(form7_pdf_parser.__all__) == {
        "Form7Error",
        "Overlay",
        "OverlayError",
        "PageValidationIssue",
        "ParseResult",
        "ParsedPage",
        "PdfLimitError",
        "PdfReadError",
        "__version__",
        "annotate_pdf",
        "normalize_overlay_label",
        "parse_page",
        "parse_pdf",
        "parse_recipient_name_address_phone",
        "parse_tracking_number",
    }
