<!-- 한국어 버전 -->

# 참조 분석

참고 분석은 이 작업 흐름을 따르고 있습니다.

```text
PM4Py analysis
→ OCPA analysis
→ comparison
→ PIX adoption decisions
→ PIX implementation planning
```

모든 지원자는 다음과 같은 결정 분류 중 하나를 받아야 합니다.

- `DIRECT DEPENDENCY CANDIDATE`
- `CONCEPTUAL REUSE`
- `INDEPENDENT REIMPLEMENTATION`
- `REFERENCE ONLY`
- `REJECT`
- `DEFER`
- `UNRESOLVED`

모든 결론은 다음과 같은 것을 확인해야 합니다.

- 검사된 저장소;
- 그 지점, 태그 또는 SHA의 위탁;
- 분석 날짜
- 관찰된 증거;
- PIX에 대한 관련성
- 반론
- 철수 조건

분석 문서들은 검토 기록을 수립한다. 그들은 PIX 기능이 구현되었다는 것을 증명하지 않습니다.

---

<!-- English version -->

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
