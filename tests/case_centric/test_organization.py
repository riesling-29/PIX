"""Hand-calculated organizational populations and independent interval oracles."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo

from pix.case_centric.organization import (
    AttributeNetworkSpec,
    OrganizationalGroup,
    OrganizationDiagnosticsSpec,
    ResourceProfileSpec,
    RoleDiscoverySpec,
    SocialNetworkSpec,
    discover_attribute_network,
    discover_roles,
    discover_social_network,
    measure_organization,
    measure_resource_profiles,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseGlobal, CaseLog, CaseTrace
from pix.results import _decode, _encode

ORIGIN = datetime(2026, 9, 14, tzinfo=timezone.utc)


def event(identity, activity="a", resource="r1", start=None, end=None):
    attributes = []
    if activity is not None:
        attributes.append(CaseAttribute("concept:name", "string", activity))
    if resource is not None:
        attributes.append(CaseAttribute("org:resource", "string", resource))
    if start is not None:
        attributes.append(
            CaseAttribute("start:timestamp", "date", ORIGIN + timedelta(seconds=start))
        )
    if end is not None:
        attributes.append(
            CaseAttribute("time:timestamp", "date", ORIGIN + timedelta(seconds=end))
        )
    return CaseEvent(identity, tuple(attributes))


def log(*traces):
    return CaseLog(
        tuple(CaseTrace(f"c{i}", tuple(events)) for i, events in enumerate(traces))
    )


def edge_map(result):
    return {(e.source, e.target): e for e in result.value.edges}


class SocialNetworkTests(unittest.TestCase):
    def test_handover_distance_weight_and_global_denominator(self):
        source = log(
            [
                event("1", resource="a"),
                event("2", resource="b"),
                event("3", resource="a"),
            ],
            [event("4", resource="b"), event("5", resource="c")],
            [],
        )
        result = discover_social_network(source, SocialNetworkSpec(beta=0.5))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(set(edge_map(result)), {("a", "b"), ("b", "a"), ("b", "c")})
        self.assertEqual(result.value.eligible_pair_weight, 3.5)
        for edge in result.value.edges:
            self.assertEqual(edge.raw_weight, 1)
            self.assertAlmostEqual(edge.weight, 2 / 7)
        with_self = discover_social_network(
            source, SocialNetworkSpec(beta=0.5, include_self=True)
        )
        self.assertEqual(edge_map(with_self)["a", "a"].raw_weight, 0.5)
        self.assertAlmostEqual(sum(e.weight for e in with_self.value.edges), 1.0)

    def test_missing_resource_does_not_collapse_positions(self):
        source = log(
            [
                event("1", resource="a"),
                event("2", resource=None),
                event("3", resource="b"),
            ]
        )
        direct = discover_social_network(source)
        self.assertEqual(direct.value.edges, ())
        self.assertEqual(direct.status, ComputeStatus.PARTIAL)
        longer = discover_social_network(
            source, SocialNetworkSpec(beta=0.5, normalization="opportunities")
        )
        self.assertEqual(longer.value.opportunity_weight, 2.5)
        self.assertEqual(edge_map(longer)["a", "b"].weight, 0.2)
        self.assertEqual(longer.value.missing_resource_count, 1)

    def test_working_together_unique_case_contribution_and_empty_case(self):
        source = log(
            [
                event("1", resource="a"),
                event("2", resource="b"),
                event("3", resource="a"),
            ],
            [event("4", resource="a")],
            [],
        )
        result = discover_social_network(
            source, SocialNetworkSpec(metric="working_together")
        )
        self.assertFalse(result.value.directed)
        self.assertEqual(len(result.value.edges), 1)
        edge = result.value.edges[0]
        self.assertEqual(edge.observation_count, 1)
        self.assertEqual(edge.weight, 1 / 3)

    def test_subcontracting_counts_every_return_instead_of_first_only(self):
        source = log(
            [
                event(str(i), resource=r)
                for i, r in enumerate(["a", "b", "a", "b", "a"])
            ],
            [],
        )
        result = discover_social_network(
            source, SocialNetworkSpec(metric="subcontracting")
        )
        self.assertEqual(edge_map(result)["a", "b"].raw_weight, 2)
        self.assertEqual(edge_map(result)["a", "b"].weight, 1)
        self.assertEqual(edge_map(result)["b", "a"].weight, 0.5)
        weighted = discover_social_network(
            source, SocialNetworkSpec(metric="subcontracting", max_distance=4, beta=0.5)
        )
        self.assertEqual(edge_map(weighted)["a", "b"].raw_weight, 2.5)

    def test_pearson_negative_and_constant_vector_undefined(self):
        source = log(
            [
                event("1", "x", "a"),
                event("2", "x", "a"),
                event("3", "y", "b"),
                event("4", "y", "b"),
                event("5", "x", "c"),
                event("6", "y", "c"),
            ]
        )
        result = discover_social_network(
            source, SocialNetworkSpec(metric="joint_activities")
        )
        self.assertEqual(edge_map(result)["a", "b"].weight, -1.0)
        self.assertIsNone(edge_map(result)["a", "c"].weight)
        self.assertIsNone(edge_map(result)["b", "c"].weight)
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        cosine = discover_social_network(
            source, SocialNetworkSpec(metric="joint_activities", similarity="cosine")
        )
        self.assertEqual(edge_map(cosine)["a", "b"].weight, 0)
        self.assertAlmostEqual(edge_map(cosine)["a", "c"].weight, 1 / 2**0.5)

    def test_resource_renaming_preserves_directed_and_undirected_weights(self):
        source = log([event("1", "x", "a"), event("2", "y", "b"), event("3", "x", "a")])
        mapping = {"a": "z", "b": "q"}
        renamed = log(
            [event("1", "x", "z"), event("2", "y", "q"), event("3", "x", "z")]
        )
        for metric in (
            "handover",
            "working_together",
            "subcontracting",
            "joint_activities",
        ):
            spec = SocialNetworkSpec(metric=metric)
            before, after = (
                discover_social_network(source, spec),
                discover_social_network(renamed, spec),
            )
            expected = {}
            for edge in before.value.edges:
                key = (mapping[edge.source], mapping[edge.target])
                if not before.value.directed:
                    key = tuple(sorted(key))
                expected[key] = edge.weight
            self.assertEqual(
                expected, {k: e.weight for k, e in edge_map(after).items()}
            )

    def test_globals_and_empty_population(self):
        source = replace(
            log([event("1", resource=None), event("2", resource="b")]),
            globals=(
                CaseGlobal("event", (CaseAttribute("org:resource", "string", "a"),)),
            ),
        )
        self.assertEqual(edge_map(discover_social_network(source))["a", "b"].weight, 1)
        for metric in (
            "handover",
            "working_together",
            "subcontracting",
            "joint_activities",
        ):
            result = discover_social_network(log(), SocialNetworkSpec(metric=metric))
            self.assertEqual(result.status, ComputeStatus.COMPUTED)
            self.assertEqual(result.value.resources, ())
            self.assertEqual(result.value.edges, ())

    def test_source_and_max_normalization(self):
        source = log(
            [
                event("1", resource="a"),
                event("2", resource="b"),
                event("3", resource="a"),
                event("4", resource="b"),
            ]
        )
        result = discover_social_network(
            source, SocialNetworkSpec(normalization="source")
        )
        self.assertEqual([e.weight for e in result.value.edges], [1, 1])
        maximum = discover_social_network(
            source, SocialNetworkSpec(normalization="max_abs")
        )
        self.assertEqual(edge_map(maximum)["a", "b"].weight, 1)
        self.assertEqual(edge_map(maximum)["b", "a"].weight, 0.5)


class RoleAndDiagnosisTests(unittest.TestCase):
    def test_role_normalized_multisets_and_strict_threshold(self):
        # x=(2,0), y=(1,0), z=(0,1). x/y are distribution-identical.
        source = log(
            [
                event("1", "x", "a"),
                event("2", "x", "a"),
                event("3", "y", "a"),
                event("4", "z", "b"),
            ]
        )
        result = discover_roles(source)
        self.assertEqual(result.value.roles[0].activities, ("x", "y"))
        self.assertEqual(result.value.roles[0].resource_counts, (("a", 3),))
        self.assertEqual(result.value.merges[0].similarity, 1)
        self.assertEqual(
            len(discover_roles(source, RoleDiscoverySpec(threshold=1)).value.roles), 3
        )

    def test_role_nontrivial_multiset_similarity(self):
        # x=(2,1), y=(1,2): min sum=2/3, max sum=4/3 => Jaccard=1/2.
        source = log(
            [
                event("1", "x", "a"),
                event("2", "x", "a"),
                event("3", "x", "b"),
                event("4", "y", "a"),
                event("5", "y", "b"),
                event("6", "y", "b"),
            ]
        )
        self.assertEqual(
            len(discover_roles(source, RoleDiscoverySpec(threshold=0.5)).value.roles), 2
        )
        result = discover_roles(source, RoleDiscoverySpec(threshold=0.49))
        self.assertEqual(len(result.value.roles), 1)
        self.assertEqual(result.value.merges[0].similarity, 0.5)

    def test_missing_role_activity_retained_and_resource_renaming_invariant(self):
        source = log(
            [
                event("1", "x", "a"),
                event("2", "y", "a"),
                event("3", "unsupported", None),
            ]
        )
        result = discover_roles(source)
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.unsupported_activities, ("unsupported",))
        self.assertEqual(result.value.eligible_event_count, 2)
        renamed = log(
            [
                event("1", "x", "z"),
                event("2", "y", "z"),
                event("3", "unsupported", None),
            ]
        )
        self.assertEqual(result.value.merges, discover_roles(renamed).value.merges)

    def test_diagnostics_denominators_and_overlapping_groups(self):
        source = log(
            [
                event("1", "x", "a"),
                event("2", "x", "a"),
                event("3", "y", "b"),
                event("4", "x", "c"),
                event("5", "x", None),
                event("6", None, "b"),
            ]
        )
        groups = (
            OrganizationalGroup("team", ("a", "b", "zero")),
            OrganizationalGroup("other", ("b",)),
        )
        result = measure_organization(
            source, OrganizationDiagnosticsSpec(groups=groups)
        )
        rows = {(r.group, r.activity): r for r in result.value.diagnostics}
        x = rows["team", "x"]
        self.assertEqual(x.group_event_count, 4)  # includes b's unknown activity
        self.assertEqual(x.activity_event_count, 4)  # includes unknown resource's x
        self.assertEqual(x.focus, 0.5)
        self.assertEqual(x.stake, 0.5)
        self.assertEqual(x.coverage, 1 / 3)
        self.assertEqual(x.member_contribution, (("a", 1), ("b", 0), ("zero", 0)))
        self.assertEqual(result.value.overlapping_resources, ("b",))
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(rows["team", "y"].focus, 1 / 4)
        self.assertEqual(rows["team", "y"].stake, 1)

    def test_zero_group_population_is_unknown_not_zero(self):
        result = measure_organization(
            log([event("1")]),
            OrganizationDiagnosticsSpec(groups=(OrganizationalGroup("empty", ()),)),
        )
        row = result.value.diagnostics[0]
        self.assertIsNone(row.focus)
        self.assertIsNone(row.coverage)
        self.assertEqual(row.stake, 0)


class ResourceProfileTests(unittest.TestCase):
    def test_dst_window_uses_utc_elapsed_duration_and_accepts_positive_fold(self):
        class SpringOffset(tzinfo):
            def utcoffset(self, dt):
                return timedelta(hours=int(dt.hour >= 2))

        zone = SpringOffset()
        spec = ResourceProfileSpec(
            window_start=ORIGIN.replace(tzinfo=zone),
            window_end=(ORIGIN + timedelta(hours=4)).replace(tzinfo=zone),
        )
        self.assertIs(spec.window_start.tzinfo, timezone.utc)
        source = log([event("work", start=0, end=10800)])
        result = measure_resource_profiles(source, spec)
        self.assertEqual(result.value.workload_window_seconds, 10800)
        self.assertEqual(result.value.profiles[0].average_workload, 1)

        class FallOffset(tzinfo):
            def utcoffset(self, dt):
                return timedelta(hours=1 - dt.fold)

        zone = FallOffset()
        ambiguous = (ORIGIN + timedelta(hours=1, minutes=30)).replace(tzinfo=zone)
        folded = ResourceProfileSpec(
            window_start=ambiguous, window_end=ambiguous.replace(fold=1)
        )
        self.assertEqual(
            (folded.window_end - folded.window_start).total_seconds(), 3600
        )

    def test_zero_length_inference_does_not_count_as_active_interval(self):
        result = measure_resource_profiles(
            log([event("1", end=2), event("2", end=2)]),
            ResourceProfileSpec(
                start_policy="previous_event",
                window_start=ORIGIN,
                window_end=ORIGIN + timedelta(seconds=10),
            ),
        )
        row = result.value.profiles[0]
        self.assertEqual(row.interval_count, 0)
        self.assertEqual(row.inferred_interval_count, 0)
        self.assertEqual(row.activity_duration_count, 1)
        self.assertEqual(row.mean_activity_duration_seconds, 0)

    def test_duplicate_overlapping_intervals_against_unit_time_oracle(self):
        # Duplicate work is real multiplicity: [0,4), [2,6), [2,6), [6,8).
        source = log(
            [event("1", start=0, end=4)],
            [event("2", start=2, end=6)],
            [event("3", start=2, end=6)],
            [event("4", start=6, end=8)],
        )
        spec = ResourceProfileSpec(
            window_start=ORIGIN,
            window_end=ORIGIN + timedelta(seconds=10),
            resources=("idle",),
        )
        result = measure_resource_profiles(source, spec)
        profile = next(p for p in result.value.profiles if p.resource == "r1")
        counts = [
            sum(
                left <= tick < right for left, right in [(0, 4), (2, 6), (2, 6), (6, 8)]
            )
            for tick in range(10)
        ]
        self.assertEqual(profile.effort_seconds, sum(counts))
        self.assertEqual(profile.busy_seconds, sum(c > 0 for c in counts))
        self.assertEqual(profile.multitasking_seconds, sum(c >= 2 for c in counts))
        self.assertEqual(profile.peak_concurrent_activities, max(counts))
        self.assertEqual(
            (
                profile.effort_seconds,
                profile.busy_seconds,
                profile.multitasking_seconds,
            ),
            (14, 8, 4),
        )
        self.assertEqual(profile.average_workload, 1.4)
        self.assertEqual(profile.busy_average_workload, 1.75)
        self.assertEqual(profile.multitasking_fraction, 0.5)
        self.assertEqual(profile.interval_count, 4)
        idle = next(p for p in result.value.profiles if p.resource == "idle")
        self.assertEqual(idle.average_workload, 0)
        self.assertIsNone(idle.multitasking_fraction)

    def test_half_open_clipping_and_touching_intervals(self):
        source = log(
            [
                event("1", start=-2, end=2),
                event("2", start=2, end=5),
                event("3", start=5, end=6),
            ]
        )
        result = measure_resource_profiles(
            source,
            ResourceProfileSpec(
                window_start=ORIGIN, window_end=ORIGIN + timedelta(seconds=5)
            ),
        )
        profile = result.value.profiles[0]
        self.assertEqual(profile.event_count, 1)  # completion at 5 is outside
        self.assertEqual(profile.effort_seconds, 5)  # its [2,5) work is inside
        self.assertEqual(profile.multitasking_seconds, 0)
        self.assertEqual(profile.peak_concurrent_activities, 1)
        self.assertEqual(
            profile.mean_activity_duration_seconds, 4
        )  # full service, not clipping

    def test_case_participation_completion_and_cooperation(self):
        source = log(
            [
                event("1", resource="a", start=0, end=2),
                event("2", resource="b", start=2, end=4),
            ],
            [event("3", resource="a", start=1, end=3)],
            [event("4", resource=None, start=0, end=1)],
            [],
        )
        result = measure_resource_profiles(source)
        profiles = {p.resource: p for p in result.value.profiles}
        self.assertEqual(result.value.selected_case_count, 3)
        self.assertEqual(profiles["a"].case_participation_fraction, 2 / 3)
        self.assertEqual(profiles["a"].completed_case_fraction, 2 / 3)
        self.assertEqual(profiles["a"].event_fraction, 1 / 2)
        self.assertEqual(profiles["a"].mean_observed_case_span_seconds, 1)
        self.assertEqual(profiles["a"].coworker_fraction, 1)
        self.assertEqual(result.value.interactions[0].shared_case_count, 1)
        self.assertEqual(result.value.interactions[0].case_fraction, 1 / 3)

    def test_missing_times_do_not_invent_case_completion_or_intervals(self):
        source = log([event("1", end=1), event("2", end=None), event("3", end=4)])
        result = measure_resource_profiles(source)
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.profiles[0].event_count, 3)
        self.assertEqual(result.value.completed_case_population, 0)
        self.assertEqual(result.value.missing_start_count, 3)
        self.assertIsNone(result.value.workload_window_start)
        inferred = measure_resource_profiles(
            source, ResourceProfileSpec(start_policy="previous_event")
        )
        self.assertEqual(inferred.value.profiles[0].interval_count, 0)
        self.assertEqual(inferred.value.missing_start_count, 2)

    def test_explicit_previous_event_inference_and_invalid_interval(self):
        source = log([event("1", end=1), event("2", end=3), event("3", start=5, end=4)])
        result = measure_resource_profiles(
            source, ResourceProfileSpec(start_policy="previous_event")
        )
        profile = result.value.profiles[0]
        self.assertEqual(profile.inferred_interval_count, 1)
        self.assertEqual(profile.effort_seconds, 2)
        self.assertEqual(result.value.invalid_interval_count, 1)
        self.assertEqual(result.value.missing_start_count, 1)

    def test_timezone_conversion_globals_and_zero_resource_population(self):
        source = log([event("1", start=0, end=2)])
        spec = ResourceProfileSpec(
            window_start=ORIGIN.astimezone(timezone(timedelta(hours=9))),
            window_end=(ORIGIN + timedelta(seconds=4)).astimezone(
                timezone(timedelta(hours=9))
            ),
        )
        self.assertEqual(
            measure_resource_profiles(source, spec).value.profiles[0].average_workload,
            0.5,
        )
        self.assertEqual(measure_resource_profiles(log()).value.profiles, ())
        globals_source = replace(
            log([event("x", resource=None, start=0, end=1)]),
            globals=(
                CaseGlobal(
                    "event", (CaseAttribute("org:resource", "string", "default"),)
                ),
            ),
        )
        self.assertEqual(
            measure_resource_profiles(globals_source).value.profiles[0].resource,
            "default",
        )


class OrganizationContractTests(unittest.TestCase):
    def test_duplicate_required_attribute_is_invalid_not_first_selected(self):
        bad = CaseEvent(
            "e",
            (
                CaseAttribute("org:resource", "string", "a"),
                CaseAttribute("org:resource", "string", "b"),
            ),
        )
        for fn in (
            discover_social_network,
            discover_roles,
            measure_organization,
            measure_resource_profiles,
        ):
            self.assertEqual(fn(log([bad])).status, ComputeStatus.INVALID_INPUT)

    def test_specs_validate_semantic_boundaries_and_are_frozen(self):
        for kwargs in (
            {"beta": -1},
            {"beta": float("nan")},
            {"max_distance": True},
            {"metric": "subcontracting", "max_distance": 1},
            {"metric": "working_together", "normalization": "source"},
            {"resources": ("a", "a")},
        ):
            with self.assertRaises((TypeError, ValueError)):
                SocialNetworkSpec(**kwargs)
        with self.assertRaises(ValueError):
            ResourceProfileSpec(window_start=ORIGIN)
        with self.assertRaises(ValueError):
            ResourceProfileSpec(
                window_start=ORIGIN.replace(tzinfo=None), window_end=ORIGIN
            )
        with self.assertRaises(FrozenInstanceError):
            RoleDiscoverySpec().threshold = 0.2

    def test_request_identity_changes_with_population_or_formula(self):
        source = log([event("1", resource="a"), event("2", resource="b")])
        first = discover_social_network(source)
        second = discover_social_network(source, SocialNetworkSpec(normalization="raw"))
        self.assertEqual(first.source_digest, second.source_digest)
        self.assertNotEqual(first.computation_id, second.computation_id)
        self.assertEqual(first, discover_social_network(source))

    def test_all_payloads_and_nested_specs_pass_typed_codec(self):
        source = log(
            [event("1", "x", "a", start=0, end=1), event("2", "y", "b", start=1, end=2)]
        )
        results = [
            discover_social_network(source, SocialNetworkSpec(beta=1)),
            discover_roles(source, RoleDiscoverySpec(threshold=1)),
            measure_organization(
                source,
                OrganizationDiagnosticsSpec(
                    groups=(OrganizationalGroup("team", ("a", "b")),)
                ),
            ),
            measure_resource_profiles(source),
            discover_attribute_network(source),
        ]
        for result in results:
            self.assertEqual(
                _decode(_encode(result.spec), type(result.spec)), result.spec
            )
            self.assertEqual(
                _decode(_encode(result.value), type(result.value)), result.value
            )


class AttributeNetworkTests(unittest.TestCase):
    def test_calendar_preserves_microseconds_far_from_epoch_without_datetime_overflow(
        self,
    ):
        for instant in (
            datetime(1900, 1, 1, tzinfo=timezone.utc),
            datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc),
        ):
            items = []
            for i in range(2):
                item = event(str(i))
                items.append(
                    replace(
                        item,
                        attributes=item.attributes
                        + (
                            CaseAttribute(
                                "time:timestamp",
                                "date",
                                instant + timedelta(microseconds=i),
                            ),
                        ),
                    )
                )
            result = discover_attribute_network(
                log(items),
                AttributeNetworkSpec(
                    weekly_slots=((0, 604800),), calendar_utc_offset_minutes=540
                ),
            )
            self.assertEqual(result.value.links[0].duration_seconds, 0.000001)

    def test_case_successor_source_witness_and_duration(self):
        source = log(
            [
                event("1", "a", "r1", end=0),
                event("2", "b", "r2", end=3),
                event("3", "c", "r1", end=9),
            ],
            [event("4", "a", "r1", end=0), event("5", "b", "r2", end=5)],
        )
        result = discover_attribute_network(source)
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        edges = {(e.source, e.target, e.edge_value): e for e in result.value.edges}
        self.assertEqual(edges["r1", "r2", "a"].count, 2)
        self.assertEqual(edges["r1", "r2", "a"].mean_seconds, 4)
        self.assertEqual(edges["r1", "r2", "a"].total_seconds, 8)
        self.assertEqual(
            [(p.source_event, p.target_event) for p in result.value.links],
            [("1", "2"), ("2", "3"), ("4", "5")],
        )

    def test_custom_attribute_link_crosses_cases_and_first_target_is_not_redirected(
        self,
    ):
        def with_keys(item, out, into):
            return replace(
                item,
                attributes=item.attributes
                + (
                    CaseAttribute("output", "string", out),
                    CaseAttribute("input", "string", into),
                ),
            )

        source = log(
            [with_keys(event("1", resource="a", end=0), "job", "unused")],
            [
                with_keys(event("2", resource=None, end=1), "unused", "job"),
                with_keys(event("3", resource="b", end=2), "unused", "job"),
            ],
        )
        spec = AttributeNetworkSpec(
            out_key="output", in_key="input", include_performance=False
        )
        first = discover_attribute_network(source, spec)
        self.assertEqual(first.value.links, ())
        self.assertEqual(first.value.candidate_link_count, 1)
        self.assertEqual(first.value.excluded_node_or_edge_link_count, 1)
        all_links = discover_attribute_network(source, replace(spec, selection="all"))
        self.assertEqual(
            [(p.source_event, p.target_event) for p in all_links.value.links],
            [("1", "3")],
        )

    def test_timestamp_sorting_unknown_order_and_explicit_bound(self):
        source = log(
            [
                event("1", resource="a", end=2),
                event("2", resource="b", end=1),
                event("3", resource="c", end=3),
            ]
        )
        result = discover_attribute_network(
            source, AttributeNetworkSpec(order="timestamp")
        )
        self.assertEqual(
            [(p.source_event, p.target_event) for p in result.value.links],
            [("2", "1"), ("1", "3")],
        )
        unknown = discover_attribute_network(
            log([event("1")]), AttributeNetworkSpec(order="timestamp")
        )
        self.assertEqual(unknown.status, ComputeStatus.UNAVAILABLE)
        bounded = discover_attribute_network(
            source, AttributeNetworkSpec(selection="all", max_links=2)
        )
        self.assertEqual(bounded.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(bounded.value)

    def test_weekly_calendar_holiday_and_fixed_offset(self):
        # Monday 08:00 -> Tuesday 18:00. Mon/Tue 09-17: 16 hours;
        # exclude Monday => 8 hours. Seconds are local UTC+9 in this profile.
        source = log(
            [
                event("1", resource="a", end=-3600),
                event("2", resource="b", end=33 * 3600),
            ]
        )
        spec = AttributeNetworkSpec(
            weekly_slots=((9 * 3600, 17 * 3600), (33 * 3600, 41 * 3600)),
            calendar_utc_offset_minutes=540,
            excluded_dates=("2026-09-14",),
        )
        result = discover_attribute_network(source, spec)
        self.assertEqual(result.value.links[0].duration_seconds, 8 * 3600)
        no_holiday = discover_attribute_network(
            source, replace(spec, excluded_dates=())
        )
        self.assertEqual(no_holiday.value.links[0].duration_seconds, 16 * 3600)

    def test_multiple_weeks_calendar_and_frequency_only_without_time(self):
        source = log([event("1", end=0), event("2", end=14 * 86400)])
        result = discover_attribute_network(
            source, AttributeNetworkSpec(weekly_slots=((9 * 3600, 17 * 3600),))
        )
        self.assertEqual(result.value.links[0].duration_seconds, 16 * 3600)
        no_time = discover_attribute_network(
            log([event("1"), event("2")]),
            AttributeNetworkSpec(include_performance=False),
        )
        self.assertEqual(no_time.status, ComputeStatus.COMPUTED)
        self.assertEqual(no_time.value.edges[0].count, 1)
        self.assertIsNone(no_time.value.edges[0].mean_seconds)

    def test_calendar_slots_reject_overlap_or_invalid_dates(self):
        with self.assertRaises(ValueError):
            AttributeNetworkSpec(weekly_slots=((0, 10), (9, 20)))
        with self.assertRaises(ValueError):
            AttributeNetworkSpec(weekly_slots=(), excluded_dates=("2026-02-30",))


if __name__ == "__main__":
    unittest.main()
