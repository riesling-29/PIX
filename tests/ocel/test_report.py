from dataclasses import FrozenInstanceError

import pytest

from pix.ocel.report import Issue, Level, Report


def test_empty_report_is_valid() -> None:
    report = Report()

    assert report.valid
    assert report.issues == ()
    assert report.errors == ()
    assert report.warnings == ()


def test_error_makes_report_invalid() -> None:
    issue = Issue(
        code="duplicate_event_id",
        message="Event id 'e1' occurs more than once.",
        at=("event", "e1"),
    )
    report = Report(
        issues=(issue,),
    )

    assert not report.valid
    assert report.errors == (issue,)
    assert report.warnings == ()


def test_warning_does_not_make_report_invalid() -> None:
    issue = Issue(
        code="noncanonical_order",
        message="Events are not in canonical order.",
        level=Level.WARNING,
        at=("events",),
    )
    report = Report(
        issues=(issue,),
    )

    assert report.valid
    assert report.errors == ()
    assert report.warnings == (issue,)


def test_report_separates_errors_and_warnings() -> None:
    error = Issue(
        code="dangling_e2o_object",
        message="E2O refers to unknown object 'o9'.",
        at=("e2o", "e1", "o9", "item"),
    )
    warning = Issue(
        code="noncanonical_order",
        message="Relations are not in canonical order.",
        level=Level.WARNING,
        at=("e2o",),
    )

    report = Report(
        issues=(
            warning,
            error,
        ),
    )

    assert report.errors == (error,)
    assert report.warnings == (warning,)
    assert not report.valid


def test_report_has_issue_code() -> None:
    report = Report(
        issues=(
            Issue(
                code="duplicate_object_id",
                message="Object id 'o1' occurs more than once.",
                at=("object", "o1"),
            ),
            Issue(
                code="dangling_o2o_target",
                message="O2O refers to unknown target object 'o9'.",
                at=("o2o", "o1", "o9", "parent"),
            ),
        ),
    )

    assert report.has("duplicate_object_id")
    assert report.has("dangling_o2o_target")
    assert not report.has("duplicate_event_id")


def test_issue_and_report_are_frozen() -> None:
    issue = Issue(
        code="duplicate_event_id",
        message="Event id 'e1' occurs more than once.",
    )
    report = Report(
        issues=(issue,),
    )

    with pytest.raises(FrozenInstanceError):
        issue.code = "changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        report.issues = ()  # type: ignore[misc]


def test_report_requires_tuple_of_issues() -> None:
    issue = Issue(
        code="duplicate_event_id",
        message="Event id 'e1' occurs more than once.",
    )

    with pytest.raises(
        TypeError,
        match="Report.issues must be a tuple",
    ):
        Report(
            issues=[issue],  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="every item in Report.issues must be Issue",
    ):
        Report(
            issues=("invalid",),  # type: ignore[arg-type]
        )


def test_issue_requires_valid_local_shape() -> None:
    with pytest.raises(
        ValueError,
        match="Issue.code",
    ):
        Issue(
            code="",
            message="Some problem.",
        )

    with pytest.raises(
        ValueError,
        match="Issue.message",
    ):
        Issue(
            code="some_issue",
            message="   ",
        )

    with pytest.raises(
        TypeError,
        match="Issue.level must be Level",
    ):
        Issue(
            code="some_issue",
            message="Some problem.",
            level="error",  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="Issue.at must be a tuple",
    ):
        Issue(
            code="some_issue",
            message="Some problem.",
            at=["event", "e1"],  # type: ignore[arg-type]
        )


def test_semantic_location_may_contain_empty_qualifier() -> None:
    issue = Issue(
        code="duplicate_e2o",
        message="Duplicate E2O relation.",
        at=(
            "e2o",
            "e1",
            "o1",
            "",
        ),
    )

    assert issue.at == (
        "e2o",
        "e1",
        "o1",
        "",
    )
