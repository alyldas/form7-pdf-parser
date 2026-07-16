from __future__ import annotations

import re

from .models import PageValidationIssue, ParsedPage

_TRACKING_MARKER_PATTERN = re.compile(
    r"\bОплачивается\s+при\s+вручении(?![^\W\d])",
    flags=re.IGNORECASE,
)
_TRACKING_PART_LENGTHS = ((5, 7), (1, 3), (4, 6), (1, 1))
_AMOUNT_PATTERN = re.compile(r"\b(?:руб|коп)\b", flags=re.IGNORECASE)
_PHONE_DASH_PATTERN = re.compile(r"[‐‑‒–—―−﹘﹣－]")
_PHONE_LABEL_PATTERN = re.compile(
    r"^(?:тел(?:ефон)?|phone)\.?\s*:?\s*"
    r"(?:(?:получател|адресат)\w*|recipient)?\s*:?\s*",
    flags=re.IGNORECASE,
)
_NON_RECIPIENT_PHONE_PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"(?:номер|код)\s+(?:заказ|заявк)\w*"
    r"|(?:тел(?:ефон)?|phone)\.?\s*:?\s*"
    r"(?:справочн|поддержк|support)\w*"
    r")\b",
    flags=re.IGNORECASE,
)
_PHONE_CHARACTERS_PATTERN = re.compile(r"[+\d\s().-]+")
_FORMATTED_PHONE_PATTERN = re.compile(
    r"^(?:(?:\+?7|8)[\s.-]*)?"
    r"(?:"
    r"\(\d{3}\)[\s.-]*\d{3}[\s.-]*(?:\d{4}|\d{2}[\s.-]*\d{2})"
    r"|\d{3}[\s.-]+\d{3}[\s.-]+(?:\d{4}|\d{2}[\s.-]+\d{2})"
    r")$"
)
_COMPACT_PHONE_PATTERN = re.compile(r"^(?:\+7|[78])[\s.-]?\d{10}$")
_PHONE_CANDIDATE_START_PATTERN = re.compile(r"(?<!\d)(?=[+(\d])")


def normalize_lines(text: str) -> list[str]:
    return [line for raw in text.splitlines() if (line := re.sub(r"\s+", " ", raw).strip())]


def _valid_tracking_number(parts: list[str] | tuple[str, ...]) -> str | None:
    candidate = "".join(parts)
    return candidate if len(candidate) == 14 and candidate.isdigit() else None


def _tracking_marker_matches(lines: list[str]) -> list[tuple[int, str]]:
    joined_lines = "\n".join(lines)
    matches: list[tuple[int, str]] = []
    for match in _TRACKING_MARKER_PATTERN.finditer(joined_lines):
        marker_end = joined_lines.count("\n", 0, match.end())
        marker_tail = joined_lines[match.end() :].split("\n", 1)[0]
        matches.append((marker_end, marker_tail))

    return matches


def _find_tracking_parts(
    lines: list[str],
    marker_end: int,
    marker_tail: str,
) -> tuple[str, int] | None:
    parts: list[tuple[int, str]] = []

    for line_index in range(marker_end, min(marker_end + 10, len(lines))):
        candidate = marker_tail if line_index == marker_end else lines[line_index]
        candidate = candidate.lstrip(" :—-")
        numeric_prefix = re.match(r"[0-9\s]+", candidate)
        if numeric_prefix is None:
            if _AMOUNT_PATTERN.search(candidate):
                break
            continue

        for digits in numeric_prefix.group().split():
            if len(digits) == 14:
                return digits, line_index + 1
            if not re.fullmatch(r"\d{1,7}", digits):
                continue

            parts.append((line_index, digits))
            candidate_parts = parts[-4:]
            if len(candidate_parts) < 4 or not all(
                minimum <= len(part) <= maximum
                for (_, part), (minimum, maximum) in zip(
                    candidate_parts,
                    _TRACKING_PART_LENGTHS,
                    strict=True,
                )
            ):
                continue

            tracking_number = _valid_tracking_number([part for _, part in candidate_parts])
            if tracking_number is not None:
                return tracking_number, candidate_parts[-1][0] + 1

        if candidate[numeric_prefix.end() :].strip():
            break

    return None


def parse_tracking_number(text: str, lines: list[str] | None = None) -> str | None:
    normalized_lines = lines if lines is not None else normalize_lines(text)
    for marker_end, marker_tail in _tracking_marker_matches(normalized_lines):
        tracking_match = _find_tracking_parts(normalized_lines, marker_end, marker_tail)
        if tracking_match is not None:
            return tracking_match[0]
    return None


def _join_lines(lines: list[str]) -> str | None:
    compact = re.sub(r"\s+", " ", " ".join(line.strip() for line in lines if line.strip()))
    return compact.strip() or None


def _phone_digits(line: str) -> str | None:
    line = _PHONE_DASH_PATTERN.sub("-", line)
    label_match = _PHONE_LABEL_PATTERN.match(line)
    value = line[label_match.end() :] if label_match is not None else line
    if not _PHONE_CHARACTERS_PATTERN.fullmatch(value):
        return None

    digits = re.sub(r"\D+", "", value)
    if len(digits) not in (10, 11):
        return None
    if label_match is None and not (
        _FORMATTED_PHONE_PATTERN.fullmatch(value) or _COMPACT_PHONE_PATTERN.fullmatch(value)
    ):
        return None
    return digits[-10:]


def _phone_match(line: str) -> tuple[str, str | None] | None:
    normalized_line = _PHONE_DASH_PATTERN.sub("-", line)
    if phone_digits := _phone_digits(normalized_line):
        return phone_digits, None

    for candidate_start in _PHONE_CANDIDATE_START_PATTERN.finditer(normalized_line):
        candidate_match = _PHONE_CHARACTERS_PATTERN.match(
            normalized_line,
            candidate_start.start(),
        )
        if candidate_match is None:
            continue
        candidate = candidate_match.group().strip()
        if phone_digits := _phone_digits(candidate):
            prefix = line[: candidate_start.start()].strip() or None
            if prefix is not None and _NON_RECIPIENT_PHONE_PREFIX_PATTERN.match(prefix):
                continue
            return phone_digits, prefix

    return None


def _find_recipient_phone(
    lines: list[str],
) -> tuple[int, str, int | None, str | None] | None:
    for amount_index in range(len(lines) - 1, -1, -1):
        if not _AMOUNT_PATTERN.search(lines[amount_index]):
            continue

        for phone_index in range(amount_index + 1, min(amount_index + 9, len(lines))):
            if phone_match := _phone_match(lines[phone_index]):
                phone_digits, line_prefix = phone_match
                return phone_index, phone_digits, amount_index, line_prefix

    for phone_index in range(len(lines) - 1, -1, -1):
        if phone_match := _phone_match(lines[phone_index]):
            phone_digits, line_prefix = phone_match
            return phone_index, phone_digits, None, line_prefix

    return None


def _trim_tracking_preamble(lines: list[str]) -> list[str]:
    marker_matches = _tracking_marker_matches(lines)
    if not marker_matches:
        return lines

    marker_end, marker_tail = marker_matches[-1]
    tracking_match = _find_tracking_parts(lines, marker_end, marker_tail)
    if tracking_match is None:
        return lines[marker_end + 1 :]
    return lines[tracking_match[1] :]


def parse_recipient_name_address_phone(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    phone_match = _find_recipient_phone(lines)
    if phone_match is None:
        return None, None, None

    phone_index, phone_digits, amount_index, phone_line_prefix = phone_match
    search_start = max(phone_index - 8, 0)
    recipient_block = (
        lines[amount_index + 1 : phone_index]
        if amount_index is not None
        else _trim_tracking_preamble(lines[search_start:phone_index])
    )
    if phone_line_prefix is not None:
        recipient_block.append(phone_line_prefix)
    recipient_block = [
        line for line in recipient_block if _NON_RECIPIENT_PHONE_PREFIX_PATTERN.match(line) is None
    ]

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
    if page_number < 1:
        raise ValueError("page_number must be at least 1")

    lines = normalize_lines(text)
    tracking_number = parse_tracking_number(text, lines)
    recipient_name, recipient_address, recipient_phone = parse_recipient_name_address_phone(lines)
    validation_issues = _page_validation_issues(
        tracking_number,
        recipient_name,
        recipient_phone,
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
    )
