"""Versioned persistence for native analytical results, separate from OCEL.

Only explicitly registered PIX contracts can be loaded. Neither Python object
deserialization nor runtime plugin imports are accepted from a document. The
document digest detects corruption; it is not a signature or proof of correctness.
"""

from __future__ import annotations

import json
import math
import os
import types
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Literal, Union, get_args, get_origin, get_type_hints

from pix._publication import FilePublication, publish_bytes
from pix.contracts import (
    analysis,
    case_log,
    conformance,
    constraint,
    discovery,
    execution,
    models,
    object_conformance,
    object_context,
    ocpn_discovery,
    precision,
    replay,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

RESULT_FORMAT = "pix.analysis-result"
RESULT_VERSION = "1.2.0"
_READABLE_VERSIONS = ("1.0.0", "1.1.0", RESULT_VERSION)
_INTEGER_TAG = "$pix.integer.hex"


def _schemas() -> dict[str, tuple[str, type, type]]:
    # Import only known modules in code, never module names from persisted data.
    schemas = {
        "pix.case_traces": (
            "case-traces",
            case_log.CaseTraceSpec,
            analysis.TraceSet,
        ),
        "pix.reconstruct_traces": (
            "object-traces",
            analysis.TraceSpec,
            analysis.TraceSet,
        ),
        "pix.discover_dfg": (
            "object-dfg",
            analysis.TraceSpec,
            analysis.DirectlyFollowsGraph,
        ),
        "pix.discover_ocdfg": ("ocdfg", analysis.OCDFGSpec, analysis.ObjectCentricDFG),
        "pix.measure_temporal": (
            "observed-temporal",
            analysis.TemporalSpec,
            analysis.ObservedTemporal,
        ),
        "pix.discover_executions": (
            "executions",
            execution.ExecutionSpec,
            execution.ExecutionSet,
        ),
        "pix.discover_variants": (
            "incidence-variants",
            execution.VariantSpec,
            execution.VariantSet,
        ),
        "pix.discover_process_tree": (
            "process-tree",
            discovery.DiscoverySpec,
            discovery.ProcessTree,
        ),
        "pix.align_traces": (
            "trace-alignments",
            conformance.AlignmentRequest,
            conformance.AlignmentSet,
        ),
        "pix.replay_traces": ("token-replay", replay.ReplayRequest, replay.ReplaySet),
        "pix.discover_ocpn": (
            "ocpn-discovery",
            ocpn_discovery.OCPNDiscoverySpec,
            models.OCPNDiscoveryPayload,
        ),
        "pix.prefix_precision": (
            "prefix-precision",
            precision.PrefixPrecisionRequest,
            precision.PrefixPrecision,
        ),
        "pix.measure_object_context": (
            "object-context-metrics",
            object_context.ObjectContextRequest,
            object_context.ObjectContextMetrics,
        ),
        "pix.align_object_log": (
            "object-alignments",
            object_conformance.ObjectAlignmentRequest,
            object_conformance.ObjectAlignment,
        ),
        "pix.evaluate_constraints": (
            "constraint-evaluation",
            constraint.ConstraintSpec,
            constraint.ConstraintEvaluation,
        ),
    }
    from pix._mining_registry import mining_schemas

    for operator, schema in mining_schemas().items():
        if operator in schemas:
            raise RuntimeError(f"duplicate analytical result operator: {operator}")
        schemas[operator] = schema
    return schemas


def _encode(value: object, depth: int = 0, *, large_integers: bool = False) -> object:
    if depth > 128:
        raise ValueError("analytical result exceeds the nesting limit")
    if isinstance(value, Enum):
        return _encode(value.value, depth + 1, large_integers=large_integers)
    if type(value) is int and large_integers and value.bit_length() > 4096:
        return {_INTEGER_TAG: hex(value)}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite result values are not supported")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("result timestamps must be timezone-aware")
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, tuple):
        return [
            _encode(item, depth + 1, large_integers=large_integers) for item in value
        ]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _encode(
                getattr(value, field.name), depth + 1, large_integers=large_integers
            )
            for field in fields(value)
        }
    raise TypeError(f"unsupported analytical value: {type(value).__name__}")


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "pix.analysis-result.v1:sha256:" + sha256(_json_bytes(value)).hexdigest()


def _check_identity(result: ComputationResult) -> None:
    from pix.contracts.result import computation_identity

    expected = computation_identity(
        result.operator_id,
        result.operator_version,
        result.source_digest,
        result.spec,
        result.parent_computation_ids,
    )
    if expected != result.computation_id:
        raise ValueError("computation identity does not match its request")


def _check_envelope(result: ComputationResult) -> None:
    """Check request/payload facts and registered structural certificates."""
    from pix.case_centric.maximal_decomposition import (
        RESULT_SCHEMAS as decomposition_schemas,
    )
    from pix.case_centric.maximal_decomposition import (
        validate_maximal_decomposition_result,
    )
    from pix.object_centric.learning import RESULT_SCHEMAS, validate_learning_result

    if result.operator_id in decomposition_schemas:
        validate_maximal_decomposition_result(result)
    if result.operator_id in RESULT_SCHEMAS:
        validate_learning_result(result)
    if result.operator_id == "pix.object_centric.assess_operational_impact":
        from pix.object_centric.operational_impact import (
            validate_operational_impact_result,
        )

        validate_operational_impact_result(result)
    if result.operator_id in (
        "pix.object_centric.local_ocpn_subprocess",
        "pix.object_centric.transform_ocpn_subprocess",
    ):
        from pix.object_centric.subprocess import validate_subprocess_result

        validate_subprocess_result(result)
    if result.operator_id == "pix.case_centric.discover_interleavings":
        from pix.case_centric.interleavings import validate_interleaving_result

        validate_interleaving_result(result)
    if result.operator_id == "pix.case_centric.retrieve_embedding_neighbors":
        from pix.case_centric.embedding_retrieval import (
            validate_embedding_retrieval_result,
        )

        validate_embedding_retrieval_result(result)
    value, spec = result.value, result.spec
    if value is None:
        return
    if isinstance(value, analysis.TraceSet):
        if value.object_type != spec.object_type:
            raise ValueError("trace payload and selected type disagree")
        for trace in value.traces:
            if trace.object_type != value.object_type:
                raise ValueError("trace member type differs from its trace set")
            if result.operator_id != "pix.case_traces" and any(
                event.time is None for event in trace.events
            ):
                raise ValueError("OCEL trace events require observed timestamps")
    if hasattr(spec, "model_digest") and hasattr(value, "model_digest"):
        if spec.model_digest != value.model_digest:
            raise ValueError("request and payload model digests disagree")
    if hasattr(value, "source_trace_computation_id"):
        if result.parent_computation_ids != (value.source_trace_computation_id,):
            raise ValueError("payload trace reference disagrees with parent identity")
    expected_status = None
    if isinstance(value, precision.PrefixPrecision):
        parameters = spec.parameters
        if (parameters.terminal_policy, parameters.weighting) != (
            value.terminal_policy,
            value.weighting,
        ):
            raise ValueError("precision request and payload policies disagree")
        if any(
            row.explored_markings_count > parameters.max_markings_per_prefix
            for row in value.prefixes
        ):
            raise ValueError("precision evidence exceeds its requested search bound")
        incomplete = (
            value.coverage.unfit_prefixes or value.coverage.search_limited_prefixes
        )
        expected_status = (
            ComputeStatus.PARTIAL if incomplete else ComputeStatus.COMPUTED
        )
    elif isinstance(value, object_context.ObjectContextMetrics):
        incomplete = (
            not value.coverage.log_enumeration_complete
            or value.coverage.incomplete_contexts > 0
        )
        expected_status = (
            ComputeStatus.PARTIAL if incomplete else ComputeStatus.COMPUTED
        )
        if any(
            kind not in spec.parameters.object_types
            for _, kind in value.selected_objects
        ):
            raise ValueError(
                "object-context payload contains an unselected object type"
            )
    elif isinstance(value, object_conformance.ObjectAlignment):
        expected_status = (
            ComputeStatus.COMPUTED
            if value.status in ("optimal", "unreachable")
            else ComputeStatus.PARTIAL
        )
        if value.cost_unit != spec.parameters.cost_mode + "_weighted_integer_cost":
            raise ValueError("joint alignment request and cost unit disagree")
        if value.scope.scope != spec.parameters.scope:
            raise ValueError("joint alignment request and event scope disagree")
    elif isinstance(value, constraint.ConstraintEvaluation):
        if value.observation_policy != spec.observation_policy:
            raise ValueError("constraint request and observation policy disagree")
        if tuple((row.rule_id, row.kind) for row in value.rules) != tuple(
            (rule.rule_id, rule.kind) for rule in spec.rules
        ):
            raise ValueError("constraint results disagree with the requested rules")
        expected_status = (
            ComputeStatus.PARTIAL
            if any(row.pending_count for row in value.rules)
            else ComputeStatus.COMPUTED
        )
    elif isinstance(value, models.OCPNDiscoveryPayload):
        if tuple(item.object_type for item in value.projections) != spec.object_types:
            raise ValueError("OCPN projections disagree with the selected object types")
        parents = tuple(
            identity
            for projection in value.projections
            for identity in (
                projection.trace_computation_id,
                projection.discovery_computation_id,
            )
        )
        if result.parent_computation_ids != parents:
            raise ValueError(
                "OCPN projection references disagree with parent identities"
            )
        expected_status = ComputeStatus.COMPUTED
    if expected_status is not None and result.status is not expected_status:
        raise ValueError("computation status disagrees with payload coverage")


def result_document(result: ComputationResult) -> dict[str, object]:
    """Return a JSON-compatible document with explicit payload and schema version."""
    if not isinstance(result, ComputationResult):
        raise TypeError("result must be ComputationResult")
    try:
        kind, spec_type, payload_type = _schemas()[result.operator_id]
    except KeyError as exc:
        raise ValueError("unsupported operator result schema") from exc
    if type(result.spec) is not spec_type:
        raise TypeError("result specification does not match its operator")
    if result.value is not None and type(result.value) is not payload_type:
        raise TypeError("result payload does not match its operator")
    if result.operator_version != "1.0.0":
        raise ValueError("unsupported operator result version")
    _decode(_encode(result.spec, large_integers=True), spec_type, large_integers=True)
    if result.value is not None:
        _decode(
            _encode(result.value, large_integers=True),
            payload_type,
            large_integers=True,
        )
    _check_identity(result)
    _check_envelope(result)
    body = {
        "format": RESULT_FORMAT,
        "version": RESULT_VERSION,
        "payload_kind": kind,
        "computation": _encode(result, large_integers=True),
    }
    return {**body, "document_digest": _digest(body)}


def result_json_bytes(result: ComputationResult) -> bytes:
    return _json_bytes(result_document(result))


def _members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate result member: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _decode(
    value: object, expected: object, depth: int = 0, *, large_integers: bool = False
) -> object:
    if depth > 128:
        raise ValueError("analytical result exceeds the nesting limit")
    origin, args = get_origin(expected), get_args(expected)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _decode(value, option, depth + 1, large_integers=large_integers)
            except (TypeError, ValueError):
                pass
        raise ValueError("result value does not match its union type")
    if expected is type(None):
        if value is not None:
            raise ValueError("expected null")
        return None
    if origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            raise ValueError("result contains an unsupported literal")
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("expected a JSON array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(
                _decode(item, args[0], depth + 1, large_integers=large_integers)
                for item in value
            )
        if len(value) != len(args):
            raise ValueError("result tuple has the wrong length")
        return tuple(
            _decode(item, kind, depth + 1, large_integers=large_integers)
            for item, kind in zip(value, args)
        )
    if expected in (str, bool, int, float):
        if expected is int and large_integers and isinstance(value, dict):
            if set(value) != {_INTEGER_TAG} or not isinstance(value[_INTEGER_TAG], str):
                raise ValueError("invalid exact integer encoding")
            text = value[_INTEGER_TAG]
            try:
                integer = int(text, 16)
            except ValueError as exc:
                raise ValueError("invalid hexadecimal integer") from exc
            if integer.bit_length() <= 4096 or hex(integer) != text:
                raise ValueError("noncanonical hexadecimal integer")
            return integer
        if type(value) is not expected:
            raise ValueError(f"expected {expected.__name__}")
        if expected is float and not math.isfinite(value):
            raise ValueError("expected a finite float")
        return value
    if expected is datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("expected a UTC result timestamp")
        result = datetime.fromisoformat(value[:-1] + "+00:00")
        if _encode(result) != value:
            raise ValueError("result timestamp must have microsecond precision")
        return result
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    if isinstance(expected, type) and is_dataclass(expected):
        if not isinstance(value, dict):
            raise ValueError("expected a result record")
        names = {field.name for field in fields(expected)}
        if set(value) != names:
            raise ValueError(f"unexpected or missing fields in {expected.__name__}")
        hints = get_type_hints(expected)
        # XES values have an explicit type discriminator. An ISO-looking string
        # must remain a string; a declared date must decode as datetime even
        # though the general CaseValue union lists str first.
        from pix.event_log.model import CaseAttribute

        if expected is CaseAttribute:
            attribute_types = {
                "string": str,
                "id": str,
                "date": datetime,
                "int": int,
                "float": float,
                "boolean": bool,
                "list": type(None),
                "container": type(None),
                "null": type(None),
            }
            if type(value["type"]) is not str or value["type"] not in attribute_types:
                raise ValueError("unsupported case attribute type")
            hints["value"] = attribute_types[value["type"]]
        return expected(
            **{
                name: _decode(
                    value[name], hints[name], depth + 1, large_integers=large_integers
                )
                for name in names
            }
        )
    raise TypeError(f"unregistered result field type: {expected!r}")


def result_from_json(data: str | bytes) -> ComputationResult:
    """Load a registered result and verify its document and request identities."""
    if not isinstance(data, (str, bytes)):
        raise TypeError("data must be str or bytes")
    document = json.loads(
        data, object_pairs_hook=_members, parse_constant=_reject_constant
    )
    if not isinstance(document, dict) or set(document) != {
        "format",
        "version",
        "payload_kind",
        "computation",
        "document_digest",
    }:
        raise ValueError("invalid result document fields")
    if (
        document["format"] != RESULT_FORMAT
        or document["version"] not in _READABLE_VERSIONS
    ):
        raise ValueError("unsupported analytical result format or version")
    body = {key: value for key, value in document.items() if key != "document_digest"}
    if document["document_digest"] != _digest(body):
        raise ValueError("analytical result document digest mismatch")
    record = document["computation"]
    if not isinstance(record, dict) or set(record) != {
        field.name for field in fields(ComputationResult)
    }:
        raise ValueError("invalid computation envelope fields")
    try:
        kind, spec_type, payload_type = _schemas()[record["operator_id"]]
    except (KeyError, TypeError) as exc:
        raise ValueError("unsupported operator result schema") from exc
    if document["payload_kind"] != kind:
        raise ValueError("payload kind does not match its operator")
    if record["operator_id"] == "pix.case_traces" and document["version"] != "1.2.0":
        raise ValueError("case trace results require format version 1.2.0")

    def decode(value: object, expected: object) -> object:
        return _decode(value, expected, large_integers=document["version"] != "1.0.0")

    result = ComputationResult(
        operator_id=decode(record["operator_id"], str),
        operator_version=decode(record["operator_version"], str),
        source_digest=decode(record["source_digest"], str | None),
        spec=decode(record["spec"], spec_type),
        status=decode(record["status"], ComputeStatus),
        value=None
        if record["value"] is None
        else decode(record["value"], payload_type),
        issues=decode(record["issues"], tuple[ComputeIssue, ...]),
        computation_id=decode(record["computation_id"], str | None),
        parent_computation_ids=decode(
            record["parent_computation_ids"], tuple[str, ...]
        ),
    )
    if result.operator_version != "1.0.0":
        raise ValueError("unsupported operator result version")
    _check_identity(result)
    _check_envelope(result)
    return result


def read_result(path: str | os.PathLike[str]) -> ComputationResult:
    return result_from_json(Path(path).read_bytes())


def write_result(
    result: ComputationResult, path: str | os.PathLike[str], *, overwrite: bool = False
) -> FilePublication:
    """Publish a verified result atomically; never clobber an existing file by default."""
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    payload = result_json_bytes(result)
    if result_from_json(payload) != result:
        raise ValueError("analytical result does not round-trip")
    return publish_bytes(payload, path, overwrite=overwrite, prefix=".pix-result-")


__all__ = [
    "RESULT_FORMAT",
    "RESULT_VERSION",
    "read_result",
    "result_document",
    "result_from_json",
    "result_json_bytes",
    "write_result",
]
