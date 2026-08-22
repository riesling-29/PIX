# PIX

PIX is an independent, deterministic Process Intelligence computation and
interpretation engine.

## Status

PIX `0.2.0` provides evidence-preserving OCEL 2.0 JSON, XML, and SQLite
readers, an immutable in-memory OCEL model, deterministic dataset construction
and semantic validation, a versioned canonical byte serializer, SHA-256 dataset
identity, and evidence-preserving import results.

PIX does not yet provide external file writers, OCEL 2.0 interchange
serializers, process-intelligence operators, or a production-ready public API.
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
src/pix/ocel/          OCEL readers, model, validation, and canonical identity
src/pix/               Remaining layer-owner modules
tests/ocel/            OCEL behavior tests and canonical golden vectors
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
