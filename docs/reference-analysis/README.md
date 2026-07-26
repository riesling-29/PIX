# Reference Analysis

Reference analysis follows this workflow:

```text
PM4Py analysis
→ OCPA analysis
→ comparison
→ PIX adoption decisions
→ PIX implementation planning
```

Every candidate must receive one of these decision classifications:

- `DIRECT DEPENDENCY CANDIDATE`
- `CONCEPTUAL REUSE`
- `INDEPENDENT REIMPLEMENTATION`
- `REFERENCE ONLY`
- `REJECT`
- `DEFER`
- `UNRESOLVED`

Every conclusion must identify:

- the inspected repository;
- its branch, tag, or commit SHA;
- the analysis date;
- observed evidence;
- relevance to PIX;
- counterarguments;
- withdrawal conditions.

Analysis documents establish a review record. They do not prove that PIX functionality has been implemented.
