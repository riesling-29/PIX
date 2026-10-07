# MODEL·W4 추가 구현 대조표

작성 기준일: 2026-09-17, 통합 정리일: 2026-09-18.

[implementation_registry.json](implementation_registry.json)은 이번 모델 확장과 W4 계산을 기존 [SCOPE-01](../scope-01/replacement_registry.json), [개발 플랜](../2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md)에 연결한다. [2026-09-15 union 기록](../union-2026-09-15/implementation_registry.json)은 당시의 스냅샷으로 유지한다. 기존 기록의 source hash를 이번 코드의 hash로 덮어쓰지 않는다.

25개 packet은 **구현·검토 단위**다. 서로 같은 원본 행을 참조할 수 있으므로 알고리즘 개수나 전체 완료율로 읽으면 안 된다. `delivery=existing_native`인 5개 packet은 기존 구현을 W4에 연결한 것이며, 이번에 새로 작성했다는 의미가 아니다. 각 packet에 실제 정의가 있는 API, 코드, 테스트 경로, 지원 프로파일, 원본 행과의 대응 범위, 한계, 반증 조건을 적었다.

| 묶음 | 이번 대조표가 구분하는 계산 |
|---|---|
| 모델 | capability·label, reset/inhibitor·stochastic, PNML/PTML/BPMN, POWL→tree, transition-bordered tree→PN, trie→PN, maximal decomposition, coverability, OC subprocess |
| 발견 | 기존 기본값을 보존하는 명시적 strict optional-block IM/IMf/IMd |
| FEAT | 관측 cutoff·검열 target·누출 방지 분할, OC k-step·역변환·회귀, held-out decision 평가, drift 다중검정, 기존 clustering·언어 거리 |
| SIM | 기존 유한 playout·tree 생성, OC binding playout, 동시 timed PN, 자원 calendar·what-if·관측 duration 학습 |
| STREAM | 정정 가능한 case DFG, OC execution merge/split, 기존 ordered monitor·online alignment |
| ACT | 모든 pattern witness, bounded 계획, replay 기반 운영 모집단, 기존 구조·관측 성능·configuration 계산 |

이 파일은 **구조적 추적성**을 기록한다. `reference_replacement_verified=false`, `domain_review_status=not_yet_reviewed`이며 PM4Py/OCPA의 모든 variant 대체나 사용자의 도메인 승인을 선언하지 않는다. API가 존재한다는 확인과 계산이 맞다는 검증은 구분한다. 실제 테스트 실행 결과와 손계산 예시는 [구현 보고서](../../reports/2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md)와 [통합 예제](../../../examples/models_w4_review.py), [통합 테스트](../../../tests/test_models_w4_integration.py)에서 확인한다.

## 검사와 최종 hash 기록

저장소 루트에서 정상 동작하는 Python으로 실행한다.

```text
python tools/check_models_w4_registry.py --self-test
python tools/check_models_w4_registry.py --freeze-hashes --self-test
python tools/check_models_w4_registry.py --strict-hashes --self-test
```

첫 명령은 경로, 구체적인 AST 정의, SCOPE/plan ID, 중복, 과도한 승인 주장, 제한·반증 조건을 검사한다. self-test는 잘못된 승인·중복·없는 API·경로 이탈 등을 의도적으로 넣었을 때 거부되는지 확인한다. 계산 알고리즘 테스트는 실행하지 않는다.

두 번째 명령은 **모든 코드·테스트 수정이 끝난 뒤** source/test 및 공유 registry·codec·통합 예제의 현재 SHA-256을 기록한다. 마지막 명령은 이 스냅샷과 파일 내용이 일치하는지 확인한다. hash는 파일 식별 근거이며 정확성·참조 동등성의 증거가 아니다. 미동결 상태에서 strict 검사는 실패해야 정상이다. 수정 후에는 필요한 계산 검증을 다시 수행하고 의도적으로 스냅샷을 갱신한다.

판단의 유효 범위는 기록된 파일 버전과 명시한 프로파일이다. 각 packet의 반증 조건이 재현되면 해당 지원·보존 주장을 철회하고 수정한다. 이후 upstream 버전과의 호환성, 대형 외부 corpus의 성공률, 실운영 처리량과 예측 정확도는 이 대조표로 알 수 없다.
