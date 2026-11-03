# Supported formats

This reference describes the existing text heuristics and label placement rules.
See the [README](../README.md) for installation, CLI usage and the stable JSON contract.

## Format detection

Formats are detected per page, so one PDF can contain both layouts. Explicit waybill
sections take priority when the header contains tracking or no legacy recipient payment
block is present. Sender details are never used as a fallback for an empty `КОМУ` section.
The JSON fields are the same for both formats.

## Waybill fields

### Tracking number

Tracking must appear before `ОТ КОГО`, as 14 contiguous digits or groups of
6, 2, 5, and 1 digits. Conflicting tracking numbers are rejected.

### Recipient name and address

Recipients are read under `КОМУ`. Inline section captions and wrapped names are supported.
Names and addresses are separated by phone/postcode and numeric address boundaries,
not a dictionary of locality names.

An unresolved wrapped-name/address boundary is reported as `ambiguous_recipient` instead
of guessed. Multiple name/locality lines before a numeric street or postcode require a
phone delimiter; otherwise neither the name nor address is returned as a guessed value.

### Phone number

Phones may appear before or after the address. Wrapped numbers and Unicode dashes are
supported. Explicit `+7` or separated `7`/`8` prefixes require eleven digits in total.
Numeric fragments may span multiple lines without a fixed three-line limit.

After the address, six bare digits are a routing postcode. Use `+7` or a phone label to
distinguish a wrapped phone that would otherwise start with six bare digits.

### Postcode and end of recipient block

An initial standalone postcode is retained; a postcode after the address ends the block.
Repeated routing postcodes are removed only when they already appear in the address.
Different postcodes are preserved without choosing which one is correct.

Trailing `Заказ № ...` and older `Order #...` labels are excluded when the routing postcode
is absent.

## Label placement

The library draws `Заказ № <number>` as shared vector outlines of Noto Sans Bold, without
embedding a label font. Labels remain sharp at any zoom level but are not extractable text.
Source fonts and images are reused across pages. Compact waybills use the
header to the right of the logo, even on an A4 sheet; Form 7 uses the free area beside the
title. Header anchors adapt to scaling and CropBox offsets. Labels shrink from 12 pt down
to 8 pt if needed, and remain at least 7 mm above a detected recipient caption. Pages without
a recognized header use the previous top-right placement, subject to the same space check.

Before writing, PDFium renders the proposed area at 216 dpi with a 2 pt safety margin.
Any visible content in that area causes `OverlayError`; the library never erases an existing
number or searches for an arbitrary alternative position. Labels outside the visible page,
unfittable labels, and multiple forms on one page are rejected. On failure, an existing output
file remains unchanged. These checks verify placement, not postal acceptance of every PDF.

### Reference geometry

Header measurements live in `_LEGACY_HEADER` and `_WAYBILL_HEADER` in
[annotation.py](../src/form7_pdf_parser/annotation.py). All distances use PDF points
(1/72 inch). The reference title sizes are 21.5 pt for Form 7 and 9 pt for compact
waybills. Offsets locate the label baseline relative to the detected title origin;
the actual title height scales them with the form. CropBox offsets convert page
coordinates to overlay coordinates. The fallback uses visible page dimensions.
These values preserve the established positions checked by the synthetic
[placement tests](../tests/test_placement.py); they are not an official postal specification.
