from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path


def _sync_directory(directory: Path) -> None:
    """Best-effort directory sync for durable POSIX rename metadata."""
    if os.name != "posix":
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        # Some filesystems do not expose directories as fsync-compatible descriptors.
        return

    try:
        with suppress(OSError):
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_file(temporary_path: Path, destination_path: Path) -> None:
    original_mode: int | None = None
    if os.name == "nt" and destination_path.exists():
        original_mode = destination_path.stat().st_mode
        destination_path.chmod(original_mode | stat.S_IWRITE)

    try:
        os.replace(temporary_path, destination_path)
    except OSError:
        if original_mode is not None and destination_path.exists():
            destination_path.chmod(original_mode)
        raise


@contextmanager
def atomic_output_path(destination: str | Path, *, suffix: str) -> Iterator[Path]:
    destination_path = Path(destination)
    destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=suffix,
        dir=destination_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.chmod(0o600)

    try:
        yield temporary_path
        temporary_path.chmod(0o600)
        _replace_file(temporary_path, destination_path)
        _sync_directory(destination_path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_json(destination: str | Path, payload: object) -> None:
    with (
        atomic_output_path(destination, suffix=".json") as temporary_path,
        temporary_path.open("w", encoding="utf-8") as handle,
    ):
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
