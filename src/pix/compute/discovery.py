"""Native noise-free trace discovery and process-tree workflow-net conversion.

Algorithm ``pix.inductive_cut.v1`` tries weak-component XOR, plain sequence,
bidirectional-edge parallel with boundary safeguards, conservative do/redo
loop, and strict tau-loop decomposition, in that order. It is not IM/IMf/IMd:
it omits strict-sequence optional-block merging, some parallel/loop merges and
activity-removal fallthroughs of reference IM. If no decomposition succeeds,
an explicit flower diagnostic accompanies ``loop(xor(alphabet), tau)``.

``pix.im.v1`` separately implements the formal XOR, plain-sequence, parallel,
and loop cuts. It completes parallel boundary groups and merges loop branches
violating the formal boundary conditions into the body. Its ordered fallthrough
profile is activity-once, activity-removal enabling a structural cut, strict
tau-loop, general tau-loop, then ``loop(tau, xor(alphabet))`` (including epsilon).
Empty traces are factored as XOR(tau, remaining behavior). This is an explicitly
defined log-based IM profile, not original B-prime-2013's empty-trace policy,
the optional-block strict-sequence refinement, IMf, IMd, or release parity.

Definitions and primary-source versions are recorded in
``docs/architecture/5_PIX_LOG_BASED_INDUCTIVE_MINER.md``. The original conservative
profile and its request identities remain unchanged.

Every cut splits the original traces, including empty projections, rather than
mining only their DFG. Frequency is ignored only because noise is explicitly
zero. All observed behavior is admitted; precision and rediscoverability are
not promised. Separate source and parent computation identities are retained.
"""

from __future__ import annotations

from collections.abc import Callable

from pix.compute._common import _result
from pix.contracts.analysis import ObjectTrace, TraceEvent, TraceSet
from pix.contracts.discovery import DiscoverySpec, ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.discover_process_tree"
OPERATOR_VERSION = "1.0.0"
_Trace = tuple[str, ...]
_Log = tuple[_Trace, ...]


def _key(tree: ProcessTree) -> tuple:
    return tree.operator, tree.activity or "", tuple(map(_key, tree.children))


def _node(operator: str, children: tuple[ProcessTree, ...]) -> ProcessTree:
    if operator in ("sequence", "xor", "parallel"):
        children = tuple(
            sub
            for child in children
            for sub in (child.children if child.operator == operator else (child,))
        )
        if operator == "sequence":
            children = tuple(child for child in children if child.operator != "tau")
        if operator in ("xor", "parallel"):
            children = tuple(sorted(children, key=_key))
        if not children:
            return ProcessTree("tau")
        if len(children) == 1:
            return children[0]
    return ProcessTree(operator, children=children)


def _components(
    activities: set[str], connected: Callable[[str, str], bool]
) -> list[set[str]]:
    unseen = set(activities)
    groups: list[set[str]] = []
    while unseen:
        component = {min(unseen)}
        pending = list(component)
        unseen -= component
        while pending:
            current = pending.pop()
            neighbors = {other for other in unseen if connected(current, other)}
            unseen -= neighbors
            component |= neighbors
            pending.extend(sorted(neighbors))
        groups.append(component)
    return groups


def _project(log: _Log, alphabet: set[str]) -> _Log:
    return tuple(sorted({tuple(a for a in trace if a in alphabet) for trace in log}))


def _sequence_groups(alphabet: set[str], edges: set[tuple[str, str]]) -> list[set[str]]:
    reachable = {a: {b for x, b in edges if x == a} for a in alphabet}
    for via in sorted(alphabet):
        for source in sorted(alphabet):
            if via in reachable[source]:
                reachable[source] |= reachable[via]
    groups = _components(
        alphabet,
        lambda a, b: (b in reachable[a]) == (a in reachable[b]),
    )
    # Every cross-group activity pair is strictly ordered. Ordering by number
    # of predecessors is deterministic; the trace check is a fitting safeguard.
    return sorted(
        groups,
        key=lambda group: sum(
            any(b in reachable[a] for a in other for b in group)
            for other in groups
            if other is not group
        ),
    )


def _loop_segments(
    log: _Log,
    body: set[str],
    redo_groups: list[set[str]],
    starts: set[str],
    ends: set[str],
) -> tuple[_Log, _Log] | None:
    branch = {a: i for i, group in enumerate(redo_groups) for a in group}
    body_log: set[_Trace] = set()
    redo_log: set[_Trace] = set()
    for trace in log:
        blocks: list[_Trace] = []
        begin = 0
        for index in range(1, len(trace)):
            if (trace[index] in body) != (trace[index - 1] in body):
                blocks.append(trace[begin:index])
                begin = index
        blocks.append(trace[begin:])
        for block in blocks:
            if block[0] in body:
                if block[0] not in starts or block[-1] not in ends:
                    return None
                body_log.add(block)
            else:
                if len({branch[a] for a in block}) != 1:
                    return None
                redo_log.add(block)
    if not redo_log:
        return None
    return tuple(sorted(body_log)), tuple(sorted(redo_log))


class _DepthExceeded(Exception):
    pass


def _mine(
    log: _Log, spec: DiscoverySpec, issues: list[ComputeIssue], path: tuple[str, ...]
) -> ProcessTree:
    if len(path) >= spec.max_depth:
        raise _DepthExceeded
    nonempty = tuple(trace for trace in log if trace)
    if not nonempty:
        return ProcessTree("tau")
    if len(nonempty) != len(log):
        return _node(
            "xor",
            (ProcessTree("tau"), _mine(nonempty, spec, issues, (*path, "nonempty"))),
        )
    alphabet = {activity for trace in log for activity in trace}
    if len(alphabet) == 1:
        leaf = ProcessTree("activity", activity=min(alphabet))
        return (
            leaf
            if all(len(trace) == 1 for trace in log)
            else _node("loop", (leaf, ProcessTree("tau")))
        )
    edges = {(a, b) for trace in log for a, b in zip(trace, trace[1:])}
    starts = {trace[0] for trace in log}
    ends = {trace[-1] for trace in log}

    def recurse(operator: str, sublogs: tuple[_Log, ...]) -> ProcessTree:
        return _node(
            operator,
            tuple(
                _mine(sublog, spec, issues, (*path, f"{operator}:{index}"))
                for index, sublog in enumerate(sublogs)
            ),
        )

    groups = _components(alphabet, lambda a, b: (a, b) in edges or (b, a) in edges)
    if len(groups) > 1:
        return recurse(
            "xor",
            tuple(
                tuple(trace for trace in log if trace[0] in group) for group in groups
            ),
        )

    groups = _sequence_groups(alphabet, edges)
    group_index = {a: i for i, group in enumerate(groups) for a in group}
    if len(groups) > 1 and all(
        group_index[a] <= group_index[b]
        for trace in log
        for a, b in zip(trace, trace[1:])
    ):
        return recurse("sequence", tuple(_project(log, group) for group in groups))

    groups = _components(
        alphabet, lambda a, b: (a, b) not in edges or (b, a) not in edges
    )
    if len(groups) > 1 and all(group & starts and group & ends for group in groups):
        return recurse("parallel", tuple(_project(log, group) for group in groups))

    body = starts | ends
    redo_groups = _components(
        alphabet - body, lambda a, b: (a, b) in edges or (b, a) in edges
    )
    if redo_groups:
        segments = _loop_segments(log, body, redo_groups, starts, ends)
        if segments is not None:
            return recurse("loop", segments)

    # A strict tau-loop splits only between an observed end and observed start.
    # It needs an actual split to ensure recursive trace lengths decrease.
    segments: set[_Trace] = set()
    split = False
    for trace in log:
        begin = 0
        for index in range(1, len(trace)):
            if trace[index - 1] in ends and trace[index] in starts:
                segments.add(trace[begin:index])
                begin = index
                split = True
        segments.add(trace[begin:])
    if split:
        return _node(
            "loop",
            (
                _mine(tuple(sorted(segments)), spec, issues, (*path, "tau_loop")),
                ProcessTree("tau"),
            ),
        )

    issues.append(
        ComputeIssue(
            "flower_fallthrough",
            "No supported cut; this subtree admits every nonempty string over "
            f"{tuple(sorted(alphabet))!r}",
            ("recursive_cut", *path),
        )
    )
    return _node(
        "loop",
        (
            _node("xor", tuple(ProcessTree("activity", a) for a in sorted(alphabet))),
            ProcessTree("tau"),
        ),
    )


def _im_parallel_groups(
    alphabet: set[str],
    edges: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
) -> tuple[set[str], ...]:
    """Find a maximum-cardinality partition satisfying the parallel cut.

    Missing either cross direction makes an atomic inseparable group. Each
    final group must contain an observed start and an observed end. Keep the
    already-complete groups, pair start-only and end-only groups, then attach
    leftovers. No valid partition can have more groups: each additional branch
    consumes at least one start-bearing and one end-bearing atomic group.
    """
    units = _components(
        alphabet, lambda a, b: (a, b) not in edges or (b, a) not in edges
    )
    complete = [group for group in units if group & starts and group & ends]
    start_only = [group for group in units if group & starts and not group & ends]
    end_only = [group for group in units if group & ends and not group & starts]
    neither = [group for group in units if not group & (starts | ends)]
    pairs = min(len(start_only), len(end_only))
    groups = complete + [start_only[i] | end_only[i] for i in range(pairs)]
    if not groups:
        return ()
    groups.sort(key=lambda group: tuple(sorted(group)))
    for group in start_only[pairs:] + end_only[pairs:] + neither:
        groups[0] |= group
    return tuple(sorted(groups, key=lambda group: tuple(sorted(group))))


def _im_loop_groups(
    alphabet: set[str],
    edges: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
) -> tuple[set[str], ...]:
    """Complete the maximal loop partition from all six formal conditions.

    The original body contains every global start/end. Redo components have no
    mutual edges. A redo exit must connect to every start and no other body
    activity; a redo entry must connect from every end and no other body
    activity. Components violating either rule must be absorbed into the body.
    Absorbing a whole component creates no new crossing to another component.
    """
    initial_body = starts | ends
    candidates = _components(
        alphabet - initial_body,
        lambda a, b: (a, b) in edges or (b, a) in edges,
    )
    body = set(initial_body)
    redo = []
    for group in candidates:
        valid = True
        for activity in group:
            exits = {b for b in initial_body if (activity, b) in edges}
            entries = {b for b in initial_body if (b, activity) in edges}
            if (exits and exits != starts) or (entries and entries != ends):
                valid = False
                break
        if valid:
            redo.append(group)
        else:
            body |= group
    return (body, *redo) if redo else ()


def _im_cut(log: _Log) -> tuple[str, tuple[set[str], ...]] | None:
    """Ordered, complete structural cut detection for an epsilon-free log.

    The caller factors epsilon before applying a cut. An activity-removal witness
    must itself be epsilon-free: a base case, optionality or eventual fallback
    does not count as exposing a nontrivial structural cut.
    """
    if not log or any(not trace for trace in log):
        return None
    alphabet = {activity for trace in log for activity in trace}
    edges = {(a, b) for trace in log for a, b in zip(trace, trace[1:])}
    starts = {trace[0] for trace in log}
    ends = {trace[-1] for trace in log}
    xor = tuple(_components(alphabet, lambda a, b: (a, b) in edges or (b, a) in edges))
    if len(xor) > 1:
        return "xor", xor
    sequence = tuple(_sequence_groups(alphabet, edges))
    if len(sequence) > 1:
        return "sequence", sequence
    parallel = _im_parallel_groups(alphabet, edges, starts, ends)
    if len(parallel) > 1:
        return "parallel", parallel
    loop = _im_loop_groups(alphabet, edges, starts, ends)
    if loop:
        return "loop", loop
    return None


def _im_split(
    log: _Log, operator: str, groups: tuple[set[str], ...]
) -> tuple[_Log, ...]:
    if operator == "xor":
        return tuple(
            tuple(trace for trace in log if trace[0] in group) for group in groups
        )
    if operator != "loop":
        return tuple(_project(log, group) for group in groups)
    membership = {activity: i for i, group in enumerate(groups) for activity in group}
    segments: list[set[_Trace]] = [set() for _ in groups]
    for trace in log:
        begin = 0
        for index in range(1, len(trace)):
            if membership[trace[index]] != membership[trace[index - 1]]:
                segments[membership[trace[begin]]].add(trace[begin:index])
                begin = index
        segments[membership[trace[begin]]].add(trace[begin:])
    return tuple(tuple(sorted(part)) for part in segments)


def _im_tau_segments(log: _Log, *, strict: bool) -> _Log | None:
    starts = {trace[0] for trace in log}
    ends = {trace[-1] for trace in log}
    segments: set[_Trace] = set()
    split = False
    for trace in log:
        begin = 0
        for index in range(1, len(trace)):
            if trace[index] in starts and (not strict or trace[index - 1] in ends):
                segments.add(trace[begin:index])
                begin = index
                split = True
        segments.add(trace[begin:])
    return tuple(sorted(segments)) if split else None


def _mine_im(
    log: _Log, spec: DiscoverySpec, issues: list[ComputeIssue], path: tuple[str, ...]
) -> ProcessTree:
    if len(path) >= spec.max_depth:
        raise _DepthExceeded
    nonempty = tuple(trace for trace in log if trace)
    if not nonempty:
        return ProcessTree("tau")
    if len(nonempty) != len(log):
        return _node(
            "xor",
            (ProcessTree("tau"), _mine_im(nonempty, spec, issues, (*path, "nonempty"))),
        )
    alphabet = {activity for trace in log for activity in trace}
    if len(alphabet) == 1 and all(len(trace) == 1 for trace in log):
        return ProcessTree("activity", min(alphabet))

    def child(sublog: _Log, label: str) -> ProcessTree:
        return _mine_im(sublog, spec, issues, (*path, label))

    cut = _im_cut(log)
    if cut is not None:
        operator, groups = cut
        children = tuple(
            child(sublog, f"{operator}:{index}")
            for index, sublog in enumerate(_im_split(log, operator, groups))
        )
        if operator == "loop":
            # The formal n-ary loop chooses exactly one redo branch each time.
            return _node("loop", (children[0], _node("xor", children[1:])))
        return _node(operator, children)

    # These are ordered fallthroughs, not additional formal cut definitions.
    # Activity selection is lexical, independent of input iteration/hash order.
    for activity in sorted(alphabet):
        if all(trace.count(activity) == 1 for trace in log):
            issues.append(
                ComputeIssue(
                    "im_activity_once_fallthrough",
                    f"Activity {activity!r} occurs once in every trace; mined as a parallel branch",
                    ("recursive_cut", *path),
                )
            )
            return _node(
                "parallel",
                (
                    ProcessTree("activity", activity),
                    child(_project(log, alphabet - {activity}), "activity_once:rest"),
                ),
            )
    for activity in sorted(alphabet):
        rest = _project(log, alphabet - {activity})
        if _im_cut(rest) is not None:
            issues.append(
                ComputeIssue(
                    "im_activity_concurrent_fallthrough",
                    f"Removing activity {activity!r} exposes a cut; mined as a parallel branch",
                    ("recursive_cut", *path),
                )
            )
            return _node(
                "parallel",
                (
                    child(_project(log, {activity}), "activity_concurrent:selected"),
                    child(rest, "activity_concurrent:rest"),
                ),
            )
    for strict in (True, False):
        segments = _im_tau_segments(log, strict=strict)
        if segments is not None:
            mode = "strict" if strict else "general"
            issues.append(
                ComputeIssue(
                    "im_tau_loop_fallthrough",
                    f"Applied {mode} tau-loop splitting before observed start activities",
                    ("recursive_cut", *path),
                )
            )
            return _node(
                "loop", (child(segments, f"tau_loop:{mode}"), ProcessTree("tau"))
            )
    issues.append(
        ComputeIssue(
            "flower_fallthrough",
            "No IM cut or preceding fallthrough applies; this subtree admits epsilon "
            f"and every string over {tuple(sorted(alphabet))!r}",
            ("recursive_cut", *path),
        )
    )
    return _node(
        "loop",
        (
            ProcessTree("tau"),
            _node("xor", tuple(ProcessTree("activity", a) for a in sorted(alphabet))),
        ),
    )


def discover_process_tree(
    trace_result: ComputationResult[TraceSet], spec: DiscoverySpec
) -> ComputationResult[ProcessTree]:
    """Discover from explicitly reconstructed object traces, preserving lineage."""
    if not isinstance(trace_result, ComputationResult):
        raise TypeError("trace_result must be ComputationResult[TraceSet]")
    if not isinstance(spec, DiscoverySpec):
        raise TypeError("spec must be DiscoverySpec")
    parents = (trace_result.computation_id,) if trace_result.computation_id else ()

    def result(status, value=None, issues=()):
        return _result(
            OPERATOR_ID,
            None,
            spec,
            status,
            value,
            issues,
            parent_computation_ids=parents,
            operator_version=OPERATOR_VERSION,
            source_digest=trace_result.source_digest,
        )

    if trace_result.status is not ComputeStatus.COMPUTED:
        return result(
            ComputeStatus.INVALID_INPUT
            if trace_result.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "upstream_not_computed",
                    f"Trace reconstruction status is {trace_result.status.value}; "
                    "discovery requires a completely computed trace population",
                ),
                *trace_result.issues,
            ),
        )
    if not isinstance(trace_result.value, TraceSet):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "trace_input_required",
                    "Discovery requires TraceSet; DFG input is not converted",
                ),
            ),
        )
    if not isinstance(trace_result.value.traces, tuple):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue("invalid_trace_input", "TraceSet.traces must be a tuple"),
            ),
        )
    if not trace_result.value.traces:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "empty_population",
                    "No object traces are available to discover behavior",
                ),
            ),
        )
    try:
        object_ids: set[str] = set()
        for trace in trace_result.value.traces:
            if not isinstance(trace, ObjectTrace) or not isinstance(
                trace.events, tuple
            ):
                raise TypeError("TraceSet must contain immutable ObjectTrace values")
            if trace.object_type != trace_result.value.object_type:
                raise ValueError("trace object type differs from TraceSet object type")
            if not isinstance(trace.object_id, str) or not trace.object_id.strip():
                raise ValueError("object trace requires a nonblank text object ID")
            if trace.object_id in object_ids:
                raise ValueError("TraceSet contains a duplicate object trace")
            object_ids.add(trace.object_id)
            if not all(isinstance(event, TraceEvent) for event in trace.events):
                raise TypeError("ObjectTrace must contain TraceEvent values")
        log = tuple(
            sorted(
                {
                    tuple(event.activity for event in trace.events)
                    for trace in trace_result.value.traces
                }
            )
        )
        for trace in log:
            for activity in trace:
                ProcessTree("activity", activity)
    except (AttributeError, TypeError, ValueError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_trace_input", str(exc)),),
        )
    # A completed upstream calculation can still carry policy/evidence warnings.
    # Preserve them alongside this miner's diagnostics for both profiles.
    issues: list[ComputeIssue] = list(trace_result.issues)
    try:
        miner = _mine_im if spec.algorithm == "pix.im.v1" else _mine
        tree = miner(log, spec, issues, ())
    except _DepthExceeded:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "discovery_depth_limit",
                    "Discovery exceeded the explicit recursion depth limit",
                ),
                *trace_result.issues,
            ),
        )
    return result(ComputeStatus.COMPUTED, tree, tuple(issues))


def process_tree_to_petri_net(tree: ProcessTree) -> PetriNet:
    """Convert block operators to a sound, labeled workflow net.

    Distinct tree leaves become distinct transitions even for repeated activity
    labels. Deterministic IDs derive from structural traversal, not random IDs.
    Generated nets use ordinary unit arcs and explicit initial/final markings.
    """
    if not isinstance(tree, ProcessTree):
        raise TypeError("tree must be ProcessTree")
    pending = [(tree, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > 128:
            raise ValueError("process tree exceeds supported depth 128")
        pending.extend((child, depth + 1) for child in node.children)
    places: list[Place] = []
    transitions: list[Transition] = []
    arcs: list[Arc] = []

    def place() -> str:
        identity = f"p{len(places):08d}"
        places.append(Place(identity))
        return identity

    def transition(
        activity: str | None, inputs: tuple[str, ...], outputs: tuple[str, ...]
    ):
        identity = f"t{len(transitions):08d}"
        transitions.append(Transition(identity, activity))
        arcs.extend(Arc(source, identity) for source in inputs)
        arcs.extend(Arc(identity, target) for target in outputs)

    def build(node: ProcessTree, source: str, sink: str, depth: int) -> None:
        if depth > 128:
            raise ValueError("process tree exceeds supported depth 128")
        if node.operator in ("activity", "tau"):
            transition(node.activity, (source,), (sink,))
        elif node.operator == "sequence":
            boundaries = (source, *(place() for _ in node.children[:-1]), sink)
            for index, child in enumerate(node.children):
                build(child, boundaries[index], boundaries[index + 1], depth + 1)
        elif node.operator == "xor":
            for child in sorted(node.children, key=_key):
                build(child, source, sink, depth + 1)
        elif node.operator == "parallel":
            children = sorted(node.children, key=_key)
            inputs = tuple(place() for _ in children)
            outputs = tuple(place() for _ in children)
            transition(None, (source,), inputs)
            for child, entry, exit_ in zip(children, inputs, outputs):
                build(child, entry, exit_, depth + 1)
            transition(None, outputs, (sink,))
        else:
            entry, exit_ = place(), place()
            transition(None, (source,), (entry,))
            build(node.children[0], entry, exit_, depth + 1)
            build(node.children[1], exit_, entry, depth + 1)
            transition(None, (exit_,), (sink,))

    source, sink = place(), place()
    build(tree, source, sink, 0)
    return PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking(((source, 1),)),
        Marking(((sink, 1),)),
    )


__all__ = ("discover_process_tree", "process_tree_to_petri_net")
