"""Public-contract counterexamples across supported Python minor versions."""

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext

import pytest

from pix.case_centric.statistics import NumericAttributeSpec, measure_numeric_attribute
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.event_log.reader import read_xes
from pix.ocel.ingest.formats.common import AdapterFailure
from pix.ocel.ingest.formats.compact import load
from pix.tabular import CaseTableMapping, read_table
from pix.viewer.visual_contracts import ChartPanel, ChartPoint, ChartSeries


@pytest.mark.parametrize(
    "fraction", ["1", "12", "123", "1234", "12345", "123456", "123456000"]
)
@pytest.mark.parametrize("reader", ["xes", "table"])
def test_exact_fractional_seconds_survive_supported_readers(tmp_path, fraction, reader):
    stamp = f"2026-01-02T03:04:05.{fraction}+09:00"
    expected = datetime(
        2026, 1, 1, 18, 4, 5, int(fraction[:6].ljust(6, "0")), timezone.utc
    )
    if reader == "xes":
        path = tmp_path / "fraction.xes"
        path.write_text(
            '<log><trace><event><string key="concept:name" value="A"/>'
            f'<date key="time:timestamp" value="{stamp}"/></event></trace></log>',
            encoding="utf-8",
        )
        log = read_xes(path)
        assert log.traces[0].events[0].attribute("time:timestamp").lexical == stamp
    else:
        log = read_table(
            [{"case": "c", "activity": "A", "time": stamp}],
            CaseTableMapping("case", "activity", timestamp="time"),
        )
    assert log.traces[0].events[0].timestamp == expected


@pytest.mark.parametrize("fraction", ["1", "12", "123", "1234", "12345", "123456"])
def test_chart_validates_fractional_seconds_without_rewriting_lexical_value(fraction):
    stamp = f"2026-01-02T03:04:05.{fraction}Z"
    panel = ChartPanel(
        "chart", "Time", "line", (ChartSeries("s", (ChartPoint(stamp, 1),)),), "time"
    )
    assert panel.series[0].points[0].x == stamp


@pytest.mark.parametrize(
    "stamp", ["2026-01-02T03:04:05.0000001Z", "20260102T030405.1234567+09"]
)
def test_compact_inference_keeps_precision_failure_visible(tmp_path, stamp):
    path = tmp_path / "fraction.ocel.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "activity", "timestamp", "ot:Order"])
        writer.writerow(["", "", "", "o" + json.dumps({"at": stamp})])
    with pytest.raises(AdapterFailure) as error:
        load(path)
    assert error.value.code == "timestamp_precision_loss"


@pytest.mark.parametrize(
    "samples", [(1e308, -1e308), (1e308, 0.0, -1e308), (1e308, 1e308)]
)
def test_large_population_stddev_matches_independent_decimal_oracle(samples):
    log = CaseLog(
        (
            CaseTrace(
                "c",
                tuple(
                    CaseEvent(str(i), (CaseAttribute("x", "float", sample),))
                    for i, sample in enumerate(samples)
                ),
            ),
        )
    )
    with localcontext() as context:
        # These binary64 samples have at most 309 integer digits; keep their
        # squares and the identical-value cancellation exact before sqrt.
        context.prec = 800
        values = [Decimal.from_float(value) for value in samples]
        center = sum(values) / len(values)
        expected = float((sum((v - center) ** 2 for v in values) / len(values)).sqrt())
    actual = measure_numeric_attribute(log, NumericAttributeSpec("x")).value.summary
    assert actual.population_stddev == pytest.approx(expected, rel=1e-15, abs=0)
