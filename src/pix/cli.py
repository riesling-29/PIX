"""Local-input CLI: acquisition belongs to Agents, computation belongs to PIX."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from pix import __version__
from pix._publication import publish_bytes
from pix.case_centric.context_ngrams import (
    ContextNGramSpec,
    fit_context_ngrams,
    transform_context_ngrams,
)
from pix.case_centric.discovery import discover_dfg
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseImportResult, CaseLog, write_xes
from pix.io import import_log
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.results import result_document, write_result
from pix.tabular import CaseTableMapping


def _parser():
    parser = argparse.ArgumentParser(prog="pix", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "dfg", "ngrams", "export-xes"):
        command = commands.add_parser(name)
        command.add_argument("input", help="local file supplied by the user or Agent")
        command.add_argument("--input-format")
        command.add_argument("--case-column")
        command.add_argument("--activity-column")
        command.add_argument("--timestamp-column")
        command.add_argument(
            "--receipt-output",
            help="save import/projection evidence separately from the result",
        )
        command.add_argument(
            "--reject-timezone-assumptions",
            action="store_true",
            help="reject disclosed OCEL UTC assumptions (does not certify acquisition quality)",
        )
        if name != "inspect":
            command.add_argument(
                "--object-type", help="explicit OCEL object-to-case projection"
            )
            command.add_argument(
                "--tie-policy", choices=("reject", "event_id"), default="reject"
            )
            command.add_argument("--output", required=name == "export-xes")
            command.add_argument("--overwrite", action="store_true")
        if name == "ngrams":
            command.add_argument(
                "--encoding", choices=("count", "binary", "tfidf"), default="count"
            )
            command.add_argument("--n-min", type=int, default=1)
            command.add_argument("--n-max", type=int, default=3)
            command.add_argument("--token-attribute", action="append", default=[])
            command.add_argument(
                "--missing", choices=("reject", "tag"), default="reject"
            )
            command.add_argument("--max-evidence", type=int, default=10_000)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if "://" in args.input:
            raise ValueError(
                "PIX accepts local input; an Agent must acquire remote data"
            )
        mapping = None
        if any((args.case_column, args.activity_column, args.timestamp_column)):
            if not args.case_column or not args.activity_column:
                raise ValueError(
                    "table mapping requires both --case-column and --activity-column"
                )
            mapping = CaseTableMapping(
                args.case_column, args.activity_column, args.timestamp_column
            )
        imported = import_log(args.input, format=args.input_format, mapping=mapping)
        evidence = {
            "import": imported.describe(),
            "mapping": asdict(mapping) if mapping else None,
            "admission": {
                "rejectTimezoneAssumptions": args.reject_timezone_assumptions
            },
            "projection": None,
        }
        if args.receipt_output:
            destination = Path(args.receipt_output).resolve()
            protected = [Path(args.input).resolve()]
            if getattr(args, "output", None):
                protected.append(Path(args.output).resolve())
            if destination in protected:
                raise ValueError("receipt output must differ from input and result")

        def save_evidence():
            if args.receipt_output:
                destination = Path(args.receipt_output).resolve()
                protected = [Path(args.input).resolve()]
                if getattr(args, "output", None):
                    protected.append(Path(args.output).resolve())
                if destination in protected:
                    raise ValueError("receipt output must differ from input and result")
                publish_bytes(
                    json.dumps(evidence, ensure_ascii=True, allow_nan=False).encode(),
                    destination,
                    overwrite=getattr(args, "overwrite", False),
                )

        if args.command == "inspect" or not imported.valid:
            save_evidence()
            print(json.dumps(imported.describe(), ensure_ascii=True, allow_nan=False))
            return 0 if imported.valid else 2
        try:
            log = (
                imported.require_case_log()
                if isinstance(imported, CaseImportResult)
                else imported.require_ocel(
                    reject_timezone_assumptions=args.reject_timezone_assumptions
                )
            )
        except ValueError:
            evidence["admission"]["accepted"] = False
            save_evidence()
            raise
        evidence["admission"]["accepted"] = True
        if not isinstance(log, CaseLog):
            if not args.object_type:
                raise ValueError(
                    "OCEL requires explicit --object-type for case calculations"
                )
            projection = project_object_cases(
                log, ObjectCaseProjectionSpec(args.object_type, args.tie_policy)
            )
            evidence["projection"] = projection.describe()
            log = projection.case_log
        elif args.object_type is not None:
            raise ValueError("--object-type applies only to OCEL input")
        if args.command == "export-xes":
            receipt = write_xes(log, args.output, overwrite=args.overwrite)
            evidence["export"] = json.loads(json.dumps(asdict(receipt), default=str))
            save_evidence()
            print(json.dumps(asdict(receipt), ensure_ascii=True, default=str))
            return 0
        if args.command == "dfg":
            result = discover_dfg(log)
        else:
            spec = ContextNGramSpec(
                encoding=args.encoding,
                ngram_min=args.n_min,
                ngram_max=args.n_max,
                token_attributes=tuple(args.token_attribute),
                missing=args.missing,
                max_evidence=args.max_evidence,
            )
            fitted = fit_context_ngrams(log, spec)
            result = (
                transform_context_ngrams(log, fitted.value)
                if fitted.value is not None
                else fitted
            )
        if args.output:
            write_result(result, args.output, overwrite=args.overwrite)
        evidence["result"] = {"document": result_document(result), "path": args.output}
        save_evidence()
        print(json.dumps(result_document(result), ensure_ascii=True, allow_nan=False))
        return {
            ComputeStatus.COMPUTED: 0,
            ComputeStatus.PARTIAL: 3,
            ComputeStatus.INVALID_INPUT: 2,
            ComputeStatus.UNAVAILABLE: 4,
        }[result.status]
    except (OSError, ValueError, TypeError) as error:
        print(
            json.dumps({"status": "error", "message": str(error)}, ensure_ascii=True),
            file=sys.stderr,
        )
        return 2


__all__ = ["main"]
