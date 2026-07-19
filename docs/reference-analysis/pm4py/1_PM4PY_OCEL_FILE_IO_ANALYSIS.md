# PM4Py OCEL File Input and Output Analysis

**Document type:** Upstream reference analysis / OCEL file-I/O baseline  
**Target project:** PIX  
**Reference library:** PM4Py  
**Reference repository:** `D:\ChantaResearchGroup\PIX-References\pm4py-upstream`  
**Analyzed branch:** `release`  
**Analyzed commit:** `3329bbcbadce8764f7df660fd88636c30793fbd0`  
**PM4Py version:** `2.7.23.3`  
**Analysis date:** 2026-07-19  
**Status:** Source-level OCEL input/output analysis baseline

---

## 0. Purpose and Scope

This document explains how PM4Py reads external OCEL files into its in-memory object-centric representation and serializes that representation back to external files.

The analysis covers:

1. the common OCEL in-memory structure;
2. public OCEL 1.x and OCEL 2.0 read/write APIs;
3. importer and exporter dispatch;
4. CSV, JSON, XML, SQLite, and bundled CSV/Parquet formats;
5. normalization and relation-filter propagation;
6. round-trip preservation limits;
7. preliminary implications for PIX contracts and adapters.

This is a source-structure analysis. It does not establish runtime throughput, memory consumption, or complete standards conformance for every possible dataset.

---

## 1. Analysis Basis

```text
Repository: D:\ChantaResearchGroup\PIX-References\pm4py-upstream
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

Primary inspected areas were:

```text
pm4py/read.py
pm4py/write.py
pm4py/objects/ocel/obj.py
pm4py/objects/ocel/importer/
pm4py/objects/ocel/exporter/
pm4py/objects/ocel/util/
```

---

## 2. Overall I/O Architecture

PM4Py uses format-specific importers and exporters around a common mutable `OCEL` object.

```text
External OCEL file
    ↓
pm4py.read_ocel*()
    ↓
format importer dispatcher
    ↓
selected importer variant
    ↓
Pandas DataFrame reconstruction
    ↓
PM4Py OCEL object
    ↓
process-mining operations
    ↓
pm4py.write_ocel*()
    ↓
format exporter dispatcher
    ↓
selected exporter variant
    ↓
External OCEL file
```

The repeated implementation pattern is:

```text
public API
→ importer.py / exporter.py
→ Variants(Enum)
→ variants/<implementation>.py
→ apply(...)
```

The I/O layer is therefore a collection of format adapters converging on one in-memory model rather than one universal serializer.

---

## 3. Common In-Memory OCEL Structure

PM4Py represents an object-centric event log as a mutable `OCEL` container holding multiple Pandas DataFrames:

```text
OCEL
├── events
├── objects
├── relations          # event-to-object, E2O
├── o2o                # object-to-object
├── e2e                # event-to-event
├── object_changes
├── globals
└── parameters
```

### 3.1 Events and objects

The `events` DataFrame contains an event identifier, activity/type, timestamp, and event attributes. Default columns include:

```text
ocel:eid
ocel:activity
ocel:timestamp
```

The `objects` DataFrame contains an object identifier, object type, and object attributes. Default columns include:

```text
ocel:oid
ocel:type
```

### 3.2 Event-object relations

The internal `relations` DataFrame is denormalized. It generally carries:

```text
event identifier
event activity
event timestamp
object identifier
object type
qualifier
```

Several importers reconstruct activity, timestamp, and object type by looking them up from the event and object tables.

### 3.3 O2O, E2E, and object changes

`o2o` stores source object, target object, and qualifier. `e2e` stores source event, target event, and qualifier.

`object_changes` represents time-dependent attributes with:

```text
object identifier
object type
timestamp
changed field
value in the named field column
```

No inspected OCEL file importer or exporter serialized or reconstructed `e2e`. Its in-memory presence must not be interpreted as proof of file round-trip support.

### 3.4 Configurable columns

The `OCEL` object stores active column names for identifiers, types, timestamps, qualifiers, and changed fields. Importer and exporter parameters may override the defaults.

---

## 4. Public Input APIs

### 4.1 Classic `read_ocel()`

```python
ocel = pm4py.read_ocel(file_path, objects_path=None)
```

It resolves the path and dispatches by extension:

| Extension | Selected path |
| --- | --- |
| `.csv` | Classic Pandas CSV importer |
| `.jsonocel` | Classic JSON-OCEL importer |
| `.xmlocel` | Classic XML-OCEL importer |
| `.sqlite` | Classic Pandas SQLite importer |

For HTTP or HTTPS input, the public helper downloads the resource to a temporary local file and passes that path to the selected importer.

### 4.2 Explicit `read_ocel2()`

```python
ocel = pm4py.read_ocel2(file_path)
```

It recognizes:

| Input | Selected path |
| --- | --- |
| `.ocel.zip` | Bundled OCEL 2.0 importer |
| directory containing `ocel-meta.json` | Uncompressed bundle importer |
| `.sqlite` | OCEL 2.0 SQLite importer |
| `.csv` | Compact OCEL 2.0 CSV importer |
| `.json`, `.jsonocel` | OCEL 2.0 standard JSON importer |
| `.xml`, `.xmlocel` | OCEL 2.0 XML importer |
| `.json.gz`, `.jsonocel.gz` | GZIP JSON importer |
| `.xml.gz`, `.xmlocel.gz` | GZIP XML importer |

For JSON and XML, an optional Rust-backed importer is selected when a supported backend is installed; otherwise, the Python implementation is used.

`read_ocel()` and `read_ocel2()` are not aliases. They select different variants and recognize different external representations.

---

## 5. Common Import Processing

Although parsers differ, their result path generally follows:

```text
parse external representation
→ extract event and object records
→ extract E2O relations
→ extract O2O and object changes when supported
→ instantiate Pandas DataFrames
→ normalize identifiers and timestamps
→ enrich E2O with event/object metadata
→ sort temporal tables
→ construct OCEL(...)
→ apply consistency handling
→ optionally propagate relation filtering
```

### 5.1 Identifier and timestamp normalization

Depending on the importer, PM4Py:

- converts numeric identifiers to strings;
- removes numeric `.0` suffix artifacts;
- parses timestamp strings into datetime values;
- adds a temporary row index;
- sorts events and relations by timestamp and original order;
- removes the temporary index afterward.

### 5.2 Consistency processing

`ocel_consistency.apply()`:

- converts required identifier, activity, and type fields to strings;
- removes rows with null values in processed required columns;
- removes rows with empty strings in processed required columns;
- warns about duplicate event or object identifiers;
- replaces missing qualifiers with empty strings;
- changes the contained DataFrames in place.

Invalid rows are not returned in a structured rejected-record result. They may disappear from the in-memory log.

### 5.3 Relation-filter propagation

Several importer paths propagate filtering from retained relationships to events, objects, E2O, O2O, E2E, and object changes. Not every importer executes the identical post-processing sequence, so behavior must be checked at the selected variant level.

---

## 6. Classic CSV

### 6.1 Physical representation

Classic CSV uses an extended event table and an optional separate object table:

```text
events.csv
├── event ID
├── activity
├── timestamp
├── event attributes
├── ocel:type:<Order> = ['order-1', 'order-2']
└── ocel:type:<Item>  = ['item-1', 'item-2']

objects.csv                  # optional
├── object ID
├── object type
└── object attributes
```

### 6.2 Export

The exporter applies consistency and relation filtering, calls `OCEL.get_extended_table()`, groups related object IDs by event and object type, writes the extended table, and optionally writes the objects DataFrame.

### 6.3 Import

The importer reads both CSVs as strings, detects object-type columns, parses list-like cell values with `ast.literal_eval()`, creates one E2O row per object reference, and infers objects from references if the optional objects file is absent.

### 6.4 Preservation limits

Classic CSV does not reliably preserve:

- relation qualifiers;
- O2O relations;
- object changes;
- E2E relations;
- unreferenced object attributes when no objects file is provided.

It is a flattened interchange representation, not a complete OCEL persistence format.

---

## 7. Compact OCEL 2.0 CSV

### 7.1 Physical representation

The compact OCEL 2.0 CSV variant encodes multiple entity kinds in one table:

```text
id
activity
timestamp
event attribute columns...
ot:<object-type-1>
ot:<object-type-2>
...
```

Object references in `ot:*` columns may include an object identifier, relation qualifier, and JSON-encoded object attributes.

### 7.2 Row interpretation

| Row shape | Meaning |
| --- | --- |
| ID, activity, and timestamp present | Event plus E2O relationships |
| ID, activity, and timestamp absent | Object declaration |
| timestamp present, ID and activity absent | Object attribute/change row |
| activity equals configured `o2o` marker | O2O relation row |

### 7.3 Import

The importer parses timestamps, identifies `ot:` columns, splits object references, registers object types, builds events/E2O/O2O, collects object attributes, places first values on objects, places later values in `object_changes`, infers primitive types, sorts temporal tables, and constructs `OCEL`.

### 7.4 Export

The exporter emits event rows, declaration rows for otherwise undeclared objects, special O2O rows, and timestamped object-change rows. Object attributes may be embedded as compact JSON inside object references.

This preserves more OCEL 2.0 semantics than classic CSV, but its meaning depends on row-shape classification and PM4Py's compact reference grammar.

---

## 8. JSON-OCEL

### 8.1 Classic JSON

Classic JSON uses namespaced, dictionary-indexed structures:

```json
{
  "ocel:global-log": {},
  "ocel:global-event": {},
  "ocel:global-object": {},
  "ocel:objects": {
    "order-1": {
      "ocel:type": "Order",
      "ocel:ovmap": {}
    }
  },
  "ocel:events": {
    "event-1": {
      "ocel:activity": "Create Order",
      "ocel:timestamp": "2026-07-19T00:00:00Z",
      "ocel:vmap": {},
      "ocel:omap": ["order-1"]
    }
  }
}
```

Extended variants recognize typed E2O relationships, qualifiers, O2O, and object changes.

### 8.2 OCEL 2.0 standard JSON

The explicit OCEL 2.0 path writes:

```json
{
  "objectTypes": [
    {"name": "Order", "attributes": []}
  ],
  "eventTypes": [
    {"name": "Create Order", "attributes": []}
  ],
  "objects": [
    {
      "id": "order-1",
      "type": "Order",
      "attributes": [],
      "relationships": []
    }
  ],
  "events": [
    {
      "id": "event-1",
      "type": "Create Order",
      "time": "2026-07-19T00:00:00Z",
      "attributes": [],
      "relationships": [
        {"objectId": "order-1", "qualifier": "created"}
      ]
    }
  ]
}
```

Object base values and later changes are represented as repeated timestamped attributes on an object. Import separates the first value into `objects` and later values into `object_changes`; export combines them again.

### 8.3 Compression and API distinction

The OCEL 2.0 JSON path supports `.json.gz` and `.jsonocel.gz`.

`write_ocel_json()` and `write_ocel2_json()` are not equivalent:

- `write_ocel_json()` selects `CLASSIC` or the internal `OCEL20` variant using `OCEL.is_ocel20()`;
- `write_ocel2_json()` explicitly selects `OCEL20_STANDARD`.

---

## 9. XML-OCEL

The OCEL 2.0 XML exporter writes a hierarchy equivalent in meaning to standard JSON:

```xml
<log>
  <object-types>...</object-types>
  <event-types>...</event-types>
  <objects>
    <object id="order-1" type="Order">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-2" qualifier="parent"/>
      </objects>
    </object>
  </objects>
  <events>
    <event id="event-1" type="Create Order" time="...">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-1" qualifier="created"/>
      </objects>
    </event>
  </events>
</log>
```

The exporter derives type declarations, writes base and timestamped object attributes, and writes E2O/O2O relationships with qualifiers. The importer reverses this mapping into DataFrames, parses typed values, sorts temporal data, and applies consistency/filtering.

The explicit OCEL 2.0 XML path supports `.xml.gz` and `.xmlocel.gz`.

---

## 10. SQLite

### 10.1 Classic SQLite

The classic Pandas variant writes three DataFrames directly:

```text
EVENTS
OBJECTS
RELATIONS
```

This path does not write O2O, E2E, or object changes.

### 10.2 OCEL 2.0 SQLite

The explicit OCEL 2.0 variant uses:

```text
event
object
event_map_type
object_map_type
event_<event-type>
object_<object-type>
event_object
object_object
```

`event` and `object` map IDs to logical types. Type-map tables connect logical type names to physical type-specific tables. Each `event_<type>` table stores timestamps and event attributes; each `object_<type>` table stores base values and time-dependent changes.

`event_object` stores E2O and qualifier. `object_object` stores O2O and qualifier.

During import, PM4Py reads and combines type-specific tables, separates object base rows from change rows, reads relationship tables, enriches E2O with activity/timestamp/object type, sorts temporal data, and constructs `OCEL`.

---

## 11. Bundled CSV/Parquet

### 11.1 Physical forms

The bundle may be a `.ocel.zip` archive or a directory containing `ocel-meta.json`. Parquet is the default table format; CSV can be selected.

```text
bundle/
├── ocel-meta.json
├── events/
│   ├── event_<encoded-event-type>.parquet
│   └── ...
├── objects/
│   ├── object_<encoded-object-type>.parquet
│   └── ...
├── object_changes/
│   ├── object_changes_<encoded-object-type>.parquet
│   └── ...
└── relations/
    ├── e2o.parquet
    └── o2o.parquet
```

Unsafe characters in type names are percent-encoded for filenames.

### 11.2 Metadata

`ocel-meta.json` records:

```text
OCEL version
bundle format version
CSV or Parquet storage format
event type → event table and attribute declarations
object type → object table, changes table, and attribute declarations
E2O table path
O2O table path
```

### 11.3 Export and import

Export creates one table per event type, one base table and one changes table per object type, separate E2O/O2O tables, and metadata describing paths and primitive types. Files are written into a ZIP archive or directory.

Import reads metadata, loads all declared tables, concatenates type-specific frames, reconstructs E2O metadata, normalizes IDs/timestamps, sorts temporal data, and constructs `OCEL`.

The bundle is the most dataset-oriented inspected representation and supports typed columnar Parquet storage.

---

## 12. Public Output APIs

### 12.1 Classic `write_ocel()`

```python
pm4py.write_ocel(ocel, file_path, objects_path=None)
```

| Extension | Selected path |
| --- | --- |
| `.csv` | Classic extended-table CSV |
| `.jsonocel` | Classic or internal OCEL20 JSON variant |
| `.xmlocel` | Classic XML variant |
| `.sqlite` | Classic Pandas SQLite variant |

### 12.2 Explicit `write_ocel2()`

```python
pm4py.write_ocel2(
    ocel,
    file_path,
    storage_format="parquet",
)
```

| Extension | Selected path |
| --- | --- |
| `.ocel.zip` | Bundled CSV/Parquet |
| `.sqlite` | OCEL 2.0 SQLite |
| `.csv` | Compact OCEL 2.0 CSV |
| `.json`, `.jsonocel` | Standard OCEL 2.0 JSON |
| `.xml`, `.xmlocel` | OCEL 2.0 XML |
| JSON/XML `.gz` forms | Compressed standard JSON/XML |

### 12.3 Version inference

`OCEL.is_ocel20()` returns true when it detects a non-empty O2O table, a non-empty object-changes table, or a non-empty relation qualifier. Generic JSON output uses this result to select a variant.

The heuristic does not inspect `e2e` and is not a complete standards-version validator.

---

## 13. Export-Time Normalization and Mutation

Several exporters execute:

```text
input OCEL
→ ocel_consistency.apply()
→ propagate_relations_filtering()
→ format conversion
→ file write
```

Consistency and filtering can replace or filter DataFrames held by the passed `OCEL`. Calling an exporter may therefore alter caller-visible state.

Possible changes include:

- dropping rows with invalid required values;
- coercing identifiers and types to strings;
- replacing null qualifiers;
- filtering events or objects not retained by relations;
- filtering O2O, E2E, or object-change rows with missing endpoints.

Not every exporter performs the same sequence. The mutation risk must be assessed per variant. No common result reports which input records were changed or removed.

---

## 14. Round-Trip Preservation Matrix

| Format | E2O | E2O qualifier | O2O | Object changes | E2E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Classic extended CSV | Partial | No reliable preservation | No | No | No |
| Classic SQLite | Yes | Schema-column dependent | No | No | No |
| Classic JSON/XML | Yes | Variant dependent | Extended variant dependent | Extended variant dependent | No |
| Compact OCEL 2.0 CSV | Yes | Yes | Yes | Yes | No |
| Standard OCEL 2.0 JSON | Yes | Yes | Yes | Yes | No |
| OCEL 2.0 XML | Yes | Yes | Yes | Yes | No |
| OCEL 2.0 SQLite | Yes | Yes | Yes | Yes | No |
| OCEL 2.0 bundle | Yes | Yes | Yes | Yes | No |

“Yes” means an explicit serialization and reconstruction path was observed. It does not prove semantic round-trip equality for every data type or malformed dataset.

No reference to `ocel.e2e` was found under the inspected OCEL importer/exporter packages.

---

## 15. Main Risks and Ambiguities

1. **Format-dependent loss** — classic CSV and SQLite do not represent the full in-memory structure.
2. **Silent normalization** — invalid rows may be removed rather than reported.
3. **Export-side mutation** — writing may change the passed object.
4. **Implicit object inference** — classic CSV without an object table reconstructs objects from relations.
5. **API-family ambiguity** — classic and explicit OCEL 2.0 functions select different variants.
6. **Dynamic change columns** — changed-field names and values must be interpreted together.
7. **Relation denormalization** — duplicated event/object metadata can become inconsistent.
8. **Missing loss report** — no common contract lists dropped, inferred, coerced, or unsupported data.

---

## 16. Preliminary PIX Implications

### 16.1 Patterns worth retaining as references

- format adapters converging on a neutral internal model;
- explicit classic and OCEL 2.0 variants;
- type-specific relational and bundle layouts;
- separate E2O, O2O, and object-change representations;
- GZIP and Parquet storage profiles.

### 16.2 Patterns requiring redesign for PIX

- destructive normalization during import;
- mutation during export;
- no structured import/export result;
- no common loss declaration;
- no E2E file round trip;
- implicit schema-version inference;
- denormalized relation semantics without discrepancy evidence.

### 16.3 Candidate adapter-result shape

A PIX import adapter may need to return more than `ProcessDataset`:

```text
DatasetImportResult
├── dataset
├── source_format
├── source_format_version
├── normalized_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source references
```

An export adapter may need:

```text
DatasetExportResult
├── target_format
├── target_format_version
├── written_components
├── omitted_components
├── lossy_conversions
├── assumptions
└── output artifact reference
```

These are preliminary design implications, not approved PIX contracts.

---

## 17. Unknowns

The following remain **unknown** from source inspection alone:

- exact round-trip equality for every primitive and timestamp type;
- performance at Schumpeter-scale OCEL volumes;
- maximum practical object and relation counts;
- memory overhead of relation denormalization;
- edge-case equivalence between Python and optional Rust importers;
- complete standards compliance of every PM4Py extension;
- behavior for every duplicate or conflicting object attribute case;
- whether a non-obvious external integration serializes E2E outside the inspected packages.

---

## 18. Validity and Withdrawal Conditions

This analysis is valid for PM4Py commit:

```text
3329bbcbadce8764f7df660fd88636c30793fbd0
```

Reassess or withdraw the relevant claims if:

- PM4Py changes the public OCEL I/O APIs;
- importers/exporters add E2E serialization;
- exporters become explicitly non-mutating;
- consistency handling returns structured rejected-record information;
- classic CSV or SQLite gains full OCEL 2.0 semantics;
- the compact CSV convention or bundle layout changes;
- executed round-trip tests contradict the source-derived matrix;
- optional Rust backends produce materially different structures;
- PIX changes its canonical data or evidence-lineage requirements.

---

## 19. Final Assessment

**PM4Py handles OCEL files through format-specific importer and exporter variants that converge on a mutable Pandas-based `OCEL` object. Explicit OCEL 2.0 JSON, XML, SQLite, compact CSV, and bundle paths preserve E2O relationships, qualifiers, O2O relationships, and object changes more completely than classic CSV and classic SQLite, but the inspected file-I/O layer does not round-trip E2E relations or provide a common record of normalization, rejected rows, inferred data, mutation, or semantic loss.**
