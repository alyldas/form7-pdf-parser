from __future__ import annotations

import re

from .models import PageValidationIssue, ParsedPage

_TRACKING_MARKER = "Оплачивается при вручении"
_TRACKING_PATTERN = re.compile(
    r"Оплачивается\s+при\s+вручении\s*"
    r"([0-9]{5,7})\s*([0-9]{1,3})\s*([0-9]{4,6})\s*([0-9])",
    flags=re.IGNORECASE | re.DOTALL,
)
_AMOUNT_PATTERN = re.compile(r"\b(?:руб|коп)\b", flags=re.IGNORECASE)
_PHONE_LINE_PATTERN = re.compile(
    r"(?:(?P<label>(?:тел(?:ефон)?|phone)\.?\s*:?)\s*)?(?P<number>\+?[0-9()\-\s]+)",
    flags=re.IGNORECASE,
)
_TRACKING_FRAGMENT_PATTERN = re.compile(r"[0-9][0-9\s-]*")
_TRACKING_GROUP_LENGTHS = ((5, 7), (1, 3), (4, 6), (1, 1))
_WAYBILL_TRACKING_PATTERN = re.compile(
    r"^(?:[0-9]{14}|[0-9]{6}\s+[0-9]{2}\s+[0-9]{5}\s+[0-9])$",
    flags=re.MULTILINE,
)
_SECTION_PATTERN = re.compile(r"^(от\s+кого|кому)(?:\s*:\s*|\s+|$)(.*)$", re.IGNORECASE)
_POSTCODE_PATTERN = re.compile(r"(?<![0-9])[0-9]{6}(?![0-9])")
_PHONE_DASHES = str.maketrans(dict.fromkeys("‐‑‒–—−", "-"))


def normalize_lines(text: str) -> list[str]:
    return [line for raw in text.splitlines() if (line := re.sub(r"\s+", " ", raw).strip())]


def _section_caption(text: str) -> tuple[str, str] | None:
    match = _SECTION_PATTERN.fullmatch(" ".join(text.split()))
    return (match[1].casefold(), match[2]) if match is not None else None


def _waybill_sections(lines: list[str]) -> tuple[list[str], list[str], bool] | None:
    expanded: list[str] = []
    for line in lines:
        if (section := _section_caption(line)) is not None:
            expanded.append(section[0])
            if section[1]:
                expanded.append(section[1])
        else:
            expanded.append(line)
    markers = [line.casefold() for line in expanded]
    if "от кого" not in markers or "кому" not in markers:
        return None
    sender_index = markers.index("от кого")
    recipient_index = markers.index("кому")
    if sender_index >= recipient_index:
        return None
    header = expanded[:sender_index]
    recipient = expanded[recipient_index + 1 :]
    # Legacy forms can also contain sender/recipient captions. Require new-layout
    # evidence before giving those captions priority over the legacy payment block.
    legacy_payment = _TRACKING_MARKER.casefold() in " ".join(recipient).casefold()
    if legacy_payment and not _WAYBILL_TRACKING_PATTERN.search("\n".join(header)):
        return None
    multiple = markers.count("от кого") > 1 or markers.count("кому") > 1
    return header, recipient, multiple


def _valid_tracking_number(parts: list[str] | tuple[str, ...]) -> str | None:
    if len(parts) != len(_TRACKING_GROUP_LENGTHS):
        return None
    if any(
        not minimum <= len(part) <= maximum
        for part, (minimum, maximum) in zip(parts, _TRACKING_GROUP_LENGTHS, strict=True)
    ):
        return None

    candidate = "".join(parts)
    return candidate if len(candidate) == 14 and candidate.isdigit() else None


def parse_tracking_number(text: str, lines: list[str] | None = None) -> str | None:
    """Best-effort extraction of one unambiguous 14-digit tracking number."""
    normalized_lines = lines if lines is not None else normalize_lines(text)
    if (sections := _waybill_sections(normalized_lines)) is not None:
        header, _recipient, multiple = sections
        return None if multiple else _parse_waybill_tracking(header)
    return _parse_legacy_tracking(text, normalized_lines)


def _parse_waybill_tracking(header: list[str]) -> str | None:
    candidates = {
        re.sub(r"\s+", "", match.group())
        for match in _WAYBILL_TRACKING_PATTERN.finditer("\n".join(header))
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _parse_legacy_tracking(text: str, lines: list[str]) -> str | None:
    direct_candidates = {
        candidate
        for match in _TRACKING_PATTERN.finditer(text)
        if (candidate := _valid_tracking_number(match.groups())) is not None
    }
    if direct_candidates:
        return next(iter(direct_candidates)) if len(direct_candidates) == 1 else None

    marker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _TRACKING_MARKER.casefold() in line.casefold()
        ),
        None,
    )
    if marker_index is None:
        return None

    parts: list[str] = []
    for line in lines[marker_index + 1 : marker_index + 10]:
        if _TRACKING_FRAGMENT_PATTERN.fullmatch(line) is None:
            continue
        digits = re.sub(r"\D+", "", line)
        if re.fullmatch(r"\d{1,7}", digits or ""):
            parts.append(digits)

    candidates: set[str] = set()
    for start in range(len(parts) - len(_TRACKING_GROUP_LENGTHS) + 1):
        candidate = _valid_tracking_number(parts[start : start + len(_TRACKING_GROUP_LENGTHS)])
        if candidate is not None:
            candidates.add(candidate)

    return next(iter(candidates)) if len(candidates) == 1 else None


def _phone_digit_limit(number: str, digits: str) -> int:
    if number.startswith("+") and not digits.startswith("7"):
        return 0
    return 11 if digits.startswith(("7", "8")) else 10


def _parse_phone_line(line: str) -> str | None:
    match = _PHONE_LINE_PATTERN.fullmatch(line)
    if match is None:
        return None

    number = match["number"]
    digits = re.sub(r"\D+", "", number)
    maximum_digits = _phone_digit_limit(number, digits)
    if not maximum_digits:
        return None
    # Explicit country prefixes cannot be reinterpreted as national numbers.
    if number.startswith("+") or re.match(r"^[78](?:\s|\(|-)", number):
        return digits[-10:] if len(digits) == 11 else None
    return digits[-10:] if len(digits) in (10, maximum_digits) else None


def _join_lines(lines: list[str]) -> str | None:
    return " ".join(" ".join(lines).split()) or None


def _waybill_phone(lines: list[str], index: int) -> tuple[str | None, int]:
    line = lines[index].translate(_PHONE_DASHES)
    phone = _parse_phone_line(line)
    consumed = 1
    match = _PHONE_LINE_PATTERN.fullmatch(line)
    if match is None:
        return phone, consumed

    line = match["number"]
    digits = re.sub(r"\D+", "", line)
    maximum_digits = _phone_digit_limit(line, digits)
    if not maximum_digits or (match["label"] is None and maximum_digits != 11):
        return phone, consumed
    digit_count = len(digits)
    for end in range(index + 1, len(lines)):
        if digit_count >= maximum_digits:
            break
        fragment = lines[end].translate(_PHONE_DASHES)
        continuation = _PHONE_LINE_PATTERN.fullmatch(fragment)
        if continuation is None or continuation["label"] is not None or "+" in fragment:
            break
        fragment_digits = re.sub(r"\D+", "", fragment)
        if not fragment_digits or digit_count + len(fragment_digits) > maximum_digits:
            break
        # Do not invent prefix-separating whitespace at a line break.
        line += fragment
        digit_count += len(fragment_digits)
        if (candidate := _parse_phone_line(line)) is not None:
            phone = candidate
            consumed = end - index + 1
            # Prefer a complete eleven-digit country-prefixed number over a
            # ten-digit intermediate candidate; retain national numbers otherwise.
    return phone, consumed


def _waybill_phones(lines: list[str]) -> tuple[list[str], set[str], int | None]:
    remaining: list[str] = []
    phones: set[str] = set()
    phone_boundary = None
    address_seen = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.fullmatch(r"(?:Order\s*#|Заказ\s*№)\s*[0-9]+", line, re.IGNORECASE):
            break
        # Stop at the routing postcode before numeric footer lines can be
        # mistaken for a continuation of a phone number.
        if address_seen and re.fullmatch(r"[0-9]{6}", line):
            remaining.append(line)
            break
        phone, consumed = _waybill_phone(lines, index)
        if phone is not None:
            phones.add(phone)
            if phone_boundary is None:
                phone_boundary = len(remaining)
        else:
            remaining.append(line)
            if (
                not re.fullmatch(r"[0-9]{6}", line)
                and (phones or re.search(r"[0-9]", line))
                and not _PHONE_LINE_PATTERN.fullmatch(line.translate(_PHONE_DASHES))
            ):
                address_seen = True
        index += consumed
    return remaining, phones, phone_boundary


def _parse_waybill_recipient(
    lines: list[str],
) -> tuple[str | None, str | None, str | None, tuple[PageValidationIssue, ...]]:
    remaining, phones, phone_boundary = _waybill_phones(lines)
    address_index = next(
        (index for index, line in enumerate(remaining) if re.search(r"[0-9]", line)),
        len(remaining),
    )
    if phone_boundary is not None:
        address_index = min(address_index, phone_boundary)
    issues: list[PageValidationIssue] = []
    if len(phones) > 1:
        issues.append(PageValidationIssue.AMBIGUOUS_RECIPIENT_PHONE)
    phone = next(iter(phones)) if len(phones) == 1 else None
    # A numeric street line or postcode does not prove that all preceding lines
    # belong to the name. Only a phone delimiter separates a multiline name
    # from a digit-free locality without guessing from a locality dictionary.
    if address_index > 1 and (
        phone_boundary != address_index
        or address_index == len(remaining)
        or (address_index == len(remaining) - 1 and re.fullmatch(r"[0-9]{6}", remaining[-1]))
    ):
        issues.append(PageValidationIssue.AMBIGUOUS_RECIPIENT)
        return None, None, phone, tuple(issues)
    name = _join_lines(remaining[:address_index])
    address_lines = remaining[address_index:]

    # The routing postcode is printed separately too. Preserve it if it differs
    # from the address, rather than silently choosing between conflicting values.
    if len(address_lines) > 1 and re.fullmatch(r"[0-9]{6}", address_lines[-1]):
        postcode = address_lines[-1]
        if postcode in _POSTCODE_PATTERN.findall(" ".join(address_lines[:-1])):
            address_lines = address_lines[:-1]

    return name, _join_lines(address_lines), phone, tuple(issues)


def parse_recipient_name_address_phone(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Prefer explicit waybill sections, then try the legacy phone-ending block."""
    if (sections := _waybill_sections(lines)) is not None:
        _header, recipient, multiple = sections
        if multiple:
            return None, None, None
        name, address, phone, _issues = _parse_waybill_recipient(recipient)
        return name, address, phone
    return _parse_legacy_recipient(lines)


def _parse_legacy_recipient(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    for phone_index in range(len(lines) - 1, -1, -1):
        phone = _parse_phone_line(lines[phone_index])
        if phone is None:
            continue
        recipient_block: list[str] = []
        for line in reversed(lines[max(phone_index - 8, 0) : phone_index]):
            if _AMOUNT_PATTERN.search(line):
                break
            recipient_block.append(line)
        recipient_block.reverse()
        name = recipient_block[0] if recipient_block else None
        return name, _join_lines(recipient_block[1:]), phone
    return None, None, None


def parse_page(text: str, page_number: int, *, include_raw_text: bool = False) -> ParsedPage:
    """Parse normalized fields and validation diagnostics from one extracted text page."""
    if page_number < 1:
        raise ValueError("page_number must be at least 1")

    lines = normalize_lines(text)
    sections = _waybill_sections(lines)
    recipient_issues: tuple[PageValidationIssue, ...] = ()
    multiple = False
    if sections is None:
        tracking_number = _parse_legacy_tracking(text, lines)
        recipient_name, recipient_address, recipient_phone = _parse_legacy_recipient(lines)
    else:
        header, recipient, multiple = sections
        if multiple:
            tracking_number = recipient_name = recipient_address = recipient_phone = None
        else:
            tracking_number = _parse_waybill_tracking(header)
            recipient_name, recipient_address, recipient_phone, recipient_issues = (
                _parse_waybill_recipient(recipient)
            )
    postcodes = set(_POSTCODE_PATTERN.findall(recipient_address or ""))
    recipient_postcode = next(iter(postcodes)) if len(postcodes) == 1 else None
    checks = [
        (tracking_number is None, PageValidationIssue.MISSING_TRACKING_NUMBER),
        (recipient_name is None and recipient_phone is None, PageValidationIssue.MISSING_RECIPIENT),
    ]
    if sections is not None:
        checks.extend(
            [
                (recipient_name is None, PageValidationIssue.MISSING_RECIPIENT_NAME),
                (recipient_phone is None, PageValidationIssue.MISSING_RECIPIENT_PHONE),
                (
                    not recipient_address
                    or not re.search(r"[^\W\d_]", recipient_address, re.UNICODE),
                    PageValidationIssue.MISSING_RECIPIENT_ADDRESS,
                ),
                (not postcodes, PageValidationIssue.MISSING_RECIPIENT_POSTCODE),
                (len(postcodes) > 1, PageValidationIssue.CONFLICTING_POSTCODES),
            ]
        )
    validation_issues = (
        (PageValidationIssue.MULTIPLE_SHIPMENTS,)
        if multiple
        else tuple(issue for missing, issue in checks if missing) + recipient_issues
    )

    return ParsedPage(
        page_number=page_number,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        recipient_address=recipient_address,
        tracking_number=tracking_number,
        raw_text=text.strip() or None if include_raw_text else None,
        is_valid=not validation_issues,
        validation_issues=validation_issues,
        recipient_postcode=recipient_postcode,
    )
