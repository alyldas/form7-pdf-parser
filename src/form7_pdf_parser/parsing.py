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
    r"(?:(?:тел(?:ефон)?|phone)\.?\s*:?\s*)?\+?[0-9()\-\s]+",
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


def _waybill_sections(lines: list[str]) -> tuple[list[str], list[str], bool] | None:
    expanded: list[str] = []
    for line in lines:
        if (match := _SECTION_PATTERN.fullmatch(line)) is not None:
            expanded.append(" ".join(match[1].casefold().split()))
            if match[2]:
                expanded.append(match[2])
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
    legacy_payment = any(_TRACKING_MARKER.casefold() in line.casefold() for line in recipient)
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
        if sections[2]:
            return None
        waybill_candidates = {
            re.sub(r"\s+", "", match.group())
            for match in _WAYBILL_TRACKING_PATTERN.finditer("\n".join(sections[0]))
        }
        return next(iter(waybill_candidates)) if len(waybill_candidates) == 1 else None

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
            for index, line in enumerate(normalized_lines)
            if _TRACKING_MARKER.casefold() in line.casefold()
        ),
        None,
    )
    if marker_index is None:
        return None

    parts: list[str] = []
    for line in normalized_lines[marker_index + 1 : marker_index + 10]:
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


def _parse_phone_line(line: str) -> str | None:
    if _PHONE_LINE_PATTERN.fullmatch(line) is None:
        return None

    digits = re.sub(r"\D+", "", line)
    if "+" in line and not digits.startswith("7"):
        return None
    if len(digits) == 11 and digits[0] in "78":
        return digits[-10:]
    if len(digits) == 10:
        return digits
    return None


def _join_lines(lines: list[str]) -> str | None:
    compact = re.sub(r"\s+", " ", " ".join(line.strip() for line in lines if line.strip()))
    return compact.strip() or None


def _find_amount_line(lines: list[str], phone_index: int, search_start: int) -> int | None:
    for index in range(phone_index - 1, search_start - 1, -1):
        if _AMOUNT_PATTERN.search(lines[index]):
            return index
    return None


def _waybill_content(lines: list[str]) -> list[str]:
    content: list[str] = []
    address_seen = False
    phone_seen = False
    for line in lines:
        if re.fullmatch(r"(?:Order\s*#|Заказ\s*№)\s*[0-9]+", line, re.IGNORECASE):
            break
        content.append(line)
        if re.fullmatch(r"[0-9]{6}", line):
            if address_seen:
                break
        elif _parse_phone_line(line.translate(_PHONE_DASHES)) is not None:
            phone_seen = True
        elif (phone_seen or re.search(r"[0-9]", line)) and not _PHONE_LINE_PATTERN.fullmatch(
            line.translate(_PHONE_DASHES)
        ):
            address_seen = True
    return content


def _waybill_phones(lines: list[str]) -> tuple[list[str], set[str], int | None]:
    remaining: list[str] = []
    phones: set[str] = set()
    phone_boundary = None
    index = 0
    while index < len(lines):
        line = lines[index].translate(_PHONE_DASHES)
        phone = _parse_phone_line(line)
        consumed = 1
        # Join only numeric phone fragments; never consume an address line.
        if phone is None and re.match(r"^(?:\+7|8)\b", line):
            for end in range(index + 1, min(index + 3, len(lines))):
                fragment = lines[end].translate(_PHONE_DASHES)
                if _PHONE_LINE_PATTERN.fullmatch(fragment) is None:
                    break
                line += " " + fragment
                if (phone := _parse_phone_line(line)) is not None:
                    consumed = end - index + 1
                    break
        if phone is None:
            remaining.append(lines[index])
        else:
            phones.add(phone)
            if phone_boundary is None:
                phone_boundary = len(remaining)
        index += consumed
    return remaining, phones, phone_boundary


def _parse_waybill_recipient(
    lines: list[str],
) -> tuple[str | None, str | None, str | None, tuple[PageValidationIssue, ...]]:
    remaining, phones, phone_boundary = _waybill_phones(_waybill_content(lines))
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
    # Without a phone delimiter or an address beginning before the final postcode,
    # plain text cannot distinguish a wrapped name from an unlabelled locality.
    if address_index > 1 and (
        address_index == len(remaining)
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
        if re.search(rf"(?<![0-9]){postcode}(?![0-9])", " ".join(address_lines[:-1])):
            address_lines = address_lines[:-1]

    return name, _join_lines(address_lines), phone, tuple(issues)


def parse_recipient_name_address_phone(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Prefer explicit waybill sections, then try the legacy phone-ending block."""
    if (sections := _waybill_sections(lines)) is not None:
        if sections[2]:
            return None, None, None
        name, address, phone, _ambiguous_phone = _parse_waybill_recipient(sections[1])
        return name, address, phone

    phone_index: int | None = None
    phone_digits: str | None = None

    for index in range(len(lines) - 1, -1, -1):
        phone_digits = _parse_phone_line(lines[index])
        if phone_digits is not None:
            phone_index = index
            break

    if phone_index is None or phone_digits is None:
        return None, None, None

    search_start = max(phone_index - 8, 0)
    amount_index = _find_amount_line(lines, phone_index, search_start)
    recipient_block = (
        lines[amount_index + 1 : phone_index]
        if amount_index is not None
        else lines[search_start:phone_index]
    )

    if not recipient_block:
        return None, None, phone_digits

    return recipient_block[0], _join_lines(recipient_block[1:]), phone_digits


def _page_validation_issues(
    tracking_number: str | None,
    recipient_name: str | None,
    recipient_phone: str | None,
) -> tuple[PageValidationIssue, ...]:
    issues: list[PageValidationIssue] = []
    if tracking_number is None:
        issues.append(PageValidationIssue.MISSING_TRACKING_NUMBER)
    if recipient_name is None and recipient_phone is None:
        issues.append(PageValidationIssue.MISSING_RECIPIENT)
    return tuple(issues)


def parse_page(text: str, page_number: int, *, include_raw_text: bool = False) -> ParsedPage:
    """Parse normalized fields and validation diagnostics from one extracted text page."""
    if page_number < 1:
        raise ValueError("page_number must be at least 1")

    lines = normalize_lines(text)
    tracking_number = parse_tracking_number(text, lines)
    recipient_name, recipient_address, recipient_phone = parse_recipient_name_address_phone(lines)
    postcodes = set(_POSTCODE_PATTERN.findall(recipient_address or ""))
    recipient_postcode = next(iter(postcodes)) if len(postcodes) == 1 else None
    validation_issues = _page_validation_issues(
        tracking_number,
        recipient_name,
        recipient_phone,
    )
    if (sections := _waybill_sections(lines)) is not None:
        if sections[2]:
            validation_issues = (PageValidationIssue.MULTIPLE_SHIPMENTS,)
        else:
            issues = list(validation_issues)
            for missing, issue in (
                (recipient_name is None, PageValidationIssue.MISSING_RECIPIENT_NAME),
                (recipient_phone is None, PageValidationIssue.MISSING_RECIPIENT_PHONE),
                (
                    not recipient_address
                    or not re.search(r"[^\W\d_]", recipient_address, re.UNICODE),
                    PageValidationIssue.MISSING_RECIPIENT_ADDRESS,
                ),
                (not postcodes, PageValidationIssue.MISSING_RECIPIENT_POSTCODE),
                (len(postcodes) > 1, PageValidationIssue.CONFLICTING_POSTCODES),
            ):
                if missing:
                    issues.append(issue)
            issues.extend(_parse_waybill_recipient(sections[1])[3])
            validation_issues = tuple(issues)

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
