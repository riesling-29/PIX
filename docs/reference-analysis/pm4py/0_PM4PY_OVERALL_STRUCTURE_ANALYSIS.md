# PM4Py Overall Structure Analysis

**Document type:** Upstream reference analysis / overall structure baseline  
**Target project:** PIX  
**Reference library:** PM4Py  
**Reference repository:** `D:\ChantaResearchGroup\PIX-References\pm4py-upstream`  
**Analyzed branch:** `release`  
**Analyzed commit:** `3329bbcbadce8764f7df660fd88636c30793fbd0`  
**PM4Py version:** `2.7.23.3`  
**Analysis date:** 2026-07-19  
**Status:** Source-structure analysis baseline

---

## 0. Purpose and Scope

This document records the overall source structure of PM4Py before PIX decides what should be inherited, adapted, replaced, or left unused.

The analysis covers:

1. repository and package structure;
2. public API organization;
3. core algorithm-dispatch pattern;
4. principal data and process-model objects;
5. representative execution paths;
6. object-centric functionality;
7. dependency boundaries and result contracts;
8. testing structure;
9. preliminary implications for PIX.

This document does not evaluate every PM4Py algorithm. It also does not establish that PM4Py code may be copied into PIX. Runtime performance, algorithmic correctness across all inputs, and licensing compatibility with the eventual PIX distribution model are outside the verified scope of this analysis.

---

## 1. Analysis Basis

### 1.1 Confirmed repository state

The analysis was performed against the following local checkout:

```text
Repository: D:\ChantaResearchGroup\PIX-References\pm4py-upstream
Remote:     https://github.com/process-intelligence-solutions/pm4py.git
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

At the time of inspection, the upstream checkout had no local Git changes.

### 1.2 Confirmed source counts

The local tree contained 1,657 Python files under the `pm4py` package.

| Area | Python files | Principal responsibility |
| --- | ---: | --- |
| `pm4py/algo` | 881 | Discovery, conformance, filtering, transformation, evaluation, and simulation algorithms |
| `pm4py/objects` | 359 | Event-log, OCEL, Petri-net, process-tree, BPMN, DFG, and related models |
| `pm4py/statistics` | 156 | Frequency, temporal, variant, activity, and object-centric statistics |
| `pm4py/visualization` | 142 | Graphviz and other model/result visualization |
| `pm4py/streaming` | 58 | Streaming import, conversion, and online algorithms |
| `pm4py/util` | 40 | Constants, parameter handling, date parsing, compression, and shared utilities |
| top-level `pm4py/*.py` | 21 | User-facing facade modules and package metadata |

These counts describe physical source organization only. They do not measure code quality, complexity, or feature importance.

### 1.3 License fact and unresolved compatibility

The inspected repository declares the open-source edition as **GNU Affero General Public License version 3 (AGPL-3.0)**. The repository also states that a separate commercial license is available.

Whether PM4Py source code can be incorporated into PIX without changing PIX's intended licensing or deployment model is currently **unknown**, because the final PIX licensing and distribution conditions have not been established in the analyzed material. Architectural study and source-code reuse must therefore be treated as separate decisions.

---

## 2. Top-Level Repository Structure

The PM4Py repository is organized as follows:

```text
pm4py-upstream/
├── .github/                 # GitHub automation and repository metadata
├── docs/                    # Documentation sources
├── examples/                # Executable usage examples
├── files/                   # Supporting project files
├── notebooks/               # Notebook-based examples and analysis
├── pm4py/                   # Installable Python package
├── safety_checks/           # Additional checks
├── tests/                   # Test runner, fixtures, and test modules
├── third_party/             # Third-party license information
├── README.md
├── CHANGELOG.md
├── COVERAGE.md
├── requirements*.txt
└── setup.py
```

The packaging entry point is `setup.py`. It loads version and package metadata from `pm4py/meta.py`, discovers packages whose names begin with `pm4py`, and installs the dependencies declared in `requirements.txt`.

The essential runtime dependency set includes NumPy, Pandas, NetworkX, Graphviz, SciPy, lxml, Matplotlib, pytz, and tqdm. Several additional integrations are optional.

---

## 3. Installable Package Structure

The main package has two distinct surfaces:

1. top-level user-facing facade modules;
2. large internal implementation packages.

```text
pm4py/
├── __init__.py
├── read.py
├── write.py
├── discovery.py
├── conformance.py
├── filtering.py
├── convert.py
├── analysis.py
├── stats.py
├── ocel.py
├── org.py
├── sim.py
├── vis.py
├── connectors.py
├── llm.py
├── ml.py
├── privacy.py
├── utils.py
│
├── algo/
├── objects/
├── statistics/
├── visualization/
├── streaming/
└── util/
```

### 3.1 Top-level facade modules

The top-level modules expose simplified, domain-oriented functions:

| Facade module | Representative responsibility |
| --- | --- |
| `read.py` | Read XES, PNML, BPMN, DFG, PTML, and OCEL formats |
| `write.py` | Export event logs and process models |
| `discovery.py` | Discover DFGs, process trees, Petri nets, BPMN, Declare, and related models |
| `conformance.py` | Token replay, alignments, fitness, precision, and specialized conformance |
| `filtering.py` | Case, event, path, temporal, variant, and OCEL filtering |
| `convert.py` | Convert logs and process models between supported representations |
| `analysis.py` | Soundness and structural analysis |
| `stats.py` | User-facing statistical queries |
| `ocel.py` | Object-centric summaries, discovery, filtering, and enrichment |
| `vis.py` | User-facing visualization functions |

`pm4py/__init__.py` imports these modules and re-exports many of their functions directly. The intended user experience is therefore:

```python
import pm4py

log = pm4py.read_xes("event-log.xes")
tree = pm4py.discover_process_tree_inductive(log)
net, initial_marking, final_marking = pm4py.convert_to_petri_net(tree)
```

The facade performs more than simple forwarding. Depending on the function, it may:

- validate required DataFrame columns;
- construct internal parameter dictionaries;
- select an algorithm variant;
- route based on input type and argument count;
- convert input or output representations;
- choose multiprocessing behavior;
- emit compatibility or deprecation warnings.

### 3.2 Facade size

Several facade modules are themselves substantial:

| Module | Top-level functions | Approximate lines |
| --- | ---: | ---: |
| `discovery.py` | 27 | 1,462 |
| `conformance.py` | 21 | 1,285 |
| `filtering.py` | 41 | 1,852 |
| `stats.py` | 25 | 1,193 |
| `ocel.py` | 27 | 870 |
| `vis.py` | 47 | 1,820 |

The facade is therefore an important architectural layer, but it is not uniformly thin.

---

## 4. Main Internal Packages

### 4.1 `pm4py.algo`

`algo` is the largest package and is the functional center of PM4Py.

```text
algo/
├── analysis/
├── anonymization/
├── clustering/
├── comparison/
├── concept_drift/
├── conformance/
├── connectors/
├── decision_mining/
├── discovery/
├── evaluation/
├── filtering/
├── label_splitting/
├── merging/
├── organizational_mining/
├── querying/
├── reduction/
├── simulation/
└── transformation/
```

Major discovery families include:

```text
discovery/
├── alpha/
├── declare/
├── dfg/
├── footprints/
├── genetic/
├── heuristics/
├── ilp/
├── inductive/
├── log_skeleton/
├── ocel/
├── powl/
├── split_miner/
├── temporal_profile/
└── transition_system/
```

Major conformance families include:

```text
conformance/
├── alignments/
├── antialignments/
├── declare/
├── footprints/
├── log_skeleton/
├── multialignments/
├── ocel/
├── temporal_profile/
└── tokenreplay/
```

### 4.2 `pm4py.objects`

`objects` contains in-memory representations, model semantics, importers, exporters, and conversions.

```text
objects/
├── log/
├── ocel/
├── petri_net/
├── process_tree/
├── bpmn/
├── dfg/
├── heuristics_net/
├── transition_system/
├── trie/
├── powl/
├── ocpn/
├── oc_causal_net/
├── stochastic_petri/
├── random_variables/
└── conversion/
```

This package is not limited to passive data contracts. Some subpackages also contain semantics, retrieval, filtering, conversion, importer, and exporter behavior.

### 4.3 `pm4py.statistics`

The statistics package calculates reusable process facts, including:

- activity and attribute frequencies;
- start and end activities;
- variants;
- directly/eventually-following behavior;
- service and sojourn time;
- overlap, concurrency, rework, and passed time;
- trace and process-cube statistics;
- object-centric statistics.

This area is conceptually close to part of the future PIX Compute Layer. Physically, however, PM4Py algorithms also import and compose these statistical functions directly.

### 4.4 `pm4py.visualization`

Visualization is divided by process-model or result type, including Petri nets, BPMN, DFG, process trees, OCEL, transition systems, performance spectra, and alignment tables.

The most common rendering mechanism is Graphviz, with Matplotlib and NetworkX used in other paths.

### 4.5 `pm4py.streaming`

The streaming package provides separate import, conversion, connectors, streams, and algorithms for online event processing. It is a parallel capability rather than the organizing center of the library.

### 4.6 `pm4py.util`

The utility package centralizes:

- environment-controlled defaults;
- standard XES and OCEL parameter keys;
- generic parameter extraction;
- algorithm-variant resolution;
- date/time parsing;
- DataFrame utilities;
- compression and low-level helper functions.

---

## 5. Repeated Algorithm Organization Pattern

The most characteristic PM4Py implementation pattern is:

```text
user-facing function
    ↓
family-level algorithm.py
    ↓
Variants(Enum)
    ↓
variants/<implementation>.py
    ↓
apply(..., parameters=dict)
```

The analyzed tree contained:

- 106 files named `algorithm.py`;
- 164 directories named `variants`.

The common dispatcher resembles:

```python
class Variants(Enum):
    CLASSIC = classic
    ALTERNATIVE = alternative


def apply(data, variant=Variants.CLASSIC, parameters=None):
    return exec_utils.get_variant(variant).apply(data, parameters)
```

`pm4py.util.exec_utils` supports both `Enum` keys and raw string keys. This preserves compatibility between typed enumerations and older dictionary-based parameter usage.

### 5.1 Strengths of this pattern

- a new implementation can be added without changing every caller;
- one algorithm family can expose multiple backends;
- callers can select performance or semantic variants;
- implementation modules remain smaller than the public facade;
- optional dependencies can be loaded only when a path is used.

### 5.2 Structural costs of this pattern

- `apply()` does not communicate operator semantics by name;
- `parameters: dict` weakens static validation;
- variant-specific options are not represented by a uniform typed contract;
- result types differ between algorithm families;
- operator identity and version are not included in results;
- unsupported, unavailable, and invalid-input states are not standardized.

These costs are observations about architectural suitability for PIX, not proof that the pattern is defective for PM4Py's own scientific-library purpose.

---

## 6. Representative Execution Paths

### 6.1 XES import

The public call:

```python
log = pm4py.read_xes("event-log.xes")
```

follows this approximate path:

```text
pm4py.read_xes
→ resolve local path or remote URL
→ select parser/backend
→ pm4py.objects.log.importer.xes.importer.apply
→ selected Variants member
→ variants/<parser>.apply
→ EventLog, Pandas DataFrame, or optional lazy representation
→ optional normalization/conversion
```

Supported variants in the inspected source include:

- chunk-regex parsing;
- XML iterparse;
- XES 2.0 iterparse;
- memory-compressed iterparse;
- line-by-line parsing;
- optional Rust-backed parsing.

The public API defaults away from the legacy `EventLog` representation. `EventLog`, `Trace`, and `EventStream` are marked by runtime warnings as deprecated in favor of DataFrame-oriented use.

### 6.2 Inductive Miner

The Process Tree path is:

```text
DataFrame / EventLog / DFG
→ facade validation and property extraction
→ pm4py.algo.discovery.inductive.algorithm.apply
→ normalize or compress traces to a univariate variant log
→ select IM, IMf, or IMd
→ recursive base-case, cut, and fall-through processing
→ fold and sort the resulting ProcessTree
→ ProcessTree
```

`discover_petri_net_inductive()` does not independently implement Petri-net discovery. It first calls Process Tree discovery and then converts the Process Tree into a Petri net with initial and final markings:

```text
log
→ discover_process_tree_inductive
→ ProcessTree
→ convert_to_petri_net
→ PetriNet + initial marking + final marking
```

This is an example of PM4Py using conversion paths to compose capabilities.

### 6.3 Alignment conformance

`conformance_diagnostics_alignments()` selects behavior from the runtime shape of its arguments:

```text
PetriNet + markings → Petri-net alignments
DFG + boundaries   → DFG alignments
ProcessTree        → Process-tree alignments
EventLog/DataFrame → edit-distance log-to-log alignments
other model        → attempt conversion to Petri net, then align
```

The facade also decides whether to use multiprocessing and whether to return the native list/dictionary diagnostics or a DataFrame.

This provides a convenient polymorphic user API, but the accepted signature and failure behavior cannot be fully understood from a single static return contract.

### 6.4 Model conversion

Model conversion is primarily type-directed:

```text
ProcessTree ─┐
BPMN        ─┤
Heuristics  ─┼→ convert_to_petri_net → PetriNet + markings
POWL        ─┤
DFG         ─┘
```

Conversions are a significant internal integration mechanism. Some facade operations attempt a conversion automatically when a direct implementation is unavailable.

---

## 7. Data and Model Objects

### 7.1 Traditional event-log model

The legacy object model consists of:

```text
Event       # mapping-like event attributes
Trace       # sequence of Event plus trace attributes
EventStream # sequence of events plus stream/log metadata
EventLog    # EventStream-derived collection of traces
```

These objects are mutable. They expose list-like mutation operations such as `append`, `insert`, and item assignment.

The current public direction is predominantly DataFrame-based, while legacy objects remain for compatibility with established algorithms and consumers.

### 7.2 Process-model objects

PM4Py defines native objects for several model families:

- Petri nets and markings;
- process trees;
- BPMN graphs;
- directly-follows graphs;
- heuristics nets;
- transition systems;
- tries;
- POWL;
- stochastic Petri nets;
- object-centric Petri nets;
- object-centric causal nets.

These objects are supported by model-specific conversion, semantics, importer, exporter, analysis, and visualization modules.

### 7.3 Object-Centric Event Log model

The PM4Py `OCEL` object is a mutable container around multiple Pandas DataFrames:

```text
OCEL
├── events
├── objects
├── relations          # event-to-object relations
├── o2o                # object-to-object relations
├── e2e                # event-to-event relations
├── object_changes
├── globals
└── parameters
```

The object also stores configurable column names for:

- event identifier;
- event activity;
- event timestamp;
- object identifier;
- object type;
- relation qualifier;
- changed field.

The `relations` DataFrame is denormalized for calculation convenience: it may include event activity, event timestamp, and object type in addition to event and object identifiers.

### 7.4 OCEL consistency handling

The inspected `ocel_consistency.apply()` function:

- converts identifier, activity, and type columns to strings;
- removes rows containing null values in required processed columns;
- removes rows with empty strings in those columns;
- warns about duplicate event or object identifiers;
- replaces missing relation qualifiers with empty strings;
- mutates DataFrames held by the `OCEL` object;
- returns the same logical OCEL container after normalization.

It does not return a structured integrity result carrying status, offending relation identifiers, evidence references, or assumptions. Filtering-propagation utilities can remove no-longer-reachable events, objects, or relations by mutating the relevant DataFrames.

Consequently, PM4Py consistency handling is primarily operational normalization for later analysis. It is not equivalent to PIX's proposed evidence-preserving integrity computation.

---

## 8. Object-Centric Function Distribution

Object-centric behavior is distributed across PM4Py rather than implemented as an independent internal engine:

```text
pm4py/ocel.py
    User-facing OCEL facade

pm4py/objects/ocel/
    OCEL object, import/export, validation, consistency, filtering utilities

pm4py/algo/discovery/ocel/
    OC-DFG, OCPN, OTG, ETOT, interleaving and related discovery

pm4py/algo/conformance/ocel/
    OC-DFG, OTG, and ETOT comparison-based conformance

pm4py/algo/transformation/ocel/
    Feature extraction, graph conversion, OLAP, splitting

pm4py/statistics/ocel/
    Object graphs, event-to-object statistics, interleavings

pm4py/visualization/ocel/
    OC-DFG and OCPN visualization
```

### 8.1 OCEL flattening

`ocel_flattening(ocel, object_type)` projects an object-centric log into a traditional case-centric DataFrame:

```text
selected object type
→ objects of that type become case identifiers
→ event-object relations connect cases to events
→ event attributes are merged
→ standard XES activity, timestamp, and case columns are produced
```

This is a projection operation with direct relevance to PIX trace reconstruction. It also shows a semantic limitation: a single object type must be chosen as the case perspective, so flattening loses some of the original multi-object context.

### 8.2 OC-DFG discovery

The public OC-DFG path is:

```text
pm4py.discover_ocdfg
→ build column and performance parameters
→ pm4py.algo.discovery.ocel.ocdfg.algorithm.apply
→ Variants.CLASSIC
→ variants.classic.apply
→ dictionary result
```

The result dictionary includes activities, object types, per-object-type edges, start activities, end activities, and optional performance measurements.

### 8.3 Object summaries

The top-level OCEL facade also performs several direct Pandas computations, such as:

- lifecycle activity sequences per object;
- lifecycle start and end timestamps;
- lifecycle duration;
- interacting-object graphs;
- activities per object type;
- related-object counts per event.

This indicates that PM4Py does not enforce one universal boundary between low-level computation and user-facing orchestration.

---

## 9. Dependency Boundaries

The apparent dependency direction is approximately:

```text
facade
   ↓
algo
   ↓
objects / statistics / util
```

The actual imports are not strictly one-way.

Static inspection found examples of:

- modules under `objects` importing `algo`;
- multiple `algo` modules importing `statistics`;
- at least one `algo` path importing visualization behavior;
- facade modules importing conversion and algorithm implementations directly;
- conformance functions falling back to model conversion.

PM4Py is therefore not organized around an enforced clean-layer or ports-and-adapters dependency rule. Its internal structure is better described as feature-oriented packages connected through common object types, dictionaries, conversion utilities, and dispatcher conventions.

This description is not a criticism by itself. A broad scientific library may reasonably prioritize algorithm availability and composability over strict architectural isolation.

---

## 10. Input and Result Contracts

### 10.1 Inputs

PM4Py algorithms commonly accept one or more of:

- Pandas DataFrame;
- legacy `EventLog` or `Trace`;
- `OCEL`;
- native process-model objects;
- tuples of model plus initial/final state;
- dictionaries representing graphs or configuration;
- optional `parameters` dictionaries.

Column semantics are usually conveyed through standard string keys such as:

```text
concept:name
case:concept:name
time:timestamp
ocel:eid
ocel:oid
ocel:type
```

### 10.2 Outputs

There is no single result envelope shared by all algorithms. Return types include:

- `pandas.DataFrame`;
- `EventLog`;
- `OCEL`;
- `ProcessTree`;
- `PetriNet` plus markings;
- dictionaries;
- lists of dictionaries;
- numeric values;
- tuples and sets.

The following fields are not universally enforced:

- computation identifier;
- operator name and version;
- explicit status such as `computed`, `unavailable`, or `invalid_input`;
- source event and object identifiers;
- assumptions;
- deterministic normalization identity;
- evidence references;
- withdrawal conditions.

This differs materially from the proposed PIX `ComputationResult` and `ProcessFinding` contracts.

### 10.3 Failure and unknown states

Failure signaling varies by function. Depending on the path, PM4Py may:

- raise a generic exception;
- emit a warning;
- attempt automatic conversion;
- remove inconsistent rows;
- return an empty structure;
- return a diagnostics dictionary whose schema is algorithm-specific.

The absence of a universal result status means that an empty result cannot be assumed to have one common meaning across PM4Py.

---

## 11. Testing and Examples

### 11.1 Confirmed physical structure

The inspected repository contained:

- 102 Python test files;
- 206 Python example files;
- input fixtures and format-specific test data;
- a custom test runner;
- coverage-focused test modules;
- documentation-oriented and simplified-interface tests.

Tests are mostly placed in a relatively flat `tests/` directory rather than mirroring every package path.

### 11.2 Repository-reported measurements

The repository's `COVERAGE.md`, dated 2026-07-17, reports:

```text
Tests discovered:       929
Passed:                 926
Skipped:                3
Failed:                 0
Statement coverage:     90.22%
Covered statements:     64,403 / 71,387
```

These are upstream-recorded figures. They were not independently reproduced during this structure analysis. Actual test results and coverage in the current PIX development environment are therefore **unknown**.

---

## 12. Architectural Characterization

### 12.1 Confirmed structural facts

- PM4Py exposes a broad functional facade through `pm4py/*.py` and `pm4py/__init__.py`.
- The majority of source files are algorithm implementations.
- Algorithm families repeatedly use `algorithm.py`, `Variants(Enum)`, variant modules, and `apply()` dispatch.
- DataFrame is the preferred current representation for traditional event-log operations.
- Native mutable model objects remain central for process models and OCEL.
- Conversion paths are used to compose algorithms and model representations.
- Object-centric functionality spans objects, discovery, conformance, transformation, statistics, and visualization packages.
- Result shapes are heterogeneous and are not wrapped in a universal computation contract.
- Internal package dependencies are not governed by a strict one-way layer boundary.

### 12.2 Data-based interpretation

The observed structure is most accurately characterized as a **feature-oriented modular monolith for scientific process-mining algorithms**.

The evidence supporting this interpretation is:

1. one installable package contains a very broad feature set;
2. algorithm families are modularized internally;
3. common objects and converters connect those modules;
4. facade functions route dynamically across implementations;
5. package boundaries do not enforce a strict dependency direction;
6. no independent compute-result or intelligence-result protocol governs the system.

This characterization should be withdrawn if a later full dependency analysis reveals enforced boundaries or runtime plugin contracts that are not visible in the inspected source paths.

---

## 13. Preliminary PIX Inheritance Implications

### 13.1 Patterns worth retaining as references

The following PM4Py patterns are plausible references for PIX:

1. **Public facade separated from implementation packages**  
   Consumers do not need to know internal algorithm locations.

2. **Algorithm-family organization**  
   Related implementations are grouped under a stable semantic family.

3. **Replaceable variants**  
   Multiple implementations can exist behind one conceptual operation.

4. **Explicit converters and projections**  
   Process representations can be transformed without embedding every representation in every algorithm.

5. **DataFrame-oriented computation paths**  
   Tabular computation can be efficient and interoperable when kept behind stable contracts.

6. **Broad fixture and example coverage**  
   Algorithms are accompanied by real files, negative paths, format tests, and executable examples.

### 13.2 Patterns that conflict with the current PIX baseline

The following patterns should not be inherited without redesign:

1. **Mutable canonical OCEL container**  
   PIX requires predictable neutral contracts and reproducible computation inputs.

2. **Untyped `parameters` dictionaries as the main operator contract**  
   PIX operators require explicit semantics, assumptions, and versioning.

3. **Heterogeneous unwrapped results**  
   PIX requires computation status, source references, and unavailable-state preservation.

4. **Automatic normalization that removes invalid rows**  
   PIX must preserve and report integrity defects rather than allowing them to disappear silently.

5. **Implicit conversion and fallback**  
   PIX must make semantic projections and assumptions visible.

6. **Compute and interpretation without an enforced boundary**  
   PIX's Compute Layer must remain independently testable from the Intelligence Layer.

7. **Broad feature growth**  
   PM4Py's discovery, visualization, machine learning, and general-purpose mining breadth exceeds PIX v0.1 scope.

8. **Direct source-code inheritance before license resolution**  
   Architectural learning does not itself establish legal compatibility for code reuse.

### 13.3 Preliminary adaptation mapping

| PM4Py concept | Possible PIX interpretation | Required PIX strengthening |
| --- | --- | --- |
| facade function | public PIX operator/API | preserve `compute → interpret → project` |
| `algorithm.py` | operator dispatcher | explicit operator identity and version |
| `Variants(Enum)` | operator implementation selection | typed configuration and deterministic selection |
| `parameters: dict` | operator configuration | validated contract rather than open dictionary |
| DataFrame/EventLog/OCEL | input representation | normalize into neutral `ProcessDataset` |
| algorithm return value | computation output | wrap in `ComputationResult` |
| diagnostics dictionary | process finding input | evidence-linked `ProcessFinding` |
| OCEL flattening | object projection | preserve projection assumptions and lost context |
| OCEL consistency utility | relation-integrity computation | report invalid references instead of silently repairing |
| conversion fallback | explicit projection/conversion | record conversion path and semantic assumptions |

This mapping is preliminary. It identifies architectural relationships, not approved implementation decisions.

---

## 14. Unknowns Requiring Later Analysis

The following items cannot be established from the completed structural inspection alone:

- runtime performance of representative PM4Py operators;
- memory behavior on Schumpeter-scale OCEL data;
- deterministic behavior of every operator;
- thread and multiprocessing reproducibility;
- exact semantic differences between algorithm variants;
- stability of internal APIs across PM4Py releases;
- full treatment of malformed or dangling OCEL relations across all import formats;
- fitness of PM4Py OCEL projections for Schumpeter mission data;
- actual reuse value of specific algorithms for PIX v0.1;
- legal compatibility between AGPL PM4Py source reuse and the future PIX license;
- independently verified current test pass rate and coverage.

These values and judgments remain **unknown** until targeted analyses or experiments are performed.

---

## 15. Validity and Withdrawal Conditions

### 15.1 Validity

This analysis is valid for PM4Py commit:

```text
3329bbcbadce8764f7df660fd88636c30793fbd0
```

It should not be assumed to describe later upstream releases without comparison.

### 15.2 Withdrawal conditions

Reassess or withdraw the relevant claims if:

- PM4Py changes its primary package layout;
- the facade and algorithm dispatch mechanism is replaced;
- a uniform typed computation-result contract is introduced;
- OCEL becomes immutable or gains evidence-preserving integrity results;
- dependency enforcement reveals strict boundaries not visible in this inspection;
- runtime execution contradicts the traced call paths;
- PIX expands from a narrow audit engine into a general-purpose process-mining suite;
- PIX's licensing and distribution model makes direct PM4Py integration either clearly compatible or clearly incompatible;
- deeper algorithm-level analysis shows that a current preliminary adaptation judgment is false.

---

## 16. Final Assessment

**PM4Py is a broad, feature-oriented modular monolith whose dominant extension pattern is `public facade → algorithm dispatcher → variant implementation`. Its algorithm organization, conversion mechanisms, and object-centric processing provide valuable references for PIX, but its mutable data containers, open parameter dictionaries, heterogeneous results, implicit normalization, and non-strict dependency boundaries do not satisfy PIX's proposed evidence-first computation and intelligence contracts without substantial redesign.**
