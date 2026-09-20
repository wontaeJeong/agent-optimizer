# 팀 Optimizer 연결 템플릿

이 디렉터리를 복사해 팀 구현을 연결하세요. `optimizer.py:Optimizer`는 공통
`contracts.py`의 `optimize(context, seeds, config) -> OptimizationResult` 슬롯입니다.
현재는 **항상 `UnavailableError`**를 내며 Meta-Harness 알고리즘을 구현하지 않습니다.
예제는 예약 이름 `meta_harness`를 파일 플러그인으로 명시적으로 대체하는 방법을 보여줍니다.
다른 알고리즘도 같은 계약을 사용하며 서로의 구현을 직접 호출하지 않습니다.

프로젝트 루트에서:

```bash
PYTHONPATH=src python3 -m agent_optimizer plan experiments/optimizer-template/experiment.toml
PYTHONPATH=src python3 -m agent_optimizer run experiments/optimizer-template/experiment.toml
```

`plan`은 설정/등록 검사로 exit 0, `valid=true`, `integrations_ready=true`를 반환합니다.
구현 완료를 뜻하지 않습니다. `run`은 최소 예제의 합성 baseline을 평가한 뒤 팀 슬롯에서
**exit 2**로 실패합니다. `summary.json`에는 `status="error"`, `error_type="UnavailableError"`를
남기며 후보 선택과 final test는 수행하지 않습니다. 외부 Agent·모델·시뮬레이터는 필요 없습니다.
실행 가능한 파일 변경 계약 예제는 `examples/minimal/experiment.toml`의 `file_variants`입니다.

## Meta-Harness 담당자가 연결할 지점

아래는 **이 프로젝트의 연결 계약**입니다. upstream API나 논문 재현 절차가 아닙니다.
채택할 논문/공식 구현/고정 버전은 [출처 문서](../../docs/SOURCES.md)의 미확정 항목을 먼저 확인하세요.

| 팀 구현 책임 | 로컬 연결 지점 |
|---|---|
| 프롬프트·설정·코드·실행 흐름의 텍스트 변경 제안 | `context.propose(parent, {"relative/file": "new content"}, producer)`로 새 후보를 생성. 부모는 전달받은 seed 또는 이 context가 발급한 후보. Agent manifest의 `editable` 범위만 가능하며 원본/스냅샷을 직접 수정하지 않음. |
| 탐색 평가와 피드백 | `context.evaluate(candidate)`가 반환하는 train 집계와 `context.history()`의 train trial `metrics`/`feedback`을 사용. split 인자는 없으며 train이 없으면 명시적 오류. validation/test 파일·점수에 접근하지 않음. |
| Optimizer 자체 모델 사용량 | 호출마다 `context.record_usage(input_tokens, output_tokens, cost_usd)`로 보고. 토큰은 관측한 비음수 정수, 비용 미수집은 `None`. Agent 사용량과 별도이며 호출 즉시 이벤트에 저장됨. 미보고를 0으로 해석하지 않음. |
| 반환 후보와 체크포인트 메타데이터 | `OptimizationResult(candidates=[candidate], checkpoint={"iteration": 1, "parent": parent.id})`. JSON 직렬화 가능한 작은 메타데이터만 저장. 채택 버전/탐색 설정 등 재현 정보를 추가하되 인증정보나 비공개 평가 데이터는 넣지 않음. checkpoint 저장은 resume 기능이 아님. |

runner가 validation 선택, stage 연결, 선택 고정 이후 test를 소유합니다.
플러그인은 신뢰한 in-process 코드이며 train-only 공개 인터페이스는 OS 보안 격리가 아닙니다.
미지원 기능·누락된 입력은 오류로 처리하고 baseline/합성 평가로 자동 대체하지 마세요.

## 파일 의존성과 테스트

팀 코드가 `helpers.py`를 사용한다면, 복사한 experiment에 등록 이름과 프로젝트 상대 경로로 선언하세요:

```toml
[plugin_dependencies]
"optimizers/meta_harness" = ["experiments/my-team/helpers.py"]
```

기존 `[plugins.optimizers]`의 경로도 복사한 팀 파일로 변경해야 합니다.
의존성 선언은 hash 기록용이며 import 경로나 패키지 설치를 대신하지 않습니다.
직접 등록 파일과 선언 파일만 manifest의 `plugin_sha256`에 기록합니다. 자동 import 탐색은 없습니다.
설치 패키지·외부 모델/환경의 버전 고정은 담당자가 별도로 기록하세요.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_plugin_contracts.py -v
```

계약 테스트는 in-memory 팀 Optimizer로 train 피드백·후보 생성·사용량·checkpoint 저장,
runner의 validation/test 분리를 확인합니다. 외부 파일 플러그인의 예약 슬롯 대체,
템플릿의 예상 실패, 의존성 hash 변경/잘못된 선언 거부도 확인합니다.
이는 합성 계약 검증이며 실제 연구 알고리즘·외부 모델 통합이나 성능 개선의 근거가 아닙니다.
