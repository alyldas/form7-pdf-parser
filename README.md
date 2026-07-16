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
python -m pip install ./form7_pdf_parser-*.whl
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

Labels retain ASCII letters, digits, spaces, `#`, `-`, `_`, and `/`. Other characters are
removed, empty normalized labels are ignored, and normalized labels longer than 64 characters
are rejected.

Successful commands return `0`, processing failures return `1`, and invalid command-line
arguments return `2`. Errors are written to standard error.

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
    [Overlay(page_number=1, order_label="Order #6904")],
)
```

A page is valid when it has a 14-digit tracking number and at least a recipient name or
phone number. The address is optional. The recommended package-level API consists of the
documented models, exceptions, `parse_pdf`, and `annotate_pdf`. Low-level helpers remain
available from their defining modules; compatibility aliases are retained for the 0.x series.

Invalid Python results expose typed `validation_issues` values such as
`missing_tracking_number` and `missing_recipient`. They are intentionally omitted from the
stable JSON contract below; JSON consumers can continue to rely on `is_valid`.

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

See the [development workflow](CONTRIBUTING.md#development-workflow) for environment setup and
the canonical list of required checks.

All committed PDF fixtures are generated from clearly fictional data. See
[tests/fixtures/README.md](tests/fixtures/README.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SUPPORT.md](SUPPORT.md) before opening an issue
or pull request.

## License

Released under the [MIT License](LICENSE).
