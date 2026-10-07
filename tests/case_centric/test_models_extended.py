from dataclasses import replace

import pytest

from pix.case_centric.extended_discovery import discover_regions
from pix.case_centric.models_extended import IntegerRegion, SeparationTarget
from pix.contracts.models import Transition
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def result():
    return discover_regions(
        CaseLog(
            (
                CaseTrace(
                    "c",
                    (CaseEvent("e", (CaseAttribute("concept:name", "string", "A"),)),),
                ),
            )
        )
    ).value


@pytest.mark.parametrize(
    "changes",
    [
        {"initial": -1},
        {"final": True},
        {"consume": (1, 2)},
        {"produce": (-1,)},
        {"consume": [1]},
        {"arc_weight_cost": 9},
        {"blocked_target_ids": (1, 1)},
        {"blocked_target_ids": (2, 1)},
    ],
)
def test_region_rejects_invalid_witness(changes):
    region = IntegerRegion(1, 0, (1,), (0,), (0,), 2)
    with pytest.raises((TypeError, ValueError)):
        replace(region, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"objective_place_count": 99},
        {"objective_arc_weight": 99},
        {"alphabet": ("B", "A")},
        {"alphabet": ("A", "A")},
        {"all_targets_separated": False},
        {"optimal_within_bounds": 1},
        {"optimizer_states": -1},
        {"separation_targets": ()},
    ],
)
def test_discovery_rejects_inconsistent_summary(changes):
    with pytest.raises((TypeError, ValueError)):
        replace(result(), **changes)


@pytest.mark.parametrize(
    "args", [(("",), "A", True), (("A",), "", True), (("A",), None, 1)]
)
def test_invalid_target(args):
    with pytest.raises((TypeError, ValueError)):
        SeparationTarget(*args)


def test_selected_region_certificate_rejects_a_different_model():
    value = result()
    modified = replace(
        value.model,
        transitions=tuple(
            Transition(t.id, "X" if t.activity is not None else None)
            for t in value.model.transitions
        ),
    )
    with pytest.raises(ValueError, match="selected integer regions"):
        replace(value, model=modified)


def test_separation_claims_must_follow_the_region_equation():
    value = result()
    changed_regions = tuple(replace(r, blocked_target_ids=()) for r in value.regions)
    changed_targets = tuple(
        replace(t, separated=False) for t in value.separation_targets
    )
    with pytest.raises(ValueError, match="marking equation"):
        replace(
            value,
            regions=changed_regions,
            separation_targets=changed_targets,
            all_targets_separated=False,
        )
