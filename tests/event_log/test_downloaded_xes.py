"""Opt-in full-source checks for nine logs in ten XES/gzip representations.

Set PIX_RUN_XES_CORPUS=1 after organizing logs in the corpus' dataset/logs
directories under tests/fixtures/event_logs/xes. No downloads occur.
Every stored attribute is compared with an independent streaming ElementTree
read. Discovery/replay is a bounded, whole-trace sample, not full-log validation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import time
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from pix import import_log
from pix.api import (
    CaseTraceSpec,
    ComputeStatus,
    DiscoverySpec,
    ReplaySpec,
    case_traces,
    discover_process_tree,
    process_tree_to_petri_net,
    replay_traces,
    result_from_json,
    result_json_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "event_logs" / "xes"
ARTIFACTS = ROOT / ".artifacts" / "xes-corpus-2026-09-13" / "pix"
SOURCES = {
    "activitylog_uci_detailed_labour.xes.gz": "297d3f5b68601cbf6af5a1971ddb7a60a7f8186831290f9a81caa0702fc88b87",
    "activitylog_uci_detailed_weekends.xes.gz": "17a419728c5d00fd537b6b43d55ec2be3c26c644fd79f3520e27deecc29f5b46",
    "edited_hh102_labour.xes.gz": "d0feb2bfa67e7006457d1a00d3e7c3064c44c790f0e32ee006c696bc7747dd01",
    "edited_hh102_weekends.xes.gz": "a43d36f1b1779741a8e766dd773cb6475ce9c6bfc90642645ca5d052c1177a6f",
    "edited_hh104_labour.xes.gz": "284fd6477ac31f99f25037c20779f159a87ddf419a9662375f56f0d1c1340189",
    "edited_hh104_weekends.xes.gz": "9535c32aad788c96d64caa323790c2099de6be0fcd24e475aca5b3880e7db1ae",
    "edited_hh110_labour.xes.gz": "0dea82ea218631c912cebe32714a0f96e2059d28b26f1890eb5cd39af1366109",
    "edited_hh110_weekends.xes.gz": "419035d870ad16ad2cb600c7ab498b64a6a0485428d43d87e25aa6a3f650f9b8",
    "Hospital Billing - Event Log.xes.gz": "3f4bb8a09b1d3dec7deb8a8b1c2f31374fbe57fd60fe38477f1cc06989242ef6",
    "Hospital Billing - Event Log.xes": "8f8d3b25f089b23458f0e01b36f8237b49c33e1ed1b70bd23c2f220c6889569f",
}
# Independent full-source .NET XmlReader scan, 2026-09-13. Values are
# (traces, events, distinct activities, shortest trace, longest trace).
PROFILES = {
    "activitylog_uci_detailed_labour.xes.gz": (25, 1392, 16, 34, 92),
    "activitylog_uci_detailed_weekends.xes.gz": (10, 488, 15, 28, 70),
    "edited_hh102_labour.xes.gz": (18, 1152, 18, 46, 82),
    "edited_hh102_weekends.xes.gz": (7, 420, 18, 46, 76),
    "edited_hh104_labour.xes.gz": (43, 4200, 19, 58, 134),
    "edited_hh104_weekends.xes.gz": (18, 1728, 19, 56, 124),
    "edited_hh110_labour.xes.gz": (21, 1390, 17, 20, 90),
    "edited_hh110_weekends.xes.gz": (6, 368, 14, 54, 66),
    "Hospital Billing - Event Log.xes.gz": (100000, 451359, 18, 1, 217),
    "Hospital Billing - Event Log.xes": (100000, 451359, 18, 1, 217),
}
CLASSIFIERS = {
    "activitylog_uci_detailed_labour.xes.gz": ("Activity", "Column_4"),
    "activitylog_uci_detailed_weekends.xes.gz": ("Activity", "watchingtv"),
    "edited_hh102_labour.xes.gz": ("Activity", "Column_4"),
    "edited_hh102_weekends.xes.gz": ("Activity", "Column_4"),
    "edited_hh104_labour.xes.gz": ("Activity", "work"),
    "edited_hh104_weekends.xes.gz": ("Activity", "Column_4"),
    "edited_hh110_labour.xes.gz": ("Activity", "Column_4"),
    "edited_hh110_weekends.xes.gz": ("Activity", "Column_4"),
    "Hospital Billing - Event Log.xes.gz": ("concept:name", "concept:name"),
    "Hospital Billing - Event Log.xes": ("concept:name", "concept:name"),
}


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _classifier_keys(text):
    """Independent tokenization of the corpus' whitespace/quoted key grammar."""
    keys = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] in {"'", '"'}:
            end = text.find(text[index], index + 1)
            assert end >= 0, "Unterminated classifier key"
            keys.append(text[index + 1 : end])
            index = end + 1
            assert index == len(text) or text[index].isspace()
        else:
            start = index
            while index < len(text) and not text[index].isspace():
                assert text[index] not in {"'", '"'}
                index += 1
            keys.append(text[start:index])
    return tuple(keys)


def _attributes(raw, stored):
    assert len(raw) == len(stored), "Attribute count changed"
    for element, attribute in zip(raw, stored):
        kind = _tag(element)
        assert attribute.type == kind
        assert attribute.key == element.attrib["key"]
        lexical = element.get("value")
        assert attribute.lexical == lexical, "Original lexical value changed"
        if kind in {"string", "id"}:
            assert attribute.value == lexical
        elif kind == "int":
            assert type(attribute.value) is int and attribute.value == int(lexical)
        elif kind == "float":
            expected = float(lexical)
            assert type(attribute.value) is float
            assert (math.isnan(expected) and math.isnan(attribute.value)) or (
                expected == attribute.value
            )
            if expected == 0:
                assert math.copysign(1, expected) == math.copysign(1, attribute.value)
        elif kind == "boolean":
            assert attribute.value is (lexical in {"true", "1"})
        elif kind == "date":
            text = lexical[:-1] + "+00:00" if lexical.endswith("Z") else lexical
            assert attribute.value == datetime.fromisoformat(text)
            assert (
                attribute.value.utcoffset() == datetime.fromisoformat(text).utcoffset()
            )
        else:
            assert kind in {"list", "container"} and attribute.value is None
        children = list(element)
        if kind == "list":
            assert _tag(children[-1]) == "values"
            _attributes(list(children.pop()), attribute.values)
        else:
            assert not attribute.values
        _attributes(children, attribute.children)


def _compare_source(path, log):
    """Compare each source record before releasing its XML element."""
    stack = []
    namespace_pairs = []
    trace_index = event_index = events = 0
    global_index = extension_index = classifier_index = 0
    log_attributes = []
    open_source = gzip.open if path.suffix == ".gz" else open
    with open_source(path, "rb") as stream:
        for action, element in ET.iterparse(
            stream, events=("start", "end", "start-ns")
        ):
            if action == "start-ns":
                namespace_pairs.append(element)
                continue
            tag = _tag(element)
            if action == "start":
                if not stack:
                    expected = dict(element.attrib)
                    expected.update(
                        {
                            "xmlns" + (":" + p if p else ""): u
                            for p, u in namespace_pairs
                        }
                    )
                    assert dict(log.metadata) == expected
                stack.append(element)
                continue
            parent = _tag(stack[-2]) if len(stack) > 1 else None
            if tag == "event" and parent == "trace":
                stored = log.traces[trace_index].events[event_index]
                assert stored.id == f"event:{trace_index}:{event_index}"
                _attributes(list(element), stored.attributes)
                event_index += 1
                events += 1
                stack[-2].remove(element)
                element.clear()
            elif tag == "trace" and parent == "log":
                stored = log.traces[trace_index]
                assert stored.id == f"trace:{trace_index}"
                assert len(stored.events) == event_index
                _attributes(list(element), stored.attributes)
                trace_index += 1
                event_index = 0
                stack[-2].remove(element)
                element.clear()
            elif parent == "log":
                if tag == "global":
                    stored = log.globals[global_index]
                    assert stored.scope == element.attrib["scope"]
                    _attributes(list(element), stored.attributes)
                    global_index += 1
                elif tag == "extension":
                    assert asdict(log.extensions[extension_index]) == element.attrib
                    extension_index += 1
                elif tag == "classifier":
                    stored = log.classifiers[classifier_index]
                    assert stored.name == element.attrib["name"]
                    assert stored.scope == element.get("scope", "event")
                    assert stored.lexical == element.attrib["keys"]
                    assert stored.keys == _classifier_keys(element.attrib["keys"])
                    classifier_index += 1
                else:
                    log_attributes.append(element)
                stack[-2].remove(element)
            stack.pop()
    _attributes(log_attributes, log.attributes)
    assert trace_index == len(log.traces)
    assert events == sum(len(t.events) for t in log.traces)
    assert global_index == len(log.globals)
    assert extension_index == len(log.extensions)
    assert classifier_index == len(log.classifiers)
    return {
        "traces": trace_index,
        "events": events,
        "all_recorded_attributes": "equal",
        "metadata": "equal",
    }


def _sample(log, max_traces=32, max_events=4096):
    count = len(log.traces)
    indices = sorted(
        {
            i * (count - 1) // max(1, min(count, max_traces) - 1)
            for i in range(min(count, max_traces))
        }
    )
    selected = []
    event_count = 0
    for index in indices:
        size = len(log.traces[index].events)
        if event_count + size <= max_events:
            selected.append(index)
            event_count += size
    # Never truncate a trace or represent the sample as the full source.
    return replace(log, traces=tuple(log.traces[i] for i in selected)), selected


def _recorded(event, key, kind):
    """These supplied logs record each requested value on every event."""
    values = [a for a in event.attributes if a.key == key]
    assert len(values) == 1, f"Expected one recorded {key!r} on {event.id}"
    assert values[0].type == kind
    return values[0].value


def _compare_projection(log, result, *, classifier_key=None):
    """Check source order and facts in the bounded analysis sample.

    The full CaseLog has already been independently compared with the XML.
    Corpus classifiers have one string key. This explicit expectation does not
    implement general classifier semantics or assume it equals concept:name.
    """
    assert result.status is ComputeStatus.COMPUTED, result.issues
    assert result.value is not None
    assert result.value.object_type == "case"
    assert len(result.value.traces) == len(log.traces)
    for original, projected in zip(log.traces, result.value.traces):
        assert projected.object_id == original.id
        assert projected.object_type == "case"
        assert len(projected.events) == len(original.events)
        for event, actual in zip(original.events, projected.events):
            assert actual.event_id == event.id
            activity = _recorded(event, "concept:name", "string")
            assert activity.strip(), "The corpus has no missing/blank activities"
            if classifier_key is None:
                assert actual.activity == activity
            else:
                value = _recorded(event, classifier_key, "string")
                assert json.loads(actual.activity) == [["string", value]]
            timestamp = _recorded(event, "time:timestamp", "date")
            assert timestamp.utcoffset() is not None
            assert actual.time == timestamp
            assert actual.time.utcoffset() == timestamp.utcoffset()
            assert len(actual.relations) == 1
            relation = actual.relations[0]
            assert (relation.event, relation.object, relation.qualifier) == (
                event.id,
                original.id,
                "case",
            )


@pytest.mark.skipif(
    os.environ.get("PIX_RUN_XES_CORPUS") != "1",
    reason="Set PIX_RUN_XES_CORPUS=1 for local downloaded logs",
)
@pytest.mark.parametrize("name,expected_hash", sorted(SOURCES.items()))
def test_downloaded_xes_preservation_and_analysis(name, expected_hash):
    report = {
        "source_name": name,
        "sha256": expected_hash,
        "status": "failed",
        "stage": "source",
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    try:
        matches = sorted(
            (p for p in FIXTURES.rglob(name) if p.parent.name == "logs"), key=str
        )
        assert matches, f"Unpack the supplied ZIP containers: missing {name}"
        assert all(_sha(p) == expected_hash for p in matches), "Corpus bytes changed"
        path = matches[0]
        report.update(source=str(path), identical_copies=len(matches), stage="import")
        started = time.perf_counter()
        result = import_log(path)
        report["import_seconds"] = time.perf_counter() - started
        report["import"] = result.describe()
        assert result.valid, result.describe()
        assert result.source_sha256 == expected_hash
        log = result.require_case_log()
        report["stage"] = "full_source_comparison"
        report["preservation"] = _compare_source(path, log)
        assert _sha(path) == expected_hash, "Source changed during verification"
        activities = Counter(e.activity for t in log.traces for e in t.events)
        lengths = [len(t.events) for t in log.traces]
        report["profile"] = {
            "traces": len(log.traces),
            "events": sum(lengths),
            "activity_count": len(activities),
            "empty_traces": lengths.count(0),
            "shortest_trace": min(lengths, default=0),
            "longest_trace": max(lengths, default=0),
        }
        assert (
            len(log.traces),
            sum(lengths),
            len(activities),
            min(lengths),
            max(lengths),
        ) == PROFILES[name]
        assert None not in activities and all(a.strip() for a in activities)
        sample, indices = _sample(log)
        report["sample"] = {
            "trace_indices": indices,
            "trace_count": len(indices),
            "event_count": sum(len(t.events) for t in sample.traces),
            "whole_trace_limit": 32,
            "event_budget": 4096,
            "scope": "sample only; no full-log analysis claim",
        }
        assert sample.traces, "No complete trace fits the documented analysis sample"
        report["stage"] = "sample_case_traces"
        traces = case_traces(sample)
        _compare_projection(sample, traces)
        assert result_from_json(result_json_bytes(traces)) == traces
        report["default_projection"] = {
            "status": traces.status.value,
            "source_order_ids_activities_timestamps_relations": "equal",
        }
        report["declared_event_classifiers"] = []
        expected_classifier_name, expected_classifier_key = CLASSIFIERS[name]
        assert len(sample.classifiers) == 1
        for classifier in sample.classifiers:
            assert classifier.scope == "event"
            assert classifier.name == expected_classifier_name
            classified = case_traces(sample, CaseTraceSpec(classifier=classifier.name))
            report["declared_event_classifiers"].append(
                {
                    "name": classifier.name,
                    "keys": classifier.keys,
                    "status": classified.status.value,
                    "issues": [asdict(i) for i in classified.issues],
                }
            )
            assert classifier.keys == (expected_classifier_key,)
            _compare_projection(
                sample, classified, classifier_key=expected_classifier_key
            )
            report["declared_event_classifiers"][-1][
                "source_order_ids_typed_values_timestamps_relations"
            ] = "equal"
            assert result_from_json(result_json_bytes(classified)) == classified
        assert report["declared_event_classifiers"], "Expected a declared classifier"
        report["stage"] = "sample_discovery"
        tree = discover_process_tree(
            traces, DiscoverySpec(algorithm="pix.im.v1", max_depth=64)
        )
        report["discovery"] = {
            "status": tree.status.value,
            "issues": [asdict(i) for i in tree.issues],
        }
        assert tree.status is ComputeStatus.COMPUTED, tree.issues
        report["stage"] = "sample_replay"
        replay = replay_traces(
            traces,
            process_tree_to_petri_net(tree.value),
            ReplaySpec(silent_max_states=256),
        )
        report["replay"] = {
            "status": replay.status.value,
            "issues": [asdict(i) for i in replay.issues],
        }
        assert replay.value is not None
        report["replay"].update(
            {
                "completed": replay.value.completed_count,
                "limited": replay.value.limited_count,
                "completed_counts": asdict(replay.value.completed_counts),
            }
        )
        assert result_from_json(result_json_bytes(replay)) == replay
        assert replay.status in {ComputeStatus.COMPUTED, ComputeStatus.PARTIAL}
        # Token insertion is a measured result, not silently equated to fitness.
        report["status"] = (
            "passed"
            if replay.status is ComputeStatus.COMPUTED
            else "passed_with_bounded_replay"
        )
        report["stage"] = "finished"
    finally:
        (ARTIFACTS / (name + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


@pytest.mark.skipif(
    os.environ.get("PIX_RUN_XES_CORPUS") != "1",
    reason="Set PIX_RUN_XES_CORPUS=1 for local downloaded logs",
)
def test_hospital_plain_and_gzip_have_identical_xml_bytes():
    folder = FIXTURES / "hospital_billing" / "logs"
    zipped = folder / "Hospital Billing - Event Log.xes.gz"
    plain = folder / "Hospital Billing - Event Log.xes"
    assert _sha(zipped) == SOURCES[zipped.name]
    assert _sha(plain) == SOURCES[plain.name]
    digest = hashlib.sha256()
    with gzip.open(zipped, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest() == _sha(plain)
