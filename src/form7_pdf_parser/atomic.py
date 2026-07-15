from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


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
        os.replace(temporary_path, destination_path)
        destination_path.chmod(0o600)
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
