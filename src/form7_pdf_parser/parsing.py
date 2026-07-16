from __future__ import annotations

import re
from itertools import product
from typing import NamedTuple

from .models import PageValidationIssue, ParsedPage

_TRACKING_MARKER_PATTERN = re.compile(
    r"Оплачивается\s+при\s+вручении(?![^\W\d])",
    flags=re.IGNORECASE,
)
_TRACKING_LAYOUTS = tuple(
    layout for layout in product(range(5, 8), range(1, 4), range(4, 7), (1,)) if sum(layout) == 14
)
_TRACKING_LABEL_PATTERN = re.compile(r"^(?:№|N[oº]?\.?)\s*:?\s*", flags=re.IGNORECASE)
_TRACKING_DATE_PREAMBLE_PATTERN = re.compile(r"(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}")
_AMOUNT_PATTERN = re.compile(r"\b(?:руб|коп)\b", flags=re.IGNORECASE)
_PHONE_DASH_PATTERN = re.compile(r"[‐‑‒–—―−﹘﹣－]")
_PHONE_LABEL_PATTERN = re.compile(
    r"^(?:контактн\w*\s+)?(?:тел(?:ефон)?|phone)\b\.?\s*:?\s*"
    r"(?:(?:(?:получател|адресат)\w*|recipient)|(?:для\s+связи))?\s*:?\s*",
    flags=re.IGNORECASE,
)
_NON_RECIPIENT_PHONE_PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"(?:номер|код)\s+(?:заказ|заявк)\w*"
    r"|(?:контактн\w*\s+)?(?:тел(?:ефон)?|phone)\b\.?\s*:?\s*"
    r"(?:(?:служб|техническ|клиентск|customer|technical)\w*\s+){0,2}"
    r"(?:справочн|поддержк|support)\w*"
    r"|служб\w*\s+(?:(?:клиентск|техническ)\w*\s+)?(?:справочн|поддержк)\w*"
    r"|(?:customer\s+)?support(?:\s+service)?"
    r")\b",
    flags=re.IGNORECASE,
)
_PHONE_CHARACTERS_PATTERN = re.compile(r"[+\d\s().-]+")
_FORMATTED_PHONE_PATTERN = re.compile(
    r"^(?:(?:\+?7|8)[\s.-]*)?"
    r"(?:\(\d{3}\)[\s.-]*|\d{3}[\s.-]+)"
    r"(?:\d{7}|\d{3}[\s.-]+(?:\d{4}|\d{2}[\s.-]+\d{2}))$"
)
_COMPACT_PHONE_PATTERN = re.compile(r"^(?:\+7|[78])[\s.-]?\d{10}$")
_PHONE_CANDIDATE_START_PATTERN = re.compile(r"(?<!\d)(?=[+(\d])")


class _TrackingCandidate(NamedTuple):
    start_index: int
    end_index: int
    inferred_boundaries: int
    tracking_number: str
    end_line: int


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


def _tracking_tokens_match(tokens: list[tuple[str, int, bool]]) -> tuple[str, int] | None:
    candidates: list[_TrackingCandidate] = []
    for start_index in range(len(tokens)):
        for layout in _TRACKING_LAYOUTS:
            part_index = 0
            token_index = start_index
            layout_matches = True
            while part_index < len(layout) and token_index < len(tokens):
                digits, _, allows_trailing_suffix = tokens[token_index]
                consumed = 0
                while part_index < len(layout) and consumed < len(digits):
                    consumed += layout[part_index]
                    part_index += 1

                if consumed > len(digits):
                    layout_matches = False
                    break
                if consumed < len(digits) and not (
                    part_index == len(layout) and allows_trailing_suffix
                ):
                    layout_matches = False
                    break

                token_index += 1

            if not layout_matches or part_index != len(layout):
                continue

            tracking_number = _valid_tracking_number(
                ("".join(digits for digits, _, _ in tokens[start_index:token_index])[:14],)
            )
            if tracking_number is not None:
                candidates.append(
                    _TrackingCandidate(
                        start_index=start_index,
                        end_index=token_index,
                        inferred_boundaries=len(layout) - (token_index - start_index),
                        tracking_number=tracking_number,
                        end_line=tokens[token_index - 1][1] + 1,
                    )
                )

    if not candidates:
        return None

    candidates.sort(key=lambda candidate: (candidate.start_index, candidate.end_index))
    overlapping_candidates = [candidates[0]]
    overlap_end = candidates[0].end_index
    for candidate in candidates[1:]:
        if candidate.start_index >= overlap_end:
            break
        overlapping_candidates.append(candidate)
        overlap_end = max(overlap_end, candidate.end_index)

    selected_start = overlapping_candidates[0].start_index
    selected_candidates = [
        candidate for candidate in overlapping_candidates if candidate.start_index == selected_start
    ]
    inferred_boundaries = min(candidate.inferred_boundaries for candidate in selected_candidates)
    if inferred_boundaries > 0 and _TRACKING_DATE_PREAMBLE_PATTERN.fullmatch(
        tokens[selected_start][0]
    ):
        later_candidates = [
            candidate
            for candidate in overlapping_candidates
            if candidate.start_index > selected_start
            and candidate.inferred_boundaries < inferred_boundaries
        ]
        if later_candidates:
            selected_start = min(candidate.start_index for candidate in later_candidates)
            selected_candidates = [
                candidate
                for candidate in later_candidates
                if candidate.start_index == selected_start
            ]

    best_candidate = min(
        selected_candidates,
        key=lambda candidate: (
            candidate.inferred_boundaries,
            candidate.end_index,
        ),
    )
    return best_candidate.tracking_number, best_candidate.end_line


def _find_tracking_parts(
    lines: list[str],
    marker_end: int,
    marker_tail: str,
) -> tuple[str, int] | None:
    tokens: list[tuple[str, int, bool]] = []

    for line_index in range(marker_end, min(marker_end + 10, len(lines))):
        candidate = marker_tail if line_index == marker_end else lines[line_index]
        candidate = _TRACKING_LABEL_PATTERN.sub("", candidate.lstrip(" :—-"), count=1)
        numeric_prefix = re.match(r"[0-9\s]+", candidate)
        if numeric_prefix is None:
            if _AMOUNT_PATTERN.search(candidate):
                break
            continue

        remainder = candidate[numeric_prefix.end() :]
        has_trailing_amount = bool(_AMOUNT_PATTERN.search(remainder))
        line_tokens = numeric_prefix.group().split()
        for token_index, digits in enumerate(line_tokens):
            tokens.append(
                (
                    digits,
                    line_index,
                    token_index == len(line_tokens) - 1,
                )
            )

        if remainder.strip():
            if has_trailing_amount:
                break
            if tracking_match := _tracking_tokens_match(tokens):
                return tracking_match

    return _tracking_tokens_match(tokens)


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


def _strip_amount_prefix(prefix: str) -> str | None:
    amount_matches = tuple(_AMOUNT_PATTERN.finditer(prefix))
    if not amount_matches:
        return prefix
    return prefix[amount_matches[-1].end() :].lstrip(" :—-,") or None


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


def _has_phone_substring_after_numeric_prefix(line: str) -> bool:
    normalized_line = _PHONE_DASH_PATTERN.sub("-", line)
    for candidate_start in _PHONE_CANDIDATE_START_PATTERN.finditer(normalized_line):
        candidate_match = _PHONE_CHARACTERS_PATTERN.match(
            normalized_line,
            candidate_start.start(),
        )
        if candidate_match is None or _phone_digits(candidate_match.group().strip()) is None:
            continue
        prefix = normalized_line[: candidate_start.start()].strip()
        if prefix and re.search(r"[^\W\d_]", prefix) is None:
            return True
    return False


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
            if prefix is not None and re.search(r"[^\W\d_]", prefix) is None:
                continue
            if prefix is not None:
                prefix = _strip_amount_prefix(prefix)
            if prefix is not None:
                prefix = _PHONE_LABEL_PATTERN.sub("", prefix, count=1).strip() or None
            return phone_digits, prefix

    return None


def _is_split_non_recipient_phone(lines: list[str], phone_index: int) -> bool:
    return phone_index > 0 and bool(
        _NON_RECIPIENT_PHONE_PREFIX_PATTERN.match(lines[phone_index - 1])
    )


def _without_non_recipient_phone_lines(lines: list[str]) -> list[str]:
    recipient_lines: list[str] = []
    skip_split_phone = False
    for line in lines:
        if _NON_RECIPIENT_PHONE_PREFIX_PATTERN.match(line):
            skip_split_phone = True
            continue
        if _has_phone_substring_after_numeric_prefix(line):
            skip_split_phone = False
            continue
        if skip_split_phone and _phone_match(line) is not None:
            skip_split_phone = False
            continue
        skip_split_phone = False
        recipient_lines.append(line)
    return recipient_lines


def _find_recipient_phone(
    lines: list[str],
) -> tuple[int, str, int | None, str | None] | None:
    for amount_index in range(len(lines) - 1, -1, -1):
        if not _AMOUNT_PATTERN.search(lines[amount_index]):
            continue

        for phone_index in range(amount_index + 1, min(amount_index + 9, len(lines))):
            if _is_split_non_recipient_phone(lines, phone_index):
                continue
            if phone_match := _phone_match(lines[phone_index]):
                phone_digits, line_prefix = phone_match
                return phone_index, phone_digits, amount_index, line_prefix

    for phone_index in range(len(lines) - 1, -1, -1):
        if _is_split_non_recipient_phone(lines, phone_index):
            continue
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
    recipient_block = _without_non_recipient_phone_lines(recipient_block)

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
