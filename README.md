# PIX

PIX is an independent, deterministic Process Intelligence computation and
interpretation engine.

## Status

PIX `0.1.2` provides an immutable in-memory OCEL model, deterministic dataset
construction and semantic validation, a versioned canonical byte serializer,
SHA-256 dataset identity, and evidence-preserving import-result contracts.

PIX does not yet provide external file readers or writers, OCEL 2.0 interchange
serializers, process-intelligence operators, or a production-ready public API.
PM4Py and OCPA remain reference implementations and are not PIX runtime
dependencies.

## Implemented OCEL flow

```text
source adapters (future)
        |
        v
import-result contracts
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

## Public OCEL API

The `pix.ocel` namespace exports the model, builder, validator, canonical
serializer and digest, and import-result contracts. A minimal valid dataset can
be identified as follows:

```python
from pix.ocel import OCEL, canonical_digest

identity = canonical_digest(OCEL())
print(identity.identifier)
```

Invalid semantic candidates do not receive canonical bytes or a digest. Import
results retain structured issues, transformations, source evidence, and—when
available—the invalid candidate for diagnostics.

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
src/pix/ocel/          OCEL model, validation, canonical identity, and ingest contracts
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

Passing the current checks establishes consistency only for the implemented
contracts and tested canonical vectors. It does not establish external-format
compatibility, scalability, process-intelligence correctness, or production
readiness.
