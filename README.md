# PIX

PIX is an independent, deterministic Process Intelligence computation and
interpretation engine.

## Status

PIX `0.4.0` provides native analysis and offline graph viewing over the immutable OCEL
foundation. It provides strict JSON/XML/SQLite import profiles, verified atomic
exports (including JSON/XML gzip), object traces, DFG/OCDFG, observed temporal
measures, explicit execution extraction, and bounded exact incidence variants.
Native model functionality includes explicit log-based IM and conservative cut
profiles, process-tree conversion, observational OCPN discovery with a checked
accepting witness, Petri net/OCPN firing and bounded binding enumeration, classical
and joint object-centric alignment, token replay, prefix precision, object-context
fitness/precision and declarative rules. Results and models have separate versioned,
evidence-bearing JSON formats. The SVG viewer bundles ELK for offline layout.

The supported miners are explicit `pix.inductive_cut.v1` and `pix.im.v1` profiles;
IMf/IMd and other algorithm families are not implied. OCPN discovery's observed-log
acceptance witness does not certify joint soundness or normative cardinalities.
Joint alignment consumes shared events once and preserves per-object partial
orders. Precision and context have named population/termination definitions,
and open observations retain pending rules. Search limits and zero denominators
are explicit. Normalized classical fitness and predictive analysis remain future work.
PM4Py and OCPA remain reference implementations and are not PIX runtime
dependencies.

## Implemented OCEL flow

```text
OCEL 2.0 JSON / XML / SQLite
        |
        v
source evidence -> format adapter -> import result
        |
        v
immutable OCEL model -> deterministic build -> semantic validation
                                               |
                                               v
                                Canonical V1 bytes -> SHA-256 digest
```

The canonical format is an internal identity representation, not an OCEL 2.0
file format. Its byte-level rules are documented in
[`docs/specifications/PIX_OCEL_CANONICAL_V1.md`](docs/specifications/PIX_OCEL_CANONICAL_V1.md).

Start with the
[OCEL reading user guide](docs/user-guide/OCEL_READING_GUIDE.md) for supported
inputs, timestamp behavior, object inspection, and failure diagnostics.
For the implemented analysis pipeline, output contracts, and reproducible viewer,
see the [native analysis guide](docs/user-guide/NATIVE_ANALYSIS_GUIDE.md),
[model evaluation structure](docs/user-guide/NATIVE_MODEL_EVALUATION_GUIDE.md) and
[current implementation evidence](docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

## Public OCEL API

The `pix.ocel` namespace exports convenient readers, diagnostic import results,
the model, builder, validator, and canonical identity functions:

```python
from pix.ocel import import_ocel, read_ocel

ocel = read_ocel("example.jsonocel")
print(ocel.summary())
print(ocel.describe())
print(ocel.timezone_type)  # UTC
print(ocel.timezone_info.to_dict())
print(ocel.warnings)
print(ocel.events_by_type("create order"))

# Use import_ocel when failure evidence is needed instead of an exception.
result = import_ocel("example.sqlite")
print(result.summary())
print(result.describe())
```

Invalid semantic candidates do not receive canonical bytes or a digest. Import
results retain structured issues, transformations, source hash and size, and,
when mapping completed, the invalid candidate for diagnostics. `read_ocel()`
raises `OCELImportError`; its `result` attribute exposes the same evidence.

The reader represents canonical timestamps in UTC. Numeric-offset timestamps,
including supported legacy forms, retain their instants. When a timestamp has
no timezone, PIX assumes UTC, emits one aggregated
`TimezoneAssumptionWarning`, and retains the count in `ocel.timezone_info` and
`ocel.warnings`. Import provenance does not affect OCEL equality or its
canonical digest.

## Dependency boundary

```text
Schumpeter -> PIX
PIX -X-> Schumpeter
```

PIX must not import Schumpeter. It also has no runtime dependency on PM4Py,
OCPA, or pandas. Python `>=3.10` is required.

## Repository structure

```text
docs/                  Architecture, specifications, version baselines, and references
docs/user-guide/       Task-oriented public API user guides
src/pix/ocel/          OCEL readers, writers, model, validation, canonical identity
src/pix/contracts/     Immutable analysis and model contracts
src/pix/compute/       Native analysis and model execution
src/pix/viewer/        Offline SVG viewer and bundled ELK layout
examples/             Executable end-to-end native pipeline
tests/                Stage-specific, integration, and optional browser tests
tests/fixtures/        Local sample event logs; excluded from release commits by default
```

## Development

Install the package with development tools:

```bash
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m ruff format --check .
```

The optional browser suite uses `pip install -e ".[dev,browser]"`,
`python -m playwright install chromium`, and `PIX_RUN_BROWSER=1` before running
`python -m pytest tests/browser -q`. JavaScript geometry tests run with
`node --test tests/viewer/test_layout.cjs` (see the viewer README for all tests).

On PowerShell:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider
Remove-Item Env:PYTHONDONTWRITEBYTECODE
```

Passing the current checks establishes consistency for the implemented
contracts, format adapters, and tested canonical vectors. It does not establish
compatibility with every producer-specific extension, scalability at arbitrary
data volumes, process-intelligence correctness, or production readiness.
