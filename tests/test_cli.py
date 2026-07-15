from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from form7_pdf_parser.cli import build_parser, main

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-form7.pdf"


def test_parse_command_writes_privacy_safe_json(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    exit_code = main(["parse", "--input", str(FIXTURE), "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["page_count"] == 2
    assert payload["pages"][0]["raw_text"] is None
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_parse_command_can_include_raw_text(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    exit_code = main(
        [
            "parse",
            "--input",
            str(FIXTURE),
            "--output",
            str(output),
            "--include-raw-text",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Synthetic Form 7 fixture" in payload["pages"][0]["raw_text"]


def test_annotate_command_writes_pdf(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay.json"
    output = tmp_path / "annotated.pdf"
    overlay.write_text(
        json.dumps({"overlays": [{"page_number": 1, "order_label": "Order #6904"}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "annotate",
            "--input",
            str(FIXTURE),
            "--overlay",
            str(overlay),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.read_bytes().startswith(b"%PDF-")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"overlays": ["invalid"]},
        {"overlays": [{"page_number": True, "order_label": "1"}]},
        {"overlays": [{"page_number": 1, "order_label": 1}]},
    ],
)
def test_annotate_command_rejects_invalid_overlay_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: object,
) -> None:
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(
        [
            "annotate",
            "--input",
            str(FIXTURE),
            "--overlay",
            str(overlay),
            "--output",
            str(tmp_path / "output.pdf"),
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().err.startswith("error:")


def test_annotate_command_rejects_oversized_overlay_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    overlay = tmp_path / "overlay.json"
    overlay.write_text(" " * (1024 * 1024 + 1), encoding="utf-8")

    exit_code = main(
        [
            "annotate",
            "--input",
            str(FIXTURE),
            "--overlay",
            str(overlay),
            "--output",
            str(tmp_path / "output.pdf"),
        ]
    )

    assert exit_code == 1
    assert "1 MiB" in capsys.readouterr().err


def test_parse_command_reports_processing_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("not a pdf", encoding="utf-8")

    exit_code = main(["parse", "--input", str(invalid), "--output", str(tmp_path / "result.json")])

    assert exit_code == 1
    assert "Unable to read" in capsys.readouterr().err


def test_cli_uses_argparse_exit_code_for_invalid_arguments() -> None:
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["parse", "--input", "input.pdf", "--max-pages", "0"])

    assert error.value.code == 2


def test_cli_accepts_positive_limits() -> None:
    args = build_parser().parse_args(
        [
            "parse",
            "--input",
            "input.pdf",
            "--output",
            "output.json",
            "--max-pages",
            "1",
        ]
    )

    assert args.max_pages == 1
