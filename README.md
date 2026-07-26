# PIX

PIX is an independent, deterministic Process Intelligence computation and interpretation engine.

## Status

PIX is currently at package-foundation initialization. The repository provides
installable package metadata, layer-owner modules, and import-boundary tests only.
No production capability is claimed, and no process operator is implemented yet.

## Internal architecture

The intended responsibility flow is:

```text
contracts
→ compute
→ intelligence
→ projection
→ engine / api
```

The owner modules currently document these boundaries without implementing their
future behavior.

## Dependency boundary

```text
Schumpeter → PIX
PIX ─X→ Schumpeter
```

PIX must not import Schumpeter. PM4Py and OCPA are architectural references, not
PIX runtime dependencies, and their source code is maintained outside this
repository.

## Repository structure

```text
docs/        Architecture, prompts, and reference-analysis records
src/pix/     Installable PIX package and layer-owner modules
tests/       Foundation import and dependency-boundary tests
```

## Development

Install the package with development tools:

```bash
python -m pip install -e ".[dev]"
```

Run the foundation checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
python -m ruff check .
python -m ruff format --check .
```

On PowerShell, set the bytecode environment variable before running pytest:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider
Remove-Item Env:PYTHONDONTWRITEBYTECODE
```

Passing these foundation tests shows only that packaging and declared import
boundaries are internally consistent. It is not production certification and
does not establish process-intelligence correctness.
