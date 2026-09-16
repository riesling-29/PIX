"""Native object-token replay and explicitly flattened replay.

Joint replay consumes each event once and requires its exact selected object
participation. It is a deterministic local repair procedure, not an alignment
or a global optimum. Silent search is forward BFS (not OCPA backward replay).
No token flooding deletion is performed: every residual token remains evidence.

Initial tokens count as produced; final-marking tokens count as consumed.
Fitness is .5*(1-m/c)+.5*(1-r/p), when both denominators are positive and
replay completed. Unmapped activities are separate deviations: token fitness
alone never certifies that the event log fits. No time is fabricated here.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.compute.object_conformance import (
    build_object_event_scope,
    validate_object_model_scope,
)
from pix.compute.replay import _replay_trace
from pix.contracts.analysis import ObjectTrace, TraceEvent
from pix.contracts.models import (
    Arc,
    Binding,
    Marking,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
)
from pix.contracts.object_conformance import (
    ObjectAlignmentSpec,
    ObjectEventParticipation,
    ObjectLogScope,
)
from pix.contracts.replay import ReplaySpec, TokenCounts, TraceReplay
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL


@dataclass(frozen=True, slots=True)
class ObjectReplaySpec:
    """Whole selected object universe, exact event binding, lexical DAG order.

    Same-object timestamp ties require an explicit event_id convention.
    Independent ready events are ordered by event ID; this is not inferred
    causality. Silent states/bindings are bounded independently per closure.
    """

    object_types: tuple[str, ...]
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    silent_max_states: int = 1000
    max_bindings: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        selection = ObjectAlignmentSpec(
            self.object_types,
            self.qualifiers,
            self.tie_policy,
        )
        object.__setattr__(self, "object_types", selection.object_types)
        object.__setattr__(self, "qualifiers", selection.qualifiers)
        for name in ("silent_max_states", "max_bindings"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class ObjectReplayRequest:
    model_digest: str
    parameters: ObjectReplaySpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ObjectReplayStep:
    kind: Literal["initial", "visible", "silent", "log_deviation", "finalize"]
    event_id: str | None
    binding: Binding | None
    marking_before: tuple[ObjectToken, ...]
    marking_after: tuple[ObjectToken, ...]
    inserted_tokens: tuple[ObjectToken, ...] = ()
    consumed_tokens: tuple[ObjectToken, ...] = ()
    produced_tokens: tuple[ObjectToken, ...] = ()
    deviation_reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in (
            "initial",
            "visible",
            "silent",
            "log_deviation",
            "finalize",
        ):
            raise ValueError("unknown replay step kind")
        for name in (
            "marking_before",
            "marking_after",
            "inserted_tokens",
            "consumed_tokens",
            "produced_tokens",
        ):
            tokens = getattr(self, name)
            if not isinstance(tokens, tuple) or any(
                not isinstance(t, ObjectToken) for t in tokens
            ):
                raise TypeError(f"{name} must be a tuple of ObjectToken")
            object.__setattr__(self, name, tuple(sorted(tokens)))
        available = Counter(self.marking_before) + Counter(self.inserted_tokens)
        required = Counter(self.consumed_tokens)
        if required - available:
            raise ValueError("replay step consumes unavailable tokens")
        after = available - required + Counter(self.produced_tokens)
        if after != Counter(self.marking_after):
            raise ValueError(
                "replay step token arithmetic disagrees with marking_after"
            )
        if (self.event_id is not None) != (self.kind in ("visible", "log_deviation")):
            raise ValueError("only visible/deviation steps carry an event ID")
        if (self.binding is not None) != (self.kind in ("visible", "silent")):
            raise ValueError("only fired steps carry a binding")
        if self.binding is not None and not isinstance(self.binding, Binding):
            raise TypeError("binding must be Binding or None")


@dataclass(frozen=True, slots=True)
class ObjectReplaySearch:
    event_id: str | None
    state_count: int
    exhaustive: bool
    limit_reason: str | None


@dataclass(frozen=True, slots=True)
class ObjectReplay:
    model_digest: str
    scope: ObjectLogScope
    status: Literal["completed", "limited"]
    event_order: tuple[str, ...]
    processed_event_count: int
    log_deviation_count: int
    steps: tuple[ObjectReplayStep, ...]
    searches: tuple[ObjectReplaySearch, ...]
    counts: TokenCounts
    token_fitness: float | None
    fitting: bool | None
    final_reached: bool | None
    ending_marking: tuple[ObjectToken, ...]
    limit_reason: str | None = None
    profile: str = "joint_lexical_topological_silent_bfs_local_repair_v1"

    def __post_init__(self) -> None:
        if self.status not in ("completed", "limited"):
            raise ValueError("unknown replay status")
        if not self.steps or self.steps[0].kind != "initial":
            raise ValueError("replay must retain its initial marking step")
        if self.profile != "joint_lexical_topological_silent_bfs_local_repair_v1":
            raise ValueError("unknown joint replay profile")
        for before, after in zip(self.steps, self.steps[1:]):
            if before.marking_after != after.marking_before:
                raise ValueError("replay witness markings are discontinuous")
        if self.ending_marking != self.steps[-1].marking_after:
            raise ValueError("ending marking disagrees with witness")
        actual_counts = TokenCounts(
            missing=sum(len(s.inserted_tokens) for s in self.steps),
            remaining=len(self.ending_marking),
            consumed=sum(len(s.consumed_tokens) for s in self.steps),
            produced=sum(len(s.produced_tokens) for s in self.steps),
        )
        if actual_counts != self.counts:
            raise ValueError("replay token counts disagree with witness")
        event_ids = tuple(s.event_id for s in self.steps if s.event_id is not None)
        if event_ids != self.event_order[: self.processed_event_count]:
            raise ValueError("processed events disagree with the scheduled prefix")
        if self.processed_event_count != len(event_ids):
            raise ValueError("processed event count disagrees with witness")
        if len(set(self.event_order)) != len(self.event_order) or set(
            self.event_order
        ) != {event.event_id for event in self.scope.events}:
            raise ValueError("event order must include each scoped event exactly once")
        if self.log_deviation_count != sum(
            s.kind == "log_deviation" for s in self.steps
        ):
            raise ValueError("log deviation count disagrees with witness")
        complete = self.status == "completed"
        if complete != (self.limit_reason is None):
            raise ValueError("replay limit and completion status disagree")
        if complete and (
            self.processed_event_count != len(self.event_order)
            or self.steps[-1].kind != "finalize"
        ):
            raise ValueError("completed replay must finalize after every event")
        if not complete and (
            self.fitting is not None or self.final_reached is not None
        ):
            raise ValueError("limited replay cannot claim a final outcome")
        if complete:
            final_step = self.steps[-1]
            reached = Counter(final_step.marking_before) == Counter(
                final_step.consumed_tokens
            )
            if self.final_reached is not reached:
                raise ValueError(
                    "final reached flag disagrees with pre-repair final marking"
                )
        if self.token_fitness != _fitness(self.counts, complete):
            raise ValueError("token fitness disagrees with token counts or coverage")
        if complete and self.fitting != (
            not (
                self.counts.missing or self.counts.remaining or self.log_deviation_count
            )
        ):
            raise ValueError("fitting flag disagrees with replay deviations")


@dataclass(frozen=True, slots=True)
class FlattenedObjectReplay:
    object_id: str
    object_type: str
    projection_model_digest: str
    replay: TraceReplay
    token_fitness: float | None


@dataclass(frozen=True, slots=True)
class FlattenedReplay:
    model_digest: str
    scope: ObjectLogScope
    objects: tuple[FlattenedObjectReplay, ...]
    completed_count: int
    limited_count: int
    source_event_count: int
    projected_event_occurrence_count: int
    unrepresented_event_ids: tuple[str, ...]
    log_deviation_count: int
    completed_counts: TokenCounts
    attempted_counts: TokenCounts
    token_fitness: float | None
    profile: str = "per_concrete_object_projection_token_weighted_v1"

    def __post_init__(self) -> None:
        if self.profile != "per_concrete_object_projection_token_weighted_v1":
            raise ValueError("unknown flattened replay profile")
        if (
            tuple((row.object_id, row.object_type) for row in self.objects)
            != self.scope.selected_objects
        ):
            raise ValueError("flattened objects disagree with selected scope")
        completed = tuple(
            row for row in self.objects if row.replay.status == "completed"
        )
        if self.completed_count != len(completed) or self.limited_count != len(
            self.objects
        ) - len(completed):
            raise ValueError("flattened replay coverage disagrees with members")
        for rows, actual in (
            (completed, self.completed_counts),
            (self.objects, self.attempted_counts),
        ):
            expected = TokenCounts(
                **{
                    name: sum(getattr(row.replay.counts, name) for row in rows)
                    for name in ("missing", "remaining", "consumed", "produced")
                }
            )
            if expected != actual:
                raise ValueError("flattened aggregate counts disagree with members")
        if self.source_event_count != len(self.scope.events):
            raise ValueError("flattened source event count disagrees with scope")
        if self.projected_event_occurrence_count != sum(
            row.replay.event_count for row in self.objects
        ):
            raise ValueError("flattened occurrence count disagrees with members")
        if self.log_deviation_count != sum(
            row.replay.log_deviation_count for row in self.objects
        ):
            raise ValueError("flattened deviation count disagrees with members")
        if self.token_fitness != _fitness(
            self.completed_counts, not self.limited_count
        ):
            raise ValueError("flattened fitness disagrees with token-weighted totals")


def _fitness(counts: TokenCounts, completed: bool) -> float | None:
    if not completed or not counts.consumed or not counts.produced:
        return None
    return 0.5 * (1 - counts.missing / counts.consumed) + 0.5 * (
        1 - counts.remaining / counts.produced
    )


def _tokens(counts: Counter[ObjectToken]) -> tuple[ObjectToken, ...]:
    return tuple(sorted(counts.elements()))


def _incidence(net: ObjectCentricPetriNet, binding: Binding):
    """Validate exact participation and return unit object-token incidence."""
    places = {place.id: place.object_type for place in net.places}
    arcs = tuple(a for a in net.arcs if binding.transition_id in (a.source, a.target))
    required = {
        places[a.source if a.target == binding.transition_id else a.target]
        for a in arcs
    }
    objects = dict(binding.objects)
    if set(objects) != required:
        return None
    incoming: Counter[ObjectToken] = Counter()
    outgoing: Counter[ObjectToken] = Counter()
    for arc in arcs:
        consume = arc.target == binding.transition_id
        place = arc.source if consume else arc.target
        selected = objects[places[place]]
        if len(selected) < arc.min_objects or (
            arc.max_objects is not None and len(selected) > arc.max_objects
        ):
            return None
        (incoming if consume else outgoing).update(
            ObjectToken(place, obj) for obj in selected
        )
    return incoming, outgoing


def _event_bindings(net: ObjectCentricPetriNet, event: ObjectEventParticipation):
    places = {place.id: place.object_type for place in net.places}
    selected = dict(event.objects)
    bindings = []
    for transition in net.transitions:
        if transition.activity != event.activity:
            continue
        required = {
            places[a.source if a.target == transition.id else a.target]
            for a in net.arcs
            if transition.id in (a.source, a.target)
        }
        if set(selected) - required:
            continue
        binding = Binding(
            transition.id,
            tuple((kind, selected.get(kind, ())) for kind in sorted(required)),
        )
        if _incidence(net, binding) is not None:
            bindings.append(binding)
    return tuple(bindings)


@dataclass(frozen=True, slots=True)
class _Closure:
    states: tuple[tuple[ObjectMarking, tuple[Binding, ...]], ...]
    choice: tuple[ObjectMarking, tuple[Binding, ...], Binding | None] | None
    limit_reason: str | None


def _closure(net, silent_net, start, bindings, spec):
    queue = deque([(start, ())])
    paths = {start: ()}
    reason = None
    while queue:
        current, path = queue.popleft()
        if bindings is None:
            if current == net.final_marking:
                return _Closure(tuple(paths.items()), (current, path, None), None)
        else:
            for binding in bindings:
                incoming, _ = _incidence(net, binding)
                if not incoming - Counter(current.tokens):
                    return _Closure(
                        tuple(paths.items()), (current, path, binding), None
                    )
        enumeration = enumerate_enabled_bindings(
            silent_net,
            current,
            max_bindings=spec.max_bindings,
        )
        if not enumeration.complete:
            reason = "silent_binding_limit"
        for binding in enumeration.bindings:
            after = fire_binding(net, current, binding)
            if after in paths:
                continue
            if len(paths) >= spec.silent_max_states:
                reason = reason or "silent_state_limit"
                continue
            following = path + (binding,)
            paths[after] = following
            queue.append((after, following))
    return _Closure(tuple(paths.items()), None, reason)


def _path_key(path):
    return tuple((binding.transition_id, binding.objects) for binding in path)


def _order(scope):
    pending = {event.event_id: set() for event in scope.events}
    successors = {event.event_id: set() for event in scope.events}
    for edge in scope.precedence:
        pending[edge.successor_event_id].add(edge.predecessor_event_id)
        successors[edge.predecessor_event_id].add(edge.successor_event_id)
    ready = []
    for event, previous in pending.items():
        if not previous:
            heappush(ready, event)
    result = []
    while ready:
        event = heappop(ready)
        result.append(event)
        for following in successors[event]:
            pending[following].remove(event)
            if not pending[following]:
                heappush(ready, following)
    if len(result) != len(pending):
        raise ValueError("object event precedence must be acyclic")
    return tuple(result)


def _joint(scope, net, spec):
    silent_ids = {t.id for t in net.transitions if t.activity is None}
    silent_net = ObjectCentricPetriNet(
        net.places,
        tuple(t for t in net.transitions if t.id in silent_ids),
        tuple(a for a in net.arcs if a.source in silent_ids or a.target in silent_ids),
        net.initial_marking,
        net.final_marking,
        net.objects,
    )
    current = net.initial_marking
    steps = [
        ObjectReplayStep(
            "initial", None, None, (), current.tokens, produced_tokens=current.tokens
        )
    ]
    searches = []
    order = _order(scope)
    events = {event.event_id: event for event in scope.events}
    processed = deviations = 0

    def finish(reason=None, final_reached=None):
        counts = TokenCounts(
            missing=sum(len(s.inserted_tokens) for s in steps),
            remaining=len(current.tokens),
            consumed=sum(len(s.consumed_tokens) for s in steps),
            produced=sum(len(s.produced_tokens) for s in steps),
        )
        return ObjectReplay(
            model_digest(net),
            scope,
            "limited" if reason else "completed",
            order,
            processed,
            deviations,
            tuple(steps),
            tuple(searches),
            counts,
            _fitness(counts, reason is None),
            None if reason else not (counts.missing or counts.remaining or deviations),
            final_reached,
            current.tokens,
            reason,
        )

    def follow(path, *, event_id=None, inserted=()):
        nonlocal current
        for index, binding in enumerate(path):
            additions = inserted if index == len(path) - 1 else ()
            incoming, outgoing = _incidence(net, binding)
            before = current.tokens
            repaired = ObjectMarking(before + additions)
            current = fire_binding(net, repaired, binding)
            visible = event_id if index == len(path) - 1 else None
            steps.append(
                ObjectReplayStep(
                    "visible" if visible is not None else "silent",
                    visible,
                    binding,
                    before,
                    current.tokens,
                    additions,
                    _tokens(incoming),
                    _tokens(outgoing),
                )
            )

    for event_id in order:
        event = events[event_id]
        bindings = _event_bindings(net, event)
        if not bindings:
            reason = (
                "unknown_activity"
                if not any(t.activity == event.activity for t in net.transitions)
                else "inadmissible_event_participation"
            )
            steps.append(
                ObjectReplayStep(
                    "log_deviation",
                    event_id,
                    None,
                    current.tokens,
                    current.tokens,
                    deviation_reason=reason,
                )
            )
            deviations += 1
            processed += 1
            continue
        closure = _closure(net, silent_net, current, bindings, spec)
        searches.append(
            ObjectReplaySearch(
                event_id,
                len(closure.states),
                closure.choice is None and not closure.limit_reason,
                closure.limit_reason,
            )
        )
        if closure.limit_reason:
            return finish(closure.limit_reason)
        if closure.choice is not None:
            _, path, binding = closure.choice
        else:
            options = []
            for state, path in closure.states:
                for binding in bindings:
                    incoming, _ = _incidence(net, binding)
                    missing = incoming - Counter(state.tokens)
                    options.append(
                        (
                            sum(missing.values()),
                            len(path),
                            _path_key(path),
                            binding.transition_id,
                            binding.objects,
                            state,
                            path,
                            binding,
                        )
                    )
            *_, state, path, binding = min(options, key=lambda item: item[:5])
        follow(path)
        incoming, _ = _incidence(net, binding)
        additions = _tokens(incoming - Counter(current.tokens))
        follow((binding,), event_id=event_id, inserted=additions)
        processed += 1

    closure = _closure(net, silent_net, current, None, spec)
    searches.append(
        ObjectReplaySearch(
            None,
            len(closure.states),
            closure.choice is None and not closure.limit_reason,
            closure.limit_reason,
        )
    )
    if closure.limit_reason:
        return finish(closure.limit_reason)
    reached = closure.choice is not None
    if reached:
        _, path, _ = closure.choice
    else:
        final = Counter(net.final_marking.tokens)
        state, path = min(
            closure.states,
            key=lambda item: (
                sum((final - Counter(item[0].tokens)).values())
                + sum((Counter(item[0].tokens) - final).values()),
                sum((final - Counter(item[0].tokens)).values()),
                len(item[1]),
                _path_key(item[1]),
            ),
        )
    follow(path)
    additions = _tokens(Counter(net.final_marking.tokens) - Counter(current.tokens))
    before = current.tokens
    ending = Counter(before + additions) - Counter(net.final_marking.tokens)
    current = ObjectMarking(_tokens(ending))
    steps.append(
        ObjectReplayStep(
            "finalize",
            None,
            None,
            before,
            current.tokens,
            additions,
            net.final_marking.tokens,
        )
    )
    return finish(final_reached=reached)


def _prepare_scope(log, net, spec):
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be ObjectCentricPetriNet")
    if not isinstance(spec, ObjectReplaySpec):
        raise TypeError("spec must be ObjectReplaySpec")
    request = ObjectReplayRequest(model_digest(net), spec)
    context, issues = _prepare(log)
    if context is None:
        return None, None, request, issues, ComputeStatus.INVALID_INPUT
    scope, issues = build_object_event_scope(
        context,
        object_types=spec.object_types,
        qualifiers=spec.qualifiers,
        tie_policy=spec.tie_policy,
    )
    if scope is None:
        return context, None, request, issues, ComputeStatus.UNAVAILABLE
    failures = validate_object_model_scope(net, scope, spec.object_types)
    if failures:
        return context, None, request, issues + failures, ComputeStatus.INVALID_INPUT
    return context, scope, request, issues, ComputeStatus.COMPUTED


OBJECT_TOKEN_REPLAY_OPERATOR_ID = "pix.object_centric.token_replay"
FLATTENED_TOKEN_REPLAY_OPERATOR_ID = "pix.object_centric.flattened_token_replay"


def replay_object_log(
    log: OCEL | ComputationContext,
    net: ObjectCentricPetriNet,
    spec: ObjectReplaySpec,
) -> ComputationResult[ObjectReplay]:
    """Replay exact shared bindings, retaining repairs and resource limits."""
    context, scope, request, issues, status = _prepare_scope(
        log,
        net,
        spec,
    )
    if scope is None:
        return _result(
            OBJECT_TOKEN_REPLAY_OPERATOR_ID, context, request, status, None, issues
        )
    value = _joint(scope, net, spec)
    if value.limit_reason:
        status = ComputeStatus.PARTIAL
        issues += (
            ComputeIssue(value.limit_reason, "Silent replay search is incomplete"),
        )
    return _result(
        OBJECT_TOKEN_REPLAY_OPERATOR_ID, context, request, status, value, issues
    )


def _project(net, object_id, object_type):
    places = {place.id for place in net.places if place.object_type == object_type}
    arcs = tuple(a for a in net.arcs if a.source in places or a.target in places)
    transitions = {a.target if a.source in places else a.source for a in arcs}

    def marking(source):
        counts = Counter(
            token.place_id for token in source.tokens if token.object_id == object_id
        )
        return Marking(tuple(sorted(counts.items())))

    return PetriNet(
        tuple(Place(place) for place in sorted(places)),
        tuple(t for t in net.transitions if t.id in transitions),
        tuple(Arc(a.source, a.target) for a in arcs),
        marking(net.initial_marking),
        marking(net.final_marking),
    )


def replay_flattened_object_log(
    log: OCEL | ComputationContext,
    net: ObjectCentricPetriNet,
    spec: ObjectReplaySpec,
) -> ComputationResult[FlattenedReplay]:
    """Replay every concrete object's projection, including isolated objects.

    Projection removes other object types and treats incident arcs as unit arcs;
    joint cardinality, synchronized bindings and no-participant events are lost.
    Shared events therefore count multiple times. Fitness uses summed token
    counts, never an unweighted average of object/type fitness values.
    """
    context, scope, request, issues, status = _prepare_scope(
        log,
        net,
        spec,
    )
    if scope is None:
        return _result(
            FLATTENED_TOKEN_REPLAY_OPERATOR_ID, context, request, status, None, issues
        )
    rows = []
    represented = set()
    for object_id, object_type in scope.selected_objects:
        events = [
            event
            for event in scope.events
            if object_id in dict(event.objects).get(object_type, ())
        ]
        events.sort(
            key=lambda event: (
                context.events_by_id[event.event_id].time,
                event.event_id,
            )
        )
        represented.update(event.event_id for event in events)
        trace = ObjectTrace(
            object_id,
            object_type,
            tuple(
                TraceEvent(
                    event.event_id,
                    event.activity,
                    context.events_by_id[event.event_id].time,
                    (),
                )
                for event in events
            ),
        )
        projected = _project(net, object_id, object_type)
        replay = _replay_trace(trace, projected, ReplaySpec(spec.silent_max_states))
        rows.append(
            FlattenedObjectReplay(
                object_id,
                object_type,
                model_digest(projected),
                replay,
                _fitness(replay.counts, replay.status == "completed"),
            )
        )
    completed = tuple(row for row in rows if row.replay.status == "completed")

    def total(selected):
        return TokenCounts(
            **{
                name: sum(getattr(row.replay.counts, name) for row in selected)
                for name in ("missing", "remaining", "consumed", "produced")
            }
        )

    counts = total(completed)
    limited = len(rows) - len(completed)
    value = FlattenedReplay(
        model_digest(net),
        scope,
        tuple(rows),
        len(completed),
        limited,
        len(scope.events),
        sum(row.replay.event_count for row in rows),
        tuple(
            event.event_id
            for event in scope.events
            if event.event_id not in represented
        ),
        sum(row.replay.log_deviation_count for row in rows),
        counts,
        total(rows),
        _fitness(counts, not limited),
    )
    if limited:
        status = ComputeStatus.PARTIAL
        issues += (
            ComputeIssue(
                "silent_state_limit", "Flattened replay has incomplete objects"
            ),
        )
    return _result(
        FLATTENED_TOKEN_REPLAY_OPERATOR_ID, context, request, status, value, issues
    )


RESULT_SCHEMAS = {
    OBJECT_TOKEN_REPLAY_OPERATOR_ID: (
        "object-token-replay",
        ObjectReplayRequest,
        ObjectReplay,
    ),
    FLATTENED_TOKEN_REPLAY_OPERATOR_ID: (
        "flattened-object-token-replay",
        ObjectReplayRequest,
        FlattenedReplay,
    ),
}

__all__ = (
    "ObjectReplaySpec",
    "ObjectReplayRequest",
    "ObjectReplayStep",
    "ObjectReplaySearch",
    "ObjectReplay",
    "FlattenedObjectReplay",
    "FlattenedReplay",
    "replay_object_log",
    "replay_flattened_object_log",
    "RESULT_SCHEMAS",
)
