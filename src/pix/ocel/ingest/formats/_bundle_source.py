"""Bounded, non-extracting access to OCEL bundle containers."""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from pix.ocel.ingest.formats.common import schema_failure, syntax_failure

# Explicit import policy, applied to declared sizes and actual bytes read.
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_ENTRIES = 100_000
BUNDLE_MAGIC = b"OCEL-BUNDLE\x00"


def safe_name(value: object) -> str:
    """Require a portable relative path without resolving untrusted syntax."""
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or "\x00" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise schema_failure(
            "unsafe_bundle_path",
            "Bundle paths must be safe relative POSIX paths.",
            (str(value),),
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise schema_failure("unsafe_bundle_path", "Invalid Unicode in path.") from exc
    return value


def _check_size(size: int, count: int) -> None:
    if size > MAX_BUNDLE_BYTES or count > MAX_BUNDLE_ENTRIES:
        raise schema_failure(
            "bundle_resource_limit",
            f"Bundle exceeds {MAX_BUNDLE_BYTES} uncompressed bytes or "
            f"{MAX_BUNDLE_ENTRIES} entries.",
        )


def _check_regular(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise schema_failure(
            "bundle_symlink_forbidden",
            "Bundle symlinks/reparse points are forbidden.",
            (str(path),),
        )
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise schema_failure(
            "bundle_special_file",
            "Bundle contains a non-regular file.",
            (str(path),),
        )
    return info


class BundleSource:
    """Inventory first; read only explicitly requested members, without extraction."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive: zipfile.ZipFile | None = None
        self.files: dict[str, int] = {}
        self._paths: dict[str, Path] = {}
        self._identities: dict[str, tuple[int, int, int]] = {}
        self._bytes_read = 0
        try:
            if path.is_dir():
                self._directory()
            else:
                self._zip()
        except Exception:
            self.close()
            raise

    def _directory(self) -> None:
        _check_regular(self.path, directory=True)
        root = self.path.resolve(strict=True)
        pending = [root]
        size = count = 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    target = Path(entry.path)
                    name = safe_name(target.relative_to(root).as_posix())
                    is_directory = entry.is_dir(follow_symlinks=False)
                    info = _check_regular(target, directory=is_directory)
                    if not target.resolve(strict=True).is_relative_to(root):
                        raise schema_failure(
                            "unsafe_bundle_path", "Path escapes bundle."
                        )
                    if is_directory:
                        pending.append(target)
                    else:
                        self.files[name] = info.st_size
                        self._paths[name] = target
                        self._identities[name] = (
                            info.st_dev,
                            info.st_ino,
                            info.st_size,
                        )
                        size += info.st_size
                    _check_size(size, count)

    def _zip(self) -> None:
        self.archive = zipfile.ZipFile(self.path, "r")
        entries = self.archive.infolist()
        _check_size(0, len(entries))
        size = 0
        seen: set[str] = set()
        for entry in entries:
            original = entry.orig_filename
            name = safe_name(original[:-1] if entry.is_dir() else original)
            if name in seen:
                raise schema_failure(
                    "duplicate_bundle_member",
                    "Repeated ZIP member.",
                    (name,),
                )
            seen.add(name)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode):
                raise schema_failure(
                    "bundle_symlink_forbidden",
                    "ZIP symlink entries are forbidden.",
                    (name,),
                )
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise schema_failure(
                    "bundle_special_file",
                    "ZIP special entries are forbidden.",
                    (name,),
                )
            if entry.flag_bits & 1:
                raise schema_failure(
                    "encrypted_bundle_member",
                    "Encrypted ZIP members are unsupported.",
                    (name,),
                )
            if entry.is_dir():
                if entry.file_size:
                    raise schema_failure(
                        "invalid_bundle_directory",
                        "ZIP directory contains data.",
                        (name,),
                    )
                continue
            if kind == stat.S_IFDIR:
                raise schema_failure(
                    "invalid_bundle_directory", "Invalid ZIP directory."
                )
            self.files[name] = entry.file_size
            size += entry.file_size
            _check_size(size, len(entries))
        for name in self.files:
            if any(str(parent) in self.files for parent in PurePosixPath(name).parents):
                raise schema_failure(
                    "ambiguous_bundle_path",
                    "ZIP path is both a file and a directory.",
                    (name,),
                )

    def read(self, name: str) -> bytes:
        safe_name(name)
        if name not in self.files:
            raise schema_failure(
                "missing_bundle_member",
                "Declared bundle file does not exist.",
                (name,),
            )
        limit = min(self.files[name], MAX_BUNDLE_BYTES) + 1
        if self.archive is not None:
            with self.archive.open(name) as stream:
                data = stream.read(limit)
        else:
            target = self._paths[name]
            # Recheck paths, then verify the opened handle before reading bytes.
            # The identity check also detects a parent replaced by a junction
            # between these checks and open(), on platforms without O_NOFOLLOW.
            for part in (self.path, *target.parents):
                if part == self.path or part.is_relative_to(self.path.resolve()):
                    _check_regular(part, directory=True)
            info = _check_regular(target, directory=False)
            identity = self._identities[name]
            if (info.st_dev, info.st_ino, info.st_size) != identity:
                raise syntax_failure("bundle_changed", "Bundle changed during import.")
            flags = (
                os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(target, flags)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino, opened.st_size) != identity:
                    raise syntax_failure(
                        "bundle_changed", "Opened bundle file identity changed."
                    )
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    data = stream.read(limit)
            finally:
                os.close(descriptor)
        if len(data) != self.files[name]:
            raise syntax_failure("bundle_changed", "Bundle size changed during import.")
        self._bytes_read += len(data)
        _check_size(self._bytes_read, len(self.files))
        return data

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()

    def __enter__(self) -> BundleSource:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def source_evidence(path: Path) -> tuple[str, int, bytes]:
    """Hash sorted path/bytes pairs; ignore mtimes and empty directories.

    Manifest v1: prefix, then UTF-8 path length (8-byte unsigned big-endian),
    path bytes, content length (8-byte unsigned big-endian), and content bytes.
    The reported size is the sum of content lengths, excluding manifest framing.
    """
    digest = hashlib.sha256(b"PIX-OCEL-BUNDLE-MANIFEST-v1\x00")
    size = 0
    with BundleSource(path) as source:
        for name in sorted(source.files):
            encoded = name.encode("utf-8")
            data = source.read(name)
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
            size += len(data)
    return digest.hexdigest(), size, BUNDLE_MAGIC
