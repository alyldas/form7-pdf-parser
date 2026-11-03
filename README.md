# Form 7 PDF Parser

A small, typed Python library and command-line tool for parsing text-based shipping waybills
and legacy Form 7 PDFs and adding order labels to their pages.

> [!IMPORTANT]
> This is an unofficial project. It is not affiliated with, endorsed by, or supported by
> Russian Post. No official logos, forms, or production documents are included.

## Features

- Prioritizes waybills with explicit `ОТ КОГО` / `КОМУ` sections; retains legacy Form 7 parsing.
- Extracts recipient name, phone, address, and a 14-digit tracking number.
- Processes multi-page PDFs and returns stable JSON.
- Adds `Заказ № <number>` in the free header area of either supported layout.
- Renders the proposed label area to detect existing text, lines, images, and annotations.
- Writes JSON and PDFs atomically with owner-only `0600` permissions on POSIX and
  best-effort private permissions on Windows.
- Applies default limits of 100 MiB and 500 pages.
- Keeps full page text out of results unless explicitly requested.
- Performs no network requests, analytics, or telemetry.

## Limitations

- Only PDFs with an extractable text layer are supported.
- Scanned documents require OCR before they can be parsed; OCR is not included.
- Parsing is heuristic because PDF text layout can vary between generators.
- Only 14-digit tracking numbers are accepted.
- Waybill tracking must appear before `ОТ КОГО`, as 14 contiguous digits or groups of
  6, 2, 5, and 1 digits. Conflicting tracking numbers are rejected.
- Waybill recipients are read under `КОМУ`, including wrapped names and phone numbers,
  inline section captions, Unicode phone dashes, and phones before or after the address.
  An initial standalone postcode is retained; a postcode after the address ends the block.
  Trailing `Заказ № ...` and older `Order #...` labels are excluded when the routing postcode is absent.
  Names and addresses are separated by phone/postcode and numeric address boundaries,
  not a dictionary of locality names. An unresolved wrapped-name/address boundary is
  reported as `ambiguous_recipient` instead of guessed.
  Repeated routing postcodes are removed only when they already appear in the address;
  different postcodes are preserved without choosing which one is correct.
- Rotated pages containing interactive annotations must be flattened before adding labels.

## Installation

Download the wheel from the [latest release](../../releases/latest), then install it:

```bash
python -m pip install ./form7_pdf_parser-*.whl
```

For development:

```bash
gh repo clone alyldas/form7-pdf-parser
cd form7-pdf-parser
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## CLI

Parse a PDF into JSON:

```bash
form7-pdf parse --input form7.pdf --output result.json
```

Full extracted page text is omitted by default because it can contain personal data. Opt in
only when the output is stored securely:

```bash
form7-pdf parse \
  --input form7.pdf \
  --output result.json \
  --include-raw-text
```

Add labels using an overlay file:

```json
{
  "overlays": [
    { "page_number": 1, "order_label": "6904" }
  ]
}
```

```bash
form7-pdf annotate \
  --input form7.pdf \
  --overlay overlays.json \
  --output annotated.pdf
```

Pass the order number as an ASCII digit string; leading zeros are preserved. An existing
`Заказ №` prefix is accepted and normalized, but other text and separators are rejected.
Five- and six-digit order numbers are supported, including leading zeros. Numbers longer
than 64 digits are rejected. Empty strings are ignored. No additional barcode is generated.

The library embeds Noto Sans Bold and prints `Заказ № <number>`. Compact waybills use the
header to the right of the logo, even on an A4 sheet; Form 7 uses the free area beside the
title. Header anchors adapt to scaling and CropBox offsets. Labels shrink from 12 pt down
to 8 pt if needed, and remain at least 7 mm above a detected recipient caption. Pages without
a recognized header use the previous top-right placement, subject to the same space check.

Before writing, PDFium renders the proposed area at 216 dpi with a 2 pt safety margin.
Any visible content in that area causes `OverlayError`; the library never erases an existing
number or searches for an arbitrary alternative position. Labels outside the visible page,
unfittable labels, and multiple forms on one page are rejected. On failure, an existing output
file remains unchanged. These checks verify placement, not postal acceptance of every PDF.

Successful commands return `0`, processing failures return `1`, and invalid command-line
arguments return `2`. Errors are written to standard error.

Both commands accept `--max-pages` and `--max-file-size-mib` to override their defensive
limits. Run `form7-pdf --version` for the installed version and `form7-pdf COMMAND --help` for
the complete command-specific options.

## Python API

```python
from form7_pdf_parser import Overlay, annotate_pdf, parse_pdf

result = parse_pdf("form7.pdf")
for page in result.pages:
    print(page.page_number, page.tracking_number, page.is_valid)
    if not page.is_valid:
        print([issue.value for issue in page.validation_issues])

annotate_pdf(
    "form7.pdf",
    "annotated.pdf",
    [Overlay(page_number=1, order_label="6904")],
)
```

Invalid Python results expose typed `validation_issues` values such as
`missing_tracking_number` and `missing_recipient`. Waybills additionally require a recipient
name, phone, address, and postcode. Missing fields, conflicting phones/postcodes, and multiple
shipments on one page make `is_valid` false. Legacy Form 7 validation remains unchanged.

Python results expose `recipient_postcode` when the address contains one unambiguous postcode;
it is `None` when missing or conflicting. Both conflicting values remain in the address.
The postcode and diagnostics are intentionally omitted from the stable JSON contract below;
JSON consumers can use `recipient_address` and `is_valid`.

The JSON contract is intentionally small and stable:

```json
{
  "page_count": 1,
  "pages": [
    {
      "page_number": 1,
      "recipient_name": "...",
      "recipient_phone": "...",
      "recipient_address": "...",
      "tracking_number": "...",
      "raw_text": null,
      "is_valid": true
    }
  ]
}
```

The package also exports the lower-level `parse_page`, `parse_tracking_number`, and
`parse_recipient_name_address_phone` helpers for advanced integrations. These functions are
best-effort text heuristics; prefer `parse_pdf` when processing complete documents.

Formats are detected per page, so one PDF can contain both layouts. Explicit waybill
sections take priority when the header contains tracking or no legacy recipient payment
block is present. Sender details are never used as a fallback for an empty `КОМУ` section.
The JSON fields are the same for both formats.

## Privacy and security

Shipping documents can contain names, addresses, phone numbers, payment amounts, and active
tracking numbers. Do not attach production PDFs or parser output to public issues. Use a
minimal synthetic reproduction instead.

The library uses defensive defaults, but it is not a malware scanner or a hardened document
sandbox. Process untrusted PDFs in an isolated worker with operating-system resource limits.
See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Development

```bash
ruff format --check .
ruff check .
mypy
pytest
python -m build
twine check dist/*
```

All committed PDF fixtures are generated from clearly fictional data. See
[tests/fixtures/README.md](tests/fixtures/README.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SUPPORT.md](SUPPORT.md) before opening an issue
or pull request.

## License

Released under the [MIT License](LICENSE).
