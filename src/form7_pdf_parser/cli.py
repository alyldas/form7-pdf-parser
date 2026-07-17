from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ._version import __version__
from .annotation import annotate_pdf
from .atomic import atomic_write_json
from .exceptions import Form7Error, OverlayError
from .models import Overlay
from .pdf import DEFAULT_MAX_FILE_SIZE, DEFAULT_MAX_PAGES, parse_pdf

MAX_OVERLAY_JSON_SIZE = 1024 * 1024


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _load_overlays(path: Path) -> list[Overlay]:
    with path.open("rb") as handle:
        raw_payload = handle.read(MAX_OVERLAY_JSON_SIZE + 1)

    if len(raw_payload) > MAX_OVERLAY_JSON_SIZE:
        raise OverlayError("Overlay JSON exceeds the 1 MiB size limit")

    payload: Any = json.loads(raw_payload.decode("utf-8"))

    raw_overlays = payload.get("overlays") if isinstance(payload, dict) else None
    if not isinstance(raw_overlays, list):
        raise OverlayError("Overlay JSON must contain an overlays array")

    overlays: list[Overlay] = []
    for item in raw_overlays:
        if not isinstance(item, dict):
            raise OverlayError("Each overlay must be an object")
        page_number = item.get("page_number")
        order_label = item.get("order_label")
        if not isinstance(page_number, int) or isinstance(page_number, bool):
            raise OverlayError("Overlay page_number must be an integer")
        if not isinstance(order_label, str):
            raise OverlayError("Overlay order_label must be a string")
        overlays.append(Overlay(page_number=page_number, order_label=order_label))

    return overlays


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="form7-pdf",
        description="Parse and annotate text-based Form 7 shipping PDFs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_command = subparsers.add_parser("parse", help="Parse PDF pages into JSON")
    parse_command.add_argument("--input", required=True, type=Path, help="Input PDF path")
    parse_command.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parse_command.add_argument(
        "--include-raw-text",
        action="store_true",
        help="Include full extracted page text; may contain personal data",
    )
    parse_command.add_argument("--max-pages", type=_positive_int, default=DEFAULT_MAX_PAGES)
    parse_command.add_argument(
        "--max-file-size-mib",
        type=_positive_int,
        default=DEFAULT_MAX_FILE_SIZE // (1024 * 1024),
    )

    annotate_command = subparsers.add_parser("annotate", help="Add page labels to a PDF")
    annotate_command.add_argument("--input", required=True, type=Path, help="Input PDF path")
    annotate_command.add_argument("--overlay", required=True, type=Path, help="Overlay JSON path")
    annotate_command.add_argument("--output", required=True, type=Path, help="Output PDF path")
    annotate_command.add_argument("--max-pages", type=_positive_int, default=DEFAULT_MAX_PAGES)
    annotate_command.add_argument(
        "--max-file-size-mib",
        type=_positive_int,
        default=DEFAULT_MAX_FILE_SIZE // (1024 * 1024),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        max_file_size = args.max_file_size_mib * 1024 * 1024
        if args.command == "parse":
            if args.output.exists() and args.input.samefile(args.output):
                raise ValueError("Input PDF and output JSON paths must be different")

            result = parse_pdf(
                args.input,
                include_raw_text=args.include_raw_text,
                max_pages=args.max_pages,
                max_file_size=max_file_size,
            )
            atomic_write_json(args.output, result.as_dict())
            return 0

        overlays = _load_overlays(args.overlay)
        annotate_pdf(
            args.input,
            args.output,
            overlays,
            max_pages=args.max_pages,
            max_file_size=max_file_size,
        )
        return 0
    except (Form7Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
