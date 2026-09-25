# MVP 기본 경로와 연구 탐색 경계 정리

## 목적과 근거

저장소 설계 검토 결과, 기본 `init`이 `--optimizer` 없이 GEPA를 선택하는 반면 대화형 wizard는 선택을 요구한다. 이는 모델 설정과 연구 탐색 비용을 사용자가 선택하지 않은 기본 경로에 도입한다. GEPA의 선택형 `merge`는 validation 수치 벡터를 모델의 변경 제안에 전달해 train 전용 mutation 근거 규칙과 충돌한다. 또한 stage 문맥의 일반 `evaluate`와 `propose`는 다른 stage 후보를 검사하지 않아 `evaluate_batch`/`evaluate_validation`과 경계가 다르다.

## 설계

1. 비대화형 `agent-opt init`은 `--optimizer`를 최소 하나 명시해야 한다. 검사 위치는 데이터셋 준비 전으로, 누락 시 선택 방법을 알리는 설정 오류로 종료한다. `baseline`, `file_variants`, 팀 파일 Optimizer, 세 연구 Optimizer는 명시적으로 선택할 수 있다. wizard는 이미 명시적 선택을 요구하므로 선택 흐름을 유지한다.
2. GEPA의 `merge=true`는 Optimizer가 train/validation 평가나 모델 호출을 시작하기 전에 명시적 미지원 오류로 거부한다. `merge` 구현 자체는 삭제하지 않고 보존하며, 기본 탐색과 `merge=false`는 기존대로 실행한다. 재활성화 조건은 모델에 전달하는 수정 근거가 train에 한정되고 해당 경계를 검증하는 테스트를 갖추는 것이다.
3. `Context.propose`의 부모와 `Context.evaluate`의 후보는 해당 stage가 발급받은 baseline 또는 자기 stage의 후보만 허용한다. 다른 stage의 후보는 평가·생성 전에 설정 오류로 거부하고, 공유 baseline 평가 캐시와 그룹별 최종 validation 선택은 유지한다.
4. README와 현재 상태·확장 안내에서 암묵적 Optimizer 선택 및 GEPA 병합의 활성 여부를 실제 경로와 일치시킨다. 과거 설계·검증 근거는 소급 수정하지 않는다.

## 검증

- `init --optimizer` 누락이 데이터셋 준비·설정 파일 생성 전에 실패하는지, 명시적 `baseline` 생성이 성공하는지 검사한다.
- `merge=true`가 모델 호출·평가 전에 실패하고 기본 GEPA 탐색이 계속 작동하는지 검사한다.
- stage A에서 생성된 후보를 stage B의 `propose`/`evaluate`에 건네는 시도를 거부하고 baseline 및 자기 후보를 허용하는지 검사한다.
- 관련 계약·연구·CLI 회귀, 전체 unittest, 최소 데모, lint를 실행한다. 외부 모델/도구의 실환경 성능은 이 변경의 검증 범위가 아니다.
