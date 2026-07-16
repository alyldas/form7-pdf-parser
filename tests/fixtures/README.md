# Synthetic fixture

`synthetic-form7.pdf` is generated from fictional data by
[`tools/generate_fixture.py`](../../tools/generate_fixture.py). It is not derived from a
production document and intentionally contains an all-zero phone and tracking number, a
nonexistent address, and no carrier branding.

The PDF embeds a subset of Noto Sans solely to preserve Cyrillic text extraction. Noto Sans is
licensed under the SIL Open Font License 1.1; see [`OFL.txt`](OFL.txt).

`parsing-cases.json` contains fictional table-driven text layouts for exercising parser
heuristics independently from PDF text extraction.

To regenerate the fixture, provide a local Noto Sans Regular font file:

```bash
python tools/generate_fixture.py \
  --font /path/to/NotoSans-Regular.ttf \
  --output tests/fixtures/synthetic-form7.pdf
```
