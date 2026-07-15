# Form 7 PDF Parser

A small, typed Python library and command-line tool for parsing text-based Form 7 shipping
PDFs and adding order labels to their pages.

> [!IMPORTANT]
> This is an unofficial project. It is not affiliated with, endorsed by, or supported by
> Russian Post. No official logos, forms, or production documents are included.

## Features

- Extracts recipient name, phone, address, and a 14-digit tracking number.
- Processes multi-page PDFs and returns stable JSON.
- Adds sanitized order labels without using private `pypdf` APIs.
- Writes JSON and PDFs atomically with owner-only `0600` permissions.
- Applies default limits of 100 MiB and 500 pages.
- Keeps full page text out of results unless explicitly requested.
- Performs no network requests, analytics, or telemetry.

## Limitations

- Only PDFs with an extractable text layer are supported.
- Scanned documents require OCR before they can be parsed; OCR is not included.
- Parsing is heuristic because PDF text layout can vary between generators.
- Only 14-digit tracking numbers are accepted.

## Installation

Download the wheel from the [latest release](../../releases/latest), then install it:

```bash
python -m pip install form7_pdf_parser-0.1.0-py3-none-any.whl
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
    { "page_number": 1, "order_label": "Order #6904" }
  ]
}
```

```bash
form7-pdf annotate \
  --input form7.pdf \
  --overlay overlays.json \
  --output annotated.pdf
```

Successful commands return `0`, processing failures return `1`, and invalid command-line
arguments return `2`. Errors are written to standard error.

## Python API

```python
from form7_pdf_parser import Overlay, annotate_pdf, parse_pdf

result = parse_pdf("form7.pdf")
for page in result.pages:
    print(page.page_number, page.tracking_number, page.is_valid)

annotate_pdf(
    "form7.pdf",
    "annotated.pdf",
    [Overlay(page_number=1, order_label="Order #6904")],
)
```

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
