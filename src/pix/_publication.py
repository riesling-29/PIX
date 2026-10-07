"""Atomic artifact publication with a distinct post-commit cleanup outcome."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CleanupIssue:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class FilePublication(os.PathLike[str]):
    path: Path
    byte_count: int
    output_sha256: str
    cleanup_issues: tuple[CleanupIssue, ...] = ()

    def __fspath__(self) -> str:
        return os.fspath(self.path)


def _cleanup(path: Path) -> tuple[CleanupIssue, ...]:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        return (CleanupIssue(path, str(error)),)
    return ()


def publish_bytes(
    payload: bytes,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    prefix: str = ".pix-artifact-",
) -> FilePublication:
    """Publish in the target directory, preserving primary and cleanup evidence.

    No-clobber publication uses a hard link so a concurrent creator wins without
    being overwritten. A successful link/replace is the commit point: later
    temporary-file cleanup failure does not turn it into a failed publication.
    Before commit, cleanup evidence is attached to the primary exception.
    """
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    target = Path(path).absolute()
    fd, temporary_name = tempfile.mkstemp(prefix=prefix, dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    except BaseException as error:
        issues = _cleanup(temporary)
        if issues:
            error.cleanup_issues = issues
        raise
    return FilePublication(
        target, len(payload), sha256(payload).hexdigest(), _cleanup(temporary)
    )
