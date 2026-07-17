from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from form7_pdf_parser.atomic import _sync_directory, atomic_write_json


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
