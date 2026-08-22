"""Versioned canonical identity for valid PIX OCEL datasets."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from pix.ocel.canonical.contract import (
    CURRENT_CANONICAL_VERSION,
    CanonicalDigest,
    CanonicalizationError,
    CanonicalVersion,
)
from pix.ocel.canonical.v1 import serialize_v1
from pix.ocel.model import OCEL

Serializer = Callable[[OCEL], bytes]

_SERIALIZERS: dict[CanonicalVersion, Serializer] = {
    CanonicalVersion.V1: serialize_v1,
}


def canonical_bytes(
    ocel: OCEL,
    *,
    version: CanonicalVersion = CURRENT_CANONICAL_VERSION,
) -> bytes:
    """Serialize a valid OCEL using one immutable canonical version."""

    if not isinstance(version, CanonicalVersion):
        raise TypeError("version must be CanonicalVersion")

    try:
        serializer = _SERIALIZERS[version]
    except KeyError as exc:  # pragma: no cover - enum currently contains only V1
        raise ValueError(f"unsupported canonical version: {version.value}") from exc

    return serializer(ocel)


def canonical_digest(
    ocel: OCEL,
    *,
    version: CanonicalVersion = CURRENT_CANONICAL_VERSION,
) -> CanonicalDigest:
    """Return the SHA-256 identity of one canonical OCEL representation."""

    serialized = canonical_bytes(ocel, version=version)
    return CanonicalDigest(
        version=version,
        algorithm="sha256",
        hexdigest=hashlib.sha256(serialized).hexdigest(),
    )


__all__ = [
    "CURRENT_CANONICAL_VERSION",
    "CanonicalDigest",
    "CanonicalVersion",
    "CanonicalizationError",
    "canonical_bytes",
    "canonical_digest",
]
