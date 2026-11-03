from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from form7_pdf_parser.atomic import _sync_directory, atomic_output_path, atomic_write_json


@pytest.mark.parametrize("failure", ["write", "sync"])
@pytest.mark.parametrize("encoding", [None, "utf-8"])
def test_atomic_output_preserves_output_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, encoding: str | None
) -> None:
    destination = tmp_path / "result"
    destination.write_bytes(b"previous result")

    def fail_sync(descriptor: int) -> None:
        raise OSError("sync failed")

    if failure == "sync":
        monkeypatch.setattr(os, "fsync", fail_sync)

    with (
        pytest.raises(OSError, match="failed"),
        atomic_output_path(destination, suffix=".tmp") as temporary_path,
        temporary_path.open("wb" if encoding is None else "w", encoding=encoding) as handle,
    ):
        handle.write(b"partial result" if encoding is None else "partial result")
        if failure == "write":
            raise OSError("write failed")

    assert destination.read_bytes() == b"previous result"
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_json_preserves_unicode_formatting(tmp_path: Path) -> None:
    destination = tmp_path / "result.json"
    atomic_write_json(destination, {"name": "Тестовый"})

    assert destination.read_bytes() == (
        '{\n  "name": "Тестовый"\n}\n'.replace("\n", os.linesep).encode("utf-8")
    )


@pytest.mark.skipif(os.name != "posix", reason="directory fsync is POSIX-only")
def test_atomic_write_json_syncs_file_and_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced_modes: list[int] = []
    original_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        synced_modes.append(os.fstat(descriptor).st_mode)
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", recording_fsync)

    atomic_write_json(tmp_path / "result.json", {"ok": True})

    assert any(stat.S_ISREG(mode) for mode in synced_modes)
    assert any(stat.S_ISDIR(mode) for mode in synced_modes)


@pytest.mark.skipif(os.name != "posix", reason="directory fsync is POSIX-only")
def test_directory_sync_tolerates_unsupported_filesystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unsupported_fsync(_descriptor: int) -> None:
        raise OSError("directory fsync is unavailable")

    monkeypatch.setattr(os, "fsync", unsupported_fsync)

    _sync_directory(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="directory fsync is POSIX-only")
def test_directory_sync_tolerates_unopenable_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_open(*_args: object, **_kwargs: object) -> int:
        raise OSError("directory descriptors are unavailable")

    monkeypatch.setattr(os, "open", failing_open)

    _sync_directory(tmp_path)
