"""Native evolutionary discovery over finite, acyclic process trees.

``pix.genetic.finite_tree.v1`` searches activity, tau, sequence, XOR and parallel
trees. It does not implement PM4Py's genetic heuristic-net representation or
its replay objective. A candidate's complete finite language is enumerated;
oversized candidates are rejected, never scored from a truncated language.

The objective combines frequency-weighted observed-case acceptance, empirical
language precision (observed distinct words / accepted distinct words), and
inverse node count. These are explicit training metrics, not alignment fitness,
escaping-edge precision, statistical generalization, or an optimality proof.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from random import Random
from typing import ClassVar

from pix.case_centric._input import as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseLog


@dataclass(frozen=True, slots=True)
class GeneticMinerSpec:
    """A seed is reproducible for the same PIX/Python implementation and input.

    Nonempty ``initial_population`` replaces automatic observed-word seeds;
    undersized populations are filled by copies. Seed depth cannot exceed 32
    and the full seed tuple cannot exceed 10,000 expanded node occurrences,
    including seeds rejected by tighter candidate budgets; the request itself
    must remain serializable. This permits controlled
    experiments. Elites always survive, including when all offspring fail
    resource bounds. Reaching the generation/stagnation criterion is a normal
    heuristic stop; exhausting ``max_evaluations`` is reported as partial.
    """

    SPEC_TYPE: ClassVar[str] = "pix.case_centric.GeneticMinerSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    seed: int = 0
    population_size: int = 24
    generations: int = 40
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float | int = 0.7
    mutation_rate: float | int = 0.8
    stagnation_generations: int = 15
    acceptance_weight: float | int = 0.7
    precision_weight: float | int = 0.2
    simplicity_weight: float | int = 0.1
    max_nodes: int = 127
    max_depth: int = 16
    max_language_words: int = 4096
    max_language_operations: int = 200_000
    max_evaluations: int = 10_000
    initial_population: tuple[ProcessTree, ...] = ()

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be an integer")
        for field in (
            "population_size",
            "elite_count",
            "tournament_size",
            "stagnation_generations",
            "max_nodes",
            "max_depth",
            "max_language_words",
            "max_language_operations",
            "max_evaluations",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        if self.population_size < 2:
            raise ValueError("population_size must be at least 2")
        if self.elite_count >= self.population_size:
            raise ValueError("elite_count must be less than population_size")
        if self.tournament_size > self.population_size:
            raise ValueError("tournament_size cannot exceed population_size")
        if type(self.generations) is not int or self.generations < 0:
            raise ValueError("generations must be a nonnegative integer")
        if self.max_depth > 32:
            raise ValueError("max_depth cannot exceed 32")
        for field in ("crossover_rate", "mutation_rate"):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{field} must be finite and between 0 and 1")
        weights = (
            self.acceptance_weight,
            self.precision_weight,
            self.simplicity_weight,
        )
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not isfinite(v)
            or v < 0
            for v in weights
        ):
            raise ValueError("objective weights must be finite nonnegative numbers")
        if not isfinite(sum(weights)) or sum(weights) <= 0:
            raise ValueError("objective weights must have a finite positive sum")
        if not isinstance(self.initial_population, tuple) or not all(
            isinstance(t, ProcessTree) for t in self.initial_population
        ):
            raise TypeError("initial_population must be a tuple of ProcessTree")
        seed_nodes = 0
        for tree in self.initial_population:
            pending = [(tree, 1)]
            while pending:
                node, depth = pending.pop()
                seed_nodes += 1
                if seed_nodes > 10_000:
                    raise ValueError(
                        "initial_population cannot exceed 10000 expanded node occurrences"
                    )
                if depth > 32:
                    raise ValueError("initial_population tree depth cannot exceed 32")
                if node.operator == "loop":
                    raise ValueError(
                        "finite-tree genetic discovery does not support loop seeds"
                    )
                if seed_nodes + len(pending) + len(node.children) > 10_000:
                    raise ValueError(
                        "initial_population cannot exceed 10000 expanded node occurrences"
                    )
                pending.extend((child, depth + 1) for child in node.children)


@dataclass(frozen=True, slots=True)
class GeneticObjective:
    score: float
    observed_case_acceptance: float
    empirical_language_precision: float
    inverse_node_count: float
    accepted_cases: int
    total_cases: int
    accepted_observed_variants: int
    language_size: int
    node_count: int


@dataclass(frozen=True, slots=True)
class GeneticGeneration:
    generation: int
    best_score: float
    mean_score: float
    distinct_models: int
    evaluated_models: int
    rejected_models: int
    crossover_changes: int
    mutation_changes: int


@dataclass(frozen=True, slots=True)
class GeneticDiscovery:
    model: ProcessTree
    objective: GeneticObjective
    language: tuple[tuple[str, ...], ...]
    rejected_observed_variants: tuple[tuple[str, ...], ...]
    history: tuple[GeneticGeneration, ...]
    stop_reason: str
    evaluated_models: int
    rejected_models: int
    crossover_changes: int
    mutation_changes: int
    profile: str = "pix.genetic.finite_tree.v1"
    optimality_proven: bool = False


class _CandidateLimit(Exception):
    pass


class _EvaluationLimit(Exception):
    pass


def _shape(tree: ProcessTree, spec: GeneticMinerSpec) -> int:
    count = 0
    pending = [(tree, 1)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > spec.max_nodes or depth > spec.max_depth:
            raise _CandidateLimit("tree size or depth limit")
        if node.operator == "loop":
            raise _CandidateLimit("infinite-language operator")
        if count + len(pending) + len(node.children) > spec.max_nodes:
            raise _CandidateLimit("tree size limit")
        pending.extend((child, depth + 1) for child in node.children)
    return count


def _language(tree: ProcessTree, spec: GeneticMinerSpec) -> frozenset[tuple[str, ...]]:
    """Complete language with bounded intermediate sets and work accounting."""
    operations = 0

    def tick() -> None:
        nonlocal operations
        operations += 1
        if operations > spec.max_language_operations:
            raise _CandidateLimit("language work limit")

    def put(target, word):
        tick()
        target.add(word)
        if len(target) > spec.max_language_words:
            raise _CandidateLimit("language cardinality limit")

    def shuffles(left, right):
        pending = [(0, 0, ())]
        seen = {(0, 0, ())}
        while pending:
            i, j, prefix = pending.pop()
            tick()
            if i == len(left) and j == len(right):
                yield prefix
            for state in ([(i + 1, j, (*prefix, left[i]))] if i < len(left) else []) + (
                [(i, j + 1, (*prefix, right[j]))] if j < len(right) else []
            ):
                if state not in seen:
                    seen.add(state)
                    if len(seen) > spec.max_language_operations:
                        raise _CandidateLimit("shuffle work limit")
                    pending.append(state)

    def visit(node):
        tick()
        if node.operator == "activity":
            return {(node.activity,)}
        if node.operator == "tau":
            return {()}
        if node.operator == "xor":
            result = set()
            for child in node.children:
                for word in sorted(visit(child)):
                    put(result, word)
            return result
        result = {()}
        for child in node.children:
            following = set()
            child_words = visit(child)
            for left in sorted(result):
                for right in sorted(child_words):
                    tick()
                    if node.operator == "sequence":
                        put(following, left + right)
                    else:
                        for word in shuffles(left, right):
                            put(following, word)
            result = following
        return result

    return frozenset(visit(tree))


def _key(tree):
    return (tree.operator, tree.activity or "", tuple(_key(c) for c in tree.children))


def _join(operator: str, children: tuple[ProcessTree, ...]) -> ProcessTree:
    flat = []
    for child in children:
        if child.operator == operator:
            flat.extend(child.children)
        elif operator in ("sequence", "parallel") and child.operator == "tau":
            continue
        else:
            flat.append(child)
    if operator == "xor":
        flat = sorted(set(flat), key=_key)
    elif operator == "parallel":
        flat.sort(key=_key)
    if not flat:
        return ProcessTree("tau")
    if len(flat) == 1:
        return flat[0]
    return ProcessTree(operator, children=tuple(flat))


def _word_tree(word):
    return _join("sequence", tuple(ProcessTree("activity", activity=a) for a in word))


def _paths(tree, prefix=()):
    yield prefix, tree
    for index, child in enumerate(tree.children):
        yield from _paths(child, (*prefix, index))


def _replace(tree, path, replacement):
    if not path:
        return replacement
    children = list(tree.children)
    children[path[0]] = _replace(children[path[0]], path[1:], replacement)
    return _join(tree.operator, tuple(children))


def _factor(tree):
    """Language-preserving shared-prefix/suffix factoring for XOR branches."""
    if tree.operator != "xor":
        return tree
    branches = tuple(
        c.children if c.operator == "sequence" else (c,) for c in tree.children
    )
    if all(b[0] == branches[0][0] for b in branches):
        suffix = _join("xor", tuple(_join("sequence", b[1:]) for b in branches))
        return _join("sequence", (branches[0][0], suffix))
    if all(b[-1] == branches[0][-1] for b in branches):
        prefix = _join("xor", tuple(_join("sequence", b[:-1]) for b in branches))
        return _join("sequence", (prefix, branches[0][-1]))
    return tree


def _mutate(tree, rng, alphabet, words):
    path, node = rng.choice(tuple(_paths(tree)))
    action = rng.randrange(7)
    atom = (
        ProcessTree("activity", activity=rng.choice(alphabet))
        if alphabet
        else ProcessTree("tau")
    )
    if action == 0:
        replacement = atom
    elif action == 1:
        replacement = _join(rng.choice(("sequence", "xor", "parallel")), (node, atom))
    elif action == 2:
        replacement = rng.choice(node.children) if node.children else ProcessTree("tau")
    elif action == 3:
        replacement = (
            _join(rng.choice(("sequence", "xor", "parallel")), node.children)
            if node.children
            else atom
        )
    elif action == 4:
        children = list(node.children)
        rng.shuffle(children)
        replacement = _join(node.operator, tuple(children)) if children else node
    elif action == 5:
        replacement = _word_tree(rng.choice(words))
    else:
        replacement = _factor(node)
    return _replace(tree, path, replacement)


def discover_genetic(
    log: CaseLog | ComputationResult[TraceSet],
    spec: GeneticMinerSpec = GeneticMinerSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[GeneticDiscovery]:
    """Run tournament selection, elitism, subtree crossover and seven mutations.

    Multiplicity affects acceptance; precision counts distinct complete words.
    The default seeds include the observed-word XOR if it fits the bounds, so
    search can improve compactness without inventing a training-fit guarantee.
    No timestamps are required; the selected case projection defines ordering.
    """
    if not isinstance(spec, GeneticMinerSpec):
        raise TypeError("spec must be GeneticMinerSpec")
    parent = as_case_traces(log, trace_spec)
    parents = (parent.computation_id,) if parent.computation_id else ()

    def finish(status, payload=None, issues=()):
        return _derived_result(
            "pix.case_centric.discover_genetic",
            parent.source_digest,
            spec,
            status,
            payload,
            parent.issues + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent.value is None:
        return finish(parent.status)
    observed = Counter(
        tuple(e.activity for e in trace.events) for trace in parent.value.traces
    )
    if not observed:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue("empty_log", "Genetic discovery needs at least one case"),
            ),
        )
    if any(not isinstance(a, str) or not a.strip() for word in observed for a in word):
        return finish(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue("invalid_activity", "Activities must be nonblank text"),
            ),
        )
    words = tuple(sorted(observed))
    alphabet = tuple(sorted({a for word in words for a in word}))
    rng = Random(spec.seed)
    total = sum(observed.values())
    weight_sum = spec.acceptance_weight + spec.precision_weight + spec.simplicity_weight
    weights = tuple(
        w / weight_sum
        for w in (
            spec.acceptance_weight,
            spec.precision_weight,
            spec.simplicity_weight,
        )
    )
    cache = {}
    evaluated = rejected = crossover_changes = mutation_changes = 0

    def evaluate(tree):
        nonlocal evaluated, rejected
        # Check shape before recursive hashing, including externally supplied seeds.
        try:
            nodes = _shape(tree, spec)
        except _CandidateLimit:
            if evaluated >= spec.max_evaluations:
                raise _EvaluationLimit
            evaluated += 1
            rejected += 1
            return None
        if tree in cache:
            return cache[tree]
        if evaluated >= spec.max_evaluations:
            raise _EvaluationLimit
        evaluated += 1
        try:
            language = _language(tree, spec)
        except _CandidateLimit:
            rejected += 1
            cache[tree] = None
            return None
        accepted = sum(n for word, n in observed.items() if word in language)
        variants = len(set(observed) & language)
        acceptance = accepted / total
        precision = variants / len(language)
        simplicity = 1 / nodes
        score = (
            weights[0] * acceptance + weights[1] * precision + weights[2] * simplicity
        )
        objective = GeneticObjective(
            score,
            acceptance,
            precision,
            simplicity,
            accepted,
            total,
            variants,
            len(language),
            nodes,
        )
        # Keep scalar scores rather than every candidate's enumerated language.
        # The incumbent's language is reproduced once for its final witness.
        candidate = (tree, objective)
        cache[tree] = candidate
        return candidate

    def ranking(candidate):
        return (-candidate[1].score, candidate[1].node_count, _key(candidate[0]))

    if spec.initial_population:
        seeds = spec.initial_population
    else:
        traces = tuple(_word_tree(word) for word in words)
        seeds = (
            _join("xor", traces),
            *traces,
            *(ProcessTree("activity", activity=a) for a in alphabet),
            ProcessTree("tau"),
        )
    population = []
    stop = "generation_limit"
    try:
        for tree in seeds:
            candidate = evaluate(tree)
            if candidate is not None:
                population.append(candidate)
            if len(population) == spec.population_size:
                break
    except _EvaluationLimit:
        stop = "evaluation_limit"
    if not population:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "no_admissible_population",
                    "No seed could be scored completely within the configured candidate/evaluation limits",
                ),
            ),
        )
    seed_population = tuple(population)
    while len(population) < spec.population_size:
        population.append(seed_population[len(population) % len(seed_population)])
    population.sort(key=ranking)
    history = []

    def record(generation):
        history.append(
            GeneticGeneration(
                generation,
                population[0][1].score,
                sum(c[1].score for c in population) / len(population),
                len({c[0] for c in population}),
                evaluated,
                rejected,
                crossover_changes,
                mutation_changes,
            )
        )

    record(0)
    stagnant = 0
    if stop != "evaluation_limit":
        for generation in range(1, spec.generations + 1):
            before = population[0][1].score
            children = population[: spec.elite_count]
            try:
                while len(children) < spec.population_size:
                    selected = min(
                        rng.sample(population, spec.tournament_size), key=ranking
                    )
                    tree = selected[0]
                    if rng.random() < spec.crossover_rate:
                        other = min(
                            rng.sample(population, spec.tournament_size), key=ranking
                        )[0]
                        path, _ = rng.choice(tuple(_paths(tree)))
                        _, subtree = rng.choice(tuple(_paths(other)))
                        crossed = _replace(tree, path, subtree)
                        crossover_changes += crossed != tree
                        tree = crossed
                    if rng.random() < spec.mutation_rate:
                        # Reject oversized crossover before recursive mutation traversal.
                        try:
                            _shape(tree, spec)
                        except _CandidateLimit:
                            pass
                        else:
                            mutated = _mutate(tree, rng, alphabet, words)
                            mutation_changes += mutated != tree
                            tree = mutated
                    candidate = evaluate(tree)
                    children.append(candidate if candidate is not None else selected)
            except _EvaluationLimit:
                stop = "evaluation_limit"
                children.extend(population[: spec.population_size - len(children)])
            population = sorted(children, key=ranking)
            record(generation)
            if stop == "evaluation_limit":
                break
            stagnant = stagnant + 1 if population[0][1].score <= before else 0
            if stagnant >= spec.stagnation_generations:
                stop = "stagnation"
                break
    champion, objective = population[0]
    language = _language(champion, spec)
    payload = GeneticDiscovery(
        champion,
        objective,
        tuple(sorted(language)),
        tuple(word for word in words if word not in language),
        tuple(history),
        stop,
        evaluated,
        rejected,
        crossover_changes,
        mutation_changes,
    )
    issues = [
        ComputeIssue(
            "heuristic_optimality_not_proven",
            "Evolutionary search does not certify a global optimum or generalization beyond the observed cases",
        )
    ]
    if stop == "evaluation_limit":
        issues.append(
            ComputeIssue(
                "genetic_evaluation_limit",
                "The evaluation budget ended search; the incumbent is retained with its exact finite-language score",
            )
        )
    status = (
        ComputeStatus.PARTIAL
        if stop == "evaluation_limit" or parent.status is ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED
    )
    return finish(status, payload, issues)


RESULT_SCHEMAS = {
    "pix.case_centric.discover_genetic": (
        "genetic-discovery",
        GeneticMinerSpec,
        GeneticDiscovery,
    ),
}

__all__ = (
    "GeneticMinerSpec",
    "GeneticObjective",
    "GeneticGeneration",
    "GeneticDiscovery",
    "discover_genetic",
)
