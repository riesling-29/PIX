# Reading and Inspecting OCEL 2.0 Logs

This guide applies to PIX `0.2.0`.

## Supported inputs

PIX reads OCEL 2.0 JSON, XML, and SQLite files without PM4Py, OCPA, pandas, or
another runtime dependency.

Common recognized names include:

- JSON: `.json`, `.jsonocel`, `.json.gz`, `.jsonocel.gz`
- XML: `.xml`, `.xmlocel`, `.xml.gz`, `.xmlocel.gz`
- SQLite: `.sqlite`, `.sqlite3`, `.db`

When the filename is not informative, PIX can detect uncompressed JSON, XML,
and SQLite content from its leading bytes.

## Read a valid OCEL

Use `read_ocel()` for the normal path-based workflow:

```python
from pix.ocel import read_ocel

log = read_ocel("order-management.json")

print(log.summary())
print(log.describe())
```

`read_ocel()` returns an immutable canonical `OCEL`. If the source cannot
produce a valid OCEL, it raises `OCELImportError` instead of returning a
partially valid object.

## Inspect the dataset

The returned object exposes deterministic information suitable for terminal
output, application code, and AI tools:

```python
print(log.info())
print(log.describe())

event = log.get_event("e1")
obj = log.get_object("o1")

create_events = log.events_by_type("create order")
orders = log.objects_by_type("order")

event_relations = log.e2o_for_event("e1")
event_objects = log.objects_for_event("e1")
object_events = log.events_for_object("o1")

outgoing = log.outgoing_o2o("o1")
incoming = log.incoming_o2o("o1")
```

Qualifier filters are optional and preserve qualified relation evidence:

```python
targets = log.objects_for_event("e1", qualifier="target")
audit_relations = log.e2o_for_event("e1", qualifier="audit")
```

PIX does not collapse two relations merely because they have the same event
and object endpoints but different qualifiers.

## Timestamp behavior

Canonical PIX timestamps are timezone-aware and represented in UTC. The
default reader applies these rules without requiring extra parameters:

1. ISO 8601 timestamps with `Z` remain UTC.
2. Timestamps with numeric offsets retain their instants and are represented in
   UTC.
3. Supported legacy timestamps containing an explicit numeric `GMT` offset are
   parsed and represented in UTC.
4. When timezone information is absent, PIX assumes UTC and records a warning.

Inspect the result directly:

```python
print(log.timezone_type)               # "UTC"
print(log.timezone_info.source_type)   # e.g. "OFFSET_AWARE"
print(log.timezone_info.to_dict())
print(log.warnings)
print(log.import_info.to_dict())
```

Possible `source_type` values are:

- `UTC`
- `OFFSET_AWARE`
- `LEGACY_OFFSET_AWARE`
- `ASSUMED_UTC`
- `MIXED_WITH_ASSUMED_UTC`

When timezone-free values are encountered, `read_ocel()` emits one aggregated
`TimezoneAssumptionWarning`. The warning count remains available through
`log.timezone_info.assumed_utc_count` and `log.warnings`.

The import metadata is evidence about reading the source. It does not change
OCEL equality or the Canonical V1 digest. If authoritative source timezone
metadata later becomes available, re-import logs that used an assumed timezone.

## Diagnose an invalid source

Use `import_ocel()` when an application needs structured evidence rather than
an exception-only workflow:

```python
from pix.ocel import import_ocel

result = import_ocel("source.sqlite")

print(result.status)
print(result.summary())
print(result.describe())

if result.valid:
    log = result.require_ocel()
else:
    for issue in result.import_issues:
        print(issue.stage, issue.code, issue.message, issue.at)

    if result.semantic_report is not None:
        for issue in result.semantic_report.issues:
            print(issue.code, issue.message, issue.at)
```

Import failures are separated into these terminal statuses:

- `unavailable`
- `unsupported`
- `syntax_invalid`
- `schema_invalid`
- `mapping_invalid`
- `semantic_invalid`
- `valid`

A semantic-invalid result retains the mapped candidate and semantic report. A
failure before semantic mapping does not fabricate a candidate.

## Handle `OCELImportError`

`OCELImportError` carries the same `ImportResult` used by `import_ocel()`:

```python
from pix.ocel import OCELImportError, read_ocel

try:
    log = read_ocel("source.json")
except OCELImportError as error:
    print(error.result.status)
    print(error.result.describe())
```

## Source and canonical identity

For valid imports, `ImportResult` records both the source-file identity and the
canonical dataset identity:

```python
result = import_ocel("source.xml")

print(result.source_sha256)
print(result.source_size)

if result.canonical_digest is not None:
    print(result.canonical_digest.identifier)
```

Different JSON, XML, and SQLite files may have different source hashes while
producing the same canonical digest when they represent the same OCEL.

## Current compatibility boundary

PIX automatically handles supported timestamp representations but does not
silently deduplicate attributes, remove dangling relations, synthesize missing
objects, or discard invalid records. Such behavior requires a separately
defined, evidence-preserving compatibility policy.

Passing schema validation alone does not establish semantic validity. Use the
`ImportResult` and its semantic report when onboarding a new producer or export
tool.
