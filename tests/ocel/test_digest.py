from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from pix.ocel import (
    CURRENT_CANONICAL_VERSION,
    OCEL,
    CanonicalDigest,
    CanonicalVersion,
    canonical_bytes,
    canonical_digest,
)


def test_digest_hashes_exact_canonical_bytes() -> None:
    serialized = canonical_bytes(OCEL())
    digest = canonical_digest(OCEL())

    assert digest.version is CURRENT_CANONICAL_VERSION
    assert digest.algorithm == "sha256"
    assert digest.hexdigest == sha256(serialized).hexdigest()
    assert digest.identifier == (
        f"pix.ocel.canonical.v1:sha256:{digest.hexdigest}"
    )


def test_digest_contract_is_frozen() -> None:
    digest = canonical_digest(OCEL())

    with pytest.raises(FrozenInstanceError):
        digest.hexdigest = "0" * 64  # type: ignore[misc]


def test_digest_contract_rejects_invalid_shape() -> None:
    with pytest.raises(TypeError, match="version"):
        CanonicalDigest(
            version="v1",  # type: ignore[arg-type]
            algorithm="sha256",
            hexdigest="0" * 64,
        )

    with pytest.raises(ValueError, match="algorithm"):
        CanonicalDigest(
            version=CanonicalVersion.V1,
            algorithm="md5",
            hexdigest="0" * 64,
        )

    with pytest.raises(ValueError, match="64 hexadecimal"):
        CanonicalDigest(
            version=CanonicalVersion.V1,
            algorithm="sha256",
            hexdigest="0" * 63,
        )

    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        CanonicalDigest(
            version=CanonicalVersion.V1,
            algorithm="sha256",
            hexdigest="A" * 64,
        )


def test_version_argument_requires_canonical_version() -> None:
    with pytest.raises(TypeError, match="version must be CanonicalVersion"):
        canonical_bytes(
            OCEL(),
            version="v1",  # type: ignore[arg-type]
        )
