from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PageValidationIssue(StrEnum):
    """Stable reasons why a parsed page does not satisfy the Form 7 contract."""

    MISSING_TRACKING_NUMBER = "missing_tracking_number"
    MISSING_RECIPIENT = "missing_recipient"


@dataclass(frozen=True, slots=True)
class ParsedPage:
    """Typed result for one PDF page; raw text is privacy-sensitive and opt-in."""

    page_number: int
    recipient_name: str | None
    recipient_phone: str | None
    recipient_address: str | None
    tracking_number: str | None
    raw_text: str | None
    is_valid: bool
    validation_issues: tuple[PageValidationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON shape, intentionally excluding diagnostic issues."""
        return {
            "page_number": self.page_number,
            "recipient_name": self.recipient_name,
            "recipient_phone": self.recipient_phone,
            "recipient_address": self.recipient_address,
            "tracking_number": self.tracking_number,
            "raw_text": self.raw_text,
            "is_valid": self.is_valid,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Immutable collection of parsed page results."""

    pages: tuple[ParsedPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def as_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "pages": [page.as_dict() for page in self.pages],
        }


@dataclass(frozen=True, slots=True)
class Overlay:
    """A sanitized order label requested for one-based PDF page number."""

    page_number: int
    order_label: str
