from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from pix.ocel import (
    OCEL,
    Event,
    EventType,
    ImportIssue,
    ImportResult,
    ImportStage,
    ImportStatus,
    Level,
    Report,
    Transformation,
    canonical_digest,
    validate,
)

T0 = datetime(2026, 8, 22, tzinfo=timezone.utc)
SOURCE_SHA256 = "1" * 64


def _source_issue(stage: ImportStage = ImportStage.SYNTAX) -> ImportIssue:
    return ImportIssue(
        stage=stage,
        code="invalid_source",
        message="Source cannot be imported.",
        at=("/events/0",),
    )


def test_valid_empty_import_exposes_ocel_and_digests() -> None:
    candidate = OCEL()
    result = ImportResult(
        source="empty.json",
        format="ocel20-json",
        status=ImportStatus.VALID,
        candidate=candidate,
        semantic_report=validate(candidate),
        source_sha256=SOURCE_SHA256,
        canonical_digest=canonical_digest(candidate),
    )

    assert result.valid
    assert result.ocel == candidate
    assert result.semantic_report == Report()


def test_valid_import_may_disclose_warnings_and_transformations() -> None:
    candidate = OCEL()
    warning = ImportIssue(
        stage=ImportStage.MAPPING,
        code="timezone_normalized",
        message="Timezone-aware timestamp was represented in UTC.",
        level=Level.WARNING,
        at=("event", "e1", "time"),
    )
    transformation = Transformation(
        code="timezone_to_utc",
        message="Represented the same instant in UTC.",
        at=("event", "e1", "time"),
    )
    result = ImportResult(
        source="valid.json",
        format="ocel20-json",
        status=ImportStatus.VALID,
        candidate=candidate,
        import_issues=(warning,),
        semantic_report=validate(candidate),
        transformations=(transformation,),
        canonical_digest=canonical_digest(candidate),
    )

    assert result.valid
    assert result.import_issues == (warning,)
    assert result.transformations == (transformation,)


def test_semantic_invalid_import_preserves_candidate_only() -> None:
    candidate = OCEL(
        event_types=(EventType("create"),),
        events=(
            Event("e1", "create", T0),
            Event("e1", "create", T0),
        ),
    )
    report = validate(candidate)
    result = ImportResult(
        source="duplicate.json",
        format="ocel20-json",
        status=ImportStatus.SEMANTIC_INVALID,
        candidate=candidate,
        semantic_report=report,
    )

    assert not result.valid
    assert result.candidate == candidate
    assert result.ocel is None
    assert report.has("duplicate_event_id")


@pytest.mark.parametrize(
    ("status", "stage"),
    (
        (ImportStatus.UNAVAILABLE, ImportStage.SOURCE),
        (ImportStatus.UNSUPPORTED, ImportStage.SOURCE),
        (ImportStatus.SYNTAX_INVALID, ImportStage.SYNTAX),
    ),
)
def test_pre_semantic_failures_have_no_candidate(
    status: ImportStatus,
    stage: ImportStage,
) -> None:
    result = ImportResult(
        source="source.bin",
        format=None,
        status=status,
        candidate=None,
        import_issues=(_source_issue(stage),),
        source_sha256=SOURCE_SHA256,
    )

    assert not result.valid
    assert result.candidate is None
    assert result.ocel is None
    assert result.semantic_report is None
    assert result.canonical_digest is None


def test_valid_status_requires_complete_valid_evidence() -> None:
    candidate = OCEL()

    with pytest.raises(ValueError, match="requires candidate"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.VALID,
            candidate=None,
            semantic_report=Report(),
            canonical_digest=canonical_digest(candidate),
        )

    with pytest.raises(ValueError, match="valid semantic report"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.VALID,
            candidate=candidate,
            semantic_report=None,
            canonical_digest=canonical_digest(candidate),
        )

    with pytest.raises(ValueError, match="requires canonical digest"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.VALID,
            candidate=candidate,
            semantic_report=Report(),
        )

    with pytest.raises(ValueError, match="cannot contain error"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.VALID,
            candidate=candidate,
            import_issues=(_source_issue(),),
            semantic_report=Report(),
            canonical_digest=canonical_digest(candidate),
        )


def test_non_valid_status_cannot_claim_canonical_digest() -> None:
    with pytest.raises(ValueError, match="cannot have canonical digest"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.SYNTAX_INVALID,
            candidate=None,
            import_issues=(_source_issue(),),
            canonical_digest=canonical_digest(OCEL()),
        )


def test_pre_semantic_failure_requires_error_issue() -> None:
    with pytest.raises(ValueError, match="requires error issue"):
        ImportResult(
            source="missing.json",
            format="ocel20-json",
            status=ImportStatus.UNAVAILABLE,
            candidate=None,
        )


def test_import_contracts_require_immutable_local_shape() -> None:
    issue = _source_issue()
    transformation = Transformation(
        code="timezone_to_utc",
        message="Represented timestamp in UTC.",
    )

    with pytest.raises(TypeError, match="import_issues must be a tuple"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.SYNTAX_INVALID,
            candidate=None,
            import_issues=[issue],  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="transformations must be a tuple"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.SYNTAX_INVALID,
            candidate=None,
            import_issues=(issue,),
            transformations=[transformation],  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="source_sha256"):
        ImportResult(
            source="source.json",
            format="ocel20-json",
            status=ImportStatus.SYNTAX_INVALID,
            candidate=None,
            import_issues=(issue,),
            source_sha256="invalid",
        )


def test_import_contracts_are_frozen() -> None:
    issue = _source_issue()
    result = ImportResult(
        source="source.json",
        format="ocel20-json",
        status=ImportStatus.SYNTAX_INVALID,
        candidate=None,
        import_issues=(issue,),
    )

    with pytest.raises(FrozenInstanceError):
        issue.code = "changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.status = ImportStatus.VALID  # type: ignore[misc]
