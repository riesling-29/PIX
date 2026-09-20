from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.context_ngrams import (
    ContextNGramSpec,
    fit_context_ngrams,
    transform_context_ngrams,
)
from pix.event_log import read_xes_bytes, xes_bytes
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)

T = datetime(2026, 9, 18, tzinfo=timezone.utc)


def example():
    return OCEL(
        event_types=(
            EventType("A", (Attribute("tool", ValueType.STRING),)),
            EventType("B"),
        ),
        object_types=(ObjectType("order", (Attribute("status", ValueType.STRING),)),),
        events=(
            Event("e1", "A", T, (EventAttr("tool", "browser"),)),
            Event("e2", "B", T + timedelta(seconds=1)),
            Event("outside", "B", T),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr("status", "open", T),
                    ObjectAttr("status", "closed", T + timedelta(seconds=2)),
                ),
            ),
            Object("o2", "order"),
            Object("empty", "order"),
        ),
        e2o=(
            E2O("e1", "o1", "actor"),
            E2O("e1", "o1", "observer"),
            E2O("e1", "o2", "actor"),
            E2O("e2", "o1", "actor"),
        ),
        o2o=(O2O("o1", "o2", "related"),),
    )


def test_shared_events_attributes_history_and_participation():
    result = project_object_cases(example(), ObjectCaseProjectionSpec("order"))
    assert result.source.o2o == example().o2o
    assert result.excluded_event_ids == ("outside",)
    assert [len(t.events) for t in result.case_log.traces] == [0, 2, 1]
    assert len(set(e.id for t in result.case_log.traces for e in t.events)) == 3
    one = result.case_log.traces[1]
    assert len(one.attribute("pix:object_history").values) == 2
    assert one.events[0].attribute("event:tool").value == "browser"
    assert len(one.events[0].attribute("pix:participation").values) == 3
    assert [source for _, source in result.occurrence_source_ids].count("e1") == 2
    # Preserved projection attributes remain exchangeable.
    assert len(read_xes_bytes(xes_bytes(result.case_log)).traces) == 3


def test_no_cross_object_ngrams_and_empty_objects_are_documents():
    projected = project_object_cases(
        example(), ObjectCaseProjectionSpec("order")
    ).case_log
    fit = fit_context_ngrams(
        projected, ContextNGramSpec(ngram_min=2, ngram_max=2)
    ).value
    result = transform_context_ngrams(projected, fit).value
    assert [c.terms for c in result.matrix.columns] == [("A", "B")]
    assert [r.values for r in result.matrix.rows] == [(0,), (1,), (0,)]
    assert fit.feature_model.document_count == 3


def test_ties_require_explicit_policy():
    log = example()
    log = replace(
        log, events=(log.events[0], replace(log.events[1], time=T), log.events[2])
    )
    with pytest.raises(ValueError, match="simultaneous"):
        project_object_cases(log, ObjectCaseProjectionSpec("order"))
    result = project_object_cases(
        log, ObjectCaseProjectionSpec("order", tie_policy="event_id")
    )
    assert result.tied_object_ids == ("o1",)
    with pytest.raises(ValueError, match="unknown object type"):
        project_object_cases(log, ObjectCaseProjectionSpec("missing"))
