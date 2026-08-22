# PIX OCEL Canonical V1

- Status: implemented identity specification
- Canonical identifier: `pix.ocel.canonical.v1`
- Digest algorithm: SHA-256
- Interchange status: internal only; not an OCEL 2.0 file format

## Purpose

Canonical V1 assigns the same byte representation and content digest to
semantically identical, valid PIX OCEL datasets regardless of input collection
order or timezone representation of the same instant.

Source paths, source bytes, provenance, import warnings, transformations, and
validation reports are not part of canonical dataset identity. Import results
record that evidence separately.

## Eligibility

Only an `OCEL` that passes the current PIX semantic validator receives
canonical bytes or a canonical digest. An invalid candidate remains available
through its build or import result but has no canonical identity.

The empty OCEL is valid and has canonical identity. Events and objects that do
not participate in a relation are valid and remain part of canonical identity.

## Normalization

Canonical V1 performs only the representation normalization already owned by
`pix.ocel.build`:

- materialize immutable tuples;
- represent timezone-aware datetimes as UTC;
- deterministically order nested and root collections;
- preserve identifiers, qualifiers, strings, values, duplicates, and records
  without trimming, coercion, inference, merging, repair, or removal.

Semantic validation rejects invalid candidates after deterministic
construction. The serializer does not repair them.

## Primitive value representation

Every attribute value is represented by an explicit type and value pair.

| PIX value | Canonical type | Canonical value |
|---|---|---|
| `str` | `string` | original string |
| aware `datetime` | `time` | UTC ISO 8601 with six fractional digits and `Z` |
| `int` | `integer` | base-10 string |
| `float` | `float` | Python hexadecimal float representation |
| `bool` | `boolean` | JSON boolean |

Strings receive no trimming, case conversion, or Unicode normalization.
Finite floats only are admitted by the canonical model. The hexadecimal float
representation preserves the exact admitted binary value, including signed
zero.

## Byte encoding

The canonical document is JSON encoded with these fixed settings:

```text
encoding        UTF-8 without BOM
ensure_ascii    false
allow_nan       false
sort_keys       true
separators      comma and colon without surrounding whitespace
final newline   absent
```

The top-level document contains these logical members:

```text
format = "pix.ocel.canonical"
version = 1
eventTypes
objectTypes
events
objects
e2o
o2o
```

The exact byte representation is fixed by the implementation and golden
vectors under `tests/ocel/golden/canonical_v1/`.

## Digest

The digest is SHA-256 over the exact canonical bytes. It is exposed with its
canonical version and algorithm:

```text
pix.ocel.canonical.v1:sha256:<lowercase-hexadecimal-digest>
```

The package version and canonical version are independent. Package releases
must never silently change Canonical V1 bytes. A byte-level rule change requires
a new canonical version and new golden vectors.

## Reconsideration conditions

Canonical V1 must be superseded rather than edited if the canonical model adds
another primitive value family, changes identity semantics, includes source
provenance in dataset identity, or changes datetime, string, float, or
collection normalization.
