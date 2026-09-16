"""A single-file import digest cannot describe an active SQLite journal."""

from pathlib import Path


def standalone_database_issue(path: Path) -> str | None:
    """Check before opening SQLite, which can itself create WAL sidecars."""
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) >= 20 and 2 in header[18:20]:
        return "WAL-mode databases require a closed, standalone SQLite export."
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            return "SQLite journal sidecars require a closed, standalone export."
    return None
