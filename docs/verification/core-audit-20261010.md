# 2026-10-10 코어 구현 점검·실환경 검증

## 범위와 결론

공통 계약, 후보/source 격리, 독립 stage, train/validation/test 경계, 예산·실행 종료,
지표·사용량, 파일 registry, Dataset 준비 및 native/CVDP 연결을 소스와 회귀로 점검했다.
**코어 결함을 수정했고 CID004 Baseline의 실제 native inner 평가·outer 재평가가 통과했다.**
GEPA/Meta-Harness의 train은 모델 요청 timeout으로 무효였으며 성능 개선 검증은 완료하지 못했다.
Ubuntu x86_64 native loop, 다른 CID의 live, Ecdysis의 새 실모델 실행은 이번 범위에서 not_run이다.

작업 기준은 `origin/main`의 `fc42d29`, 브랜치는 `fix/core-audit-20261010`이다.
기본 디렉터리는 `main`을 유지하고 기존 변경을 보존했다.

## 확인된 결함과 수정

| 경계 | 재현한 문제 | 수정·회귀 근거 |
|---|---|---|
| Optimizer Context | 반환된 train 집계·history·validation의 nested metrics 수정이 내부 cache/선택을 바꿈 | 깊은 복사 반환; `test_core_integrity.py`에서 실제 runner·frozen selection 대조 |
| 독립 stage | 다른 stage에서 발급된 정상 후보를 `OptimizationResult`로 반환하면 채택됨 | 반환 후보도 해당 context 소속 검사; 평가 시작 전 거부 |
| 실행·평가 계약 | unknown 상태 및 `completed`+비정상 exit가 성공 후보로 연결됨 | Harness/Evaluator 반환 타입·상태 검사, 완료/exit 충돌 명시 실패 |
| 복수 그룹 | 정상 그룹과 선택 불가 그룹의 혼합 실행을 전체 선택 불가로 표시 | `partial`로 정상 그룹 결과 보존 |
| 수치 | 큰 유한값 평균의 중간 합 overflow, sum의 infinity, bool/string/초대형 int가 점수 또는 예외가 됨 | 유한 숫자만 집계/선택, 평균은 합산 전 나눔, overflow는 null |
| OpenCode usage | malformed nested event로 trace 처리가 중단되거나 비유한/음수 사용량을 기록 | 객체 형태·정수 토큰·유한 비음수 cost 확인; 전체 Agent usage는 계속 null |
| native snapshot | 직접 bridge 호출의 import가 pyc를 생성해 candidate hash를 변경 | snapshot import 동안 bytecode 억제, 기존 전역값 복구 |
| native 출력 | 수정 가능한 guidance에만 출력 형식 계약이 있어 candidate가 지우면 parser와 어긋남; Markdown 위반을 환경 오류로 분류 | trusted generator instruction에 형식 고정, 엄격 parser 유지, `agent_incomplete`/무효/null |
| native timeout | 개별 모델 요청 timeout을 전체 trial timeout으로 처리해 유효 0점으로 집계 | 요청 journal은 timeout, outer 잔여 시간이 있으면 sidecar api_error·실행 infrastructure_error |
| native Docker | worker의 격리 HOME이 호스트의 Docker context를 잃음 | 기존 DOCKER_CONFIG 또는 호스트 `.docker` 경로를 환경으로 보존 |
| CVDP driver | 네트워크 생성 실패가 driver stderr에만 있고 공식 `result=1/error_msg=null`·exit 0이어서 오답으로 분류 | 소유한 driver stdout/stderr와 private test log의 Docker-specific 오류를 infrastructure_error/null로 판정 |

신뢰한 local/in-process 플러그인의 계약 보호이며 OS sandbox를 추가한 것은 아니다.
원본 Agent·private 평가 기준·source/data SHA와 모델 기본값은 바꾸지 않았다.

## 로컬 검증

환경: macOS arm64, Python 3.12.12, 고정 `uv.lock`의 dev/native extra.

```bash
uv sync --frozen --extra dev --extra native
make test
make lint
make demo
.venv/bin/python -m build
.venv/bin/python tests/test_installed_cli.py dist/agent_optimizer-0.3.0-py3-none-any.whl
git diff --check
```

- 기준 suite: 1,204개 중 실행 1,124 통과·80 skip(기존 코어-only 환경).
- 최종 suite: **1,220개 중 실행 1,142 통과·78 skip**, 184.636초. 신규 테스트 16개이며 native extra 유무에 따른 기존 skip 차이는 신규 성공으로 세지 않는다.
- lint·합성 7-trial demo `20261010T063206Z-393b0346`·최신 sdist→wheel build·소스 밖 설치형 CLI 계약·diff whitespace 검사 통과.
- 설치형 검사는 합성 사용자 Agent/평가기 실행 및 목록/설정/진단 계약이다. 설치형 native 실모델 성공으로 확대하지 않는다.
- 독립 읽기 전용 리뷰: Critical/Important 0건. 직접 실행한 코어/adapter/native 43개와 플러그인/연구 31개, 총 74개 통과.

## 실제 native 실행 조건과 재현

이전 CID004 프리셋의 명시 선택을 사용했다:
validation `cvdp_copilot_8x3_priority_encoder_0013`, 연구 train `cvdp_copilot_64b66b_encoder_0009`.
Baseline은 validation 1개·최대 1 trial, GEPA/Meta는 독립 1 iteration·최대 4 trials다.
outer trial 240초·wall 1200초·native inner 최대 3 iteration·evaluator 120초·final_test=false.
후속 독립 실행은 native `llm_timeout=120`이며 Optimizer 요청 상한은 60초다.

- ACE `fead921f18bb57345b5a41ef93ba625be208e99c` / CVDP `8e894cf74414ab1eaea1e2b4e80a02f123df07b6`.
- HF revision `5b807d945f6a99aa645f7e43a64a2115e281b4bf`의 고정 no-commercial JSONL, hash는 [SOURCES](../SOURCES.md) 그대로다.
- 작업 `.venv` native Python과 별도 기존 `external/cvdp-venv` driver, Docker Linux aarch64 daemon·호스트 `colima` context.
- 이미지 `agent-optimizer-cvdp-eval:8e894cf-arm64`, ID `sha256:ee167c7cd486111a2a807a703ae6bbb30debf2d26f5bb9d0d760ec07c96a58ec`.
- 모델 `deepseek-flash`, URL·키는 검증 자식 환경에만 제공. 앱의 `.env` 자동 로딩 기능을 추가하지 않았다.

실제 실행은 임시 검증 driver가 제품 CLI `init` → `prepare --offline` → `doctor --plan --json`
→ `run`을 호출했다. 원본 stdout JSON은 캡처해 상태만 출력했다.
초기 명령은 `PYTHONPATH=src .venv/bin/python -B /.../opencode/verify_core_audit_native.py`이며,
후속은 `PYTHONPATH=src .venv/bin/python -B /.../opencode/replay_core_audit_native.py CONFIG...`였다.
생성 설정과 실제 run은 작업 워크트리의 `runs/core-audit-native-home/`에 보존한다.

동일 조건 재현은 [NATIVE §2](../../examples/ace-rtl/NATIVE.md#2-명시-선택preparedoctor)의 전체 init 명령에
`--cid cid004`와 위 rows, 준비된 실제 경로, `--max-wall-time-seconds 1200 --trial-timeout-seconds 240`을 지정한다.
연구는 `--optimizer-config '{"gepa":{"iterations":1,"request_timeout_seconds":60}}'`
또는 Meta-Harness ID로 같은 옵션을 지정한다. 생성 `harness.toml`의 `[native].llm_timeout`을
명시적으로 120으로 바꾼 뒤 `prepare`·`doctor`·`run`을 실행한다. 이는 기존 기본 60초를 바꾼 독립 실험이다.

## 수정 후 최종 실실행 결과

| run ID | 결과 | 실제 평가·제약 |
|---|---|---|
| `20261010T064520Z-3a3d312a` Baseline | **completed, 1/1 trial, validation 1.0** | generator 1회, inner 공식 raw 통과 1건, outer 공식 raw 재평가 통과 1건, 동일 제출 target/hash·실 cleanup journal |
| `20261010T064558Z-ad651a75` GEPA | completed, 4/4 trial, Baseline 선택 | Baseline/후보 validation의 inner/outer 각 1.0 동점. train 2건은 모델 120초 timeout·infrastructure_error·valid=false·null, 공식 train raw 없음. 후보 guidance 변경과 소비 해시는 확인했으나 정상 train 최적화·개선 근거가 아님 |
| `20261010T065151Z-e7898926` Meta-Harness | error, 2/4 trial, 선택 없음 | Baseline validation inner/outer 1.0, train 모델 120초 timeout·무효/null. Optimizer 제안도 60초 timeout으로 중단; 코드 후보 생성/평가·성능 향상은 미검증 |

마지막 실제 실행의 native cleanup journal은 completed였으며,
`docker ps --filter name=agent-opt` 및 `docker network ls --filter name=agent-opt-cvdp`에서 남은 항목이 없었다.
호스트 전체 프로세스·임의 network 정리의 보장은 아니다.
Agent usage는 partial/unreported, 전체 토큰/비용은 null이며 test는 실행하지 않았다.

### 조사 중 이전 실행 보존

- `20261010T062007Z-1429741f`: Baseline 선택 없음.
- `20261010T062112Z-d2abbcd5`: 당시 GEPA completed였지만 Baseline 모델 timeout이 유효 0점으로 잘못 분류됐다. 후보 outer raw 1.0과 별개로 **0→1 개선 근거는 폐기**한다.
- `20261010T062736Z-5ff59e91`: Meta-Harness 무효 validation으로 오류.
- `20261010T063202Z-eb0f7788`: outer raw 1.0이지만 inner 3건은 worker Docker 연결 실패였다. native inner 정상 성공으로 표현하지 않는다.
- `20261010T063348Z-abbfd0f8`: 검증 도구의 600초 상한으로 부모 실행이 종료되어 최종 summary/frozen selection이 없다. 완료/선택 근거로 사용하지 않는다. 후속 명령은 더 긴 도구 상한으로 새 run을 실행했다.

## 남은 검증

1. 선택한 train의 정상 응답·공식 평가를 확보한 뒤 연구 stage의 같은 조건 반복 비교 및 선택 고정 후 test.
2. Meta-Harness의 실제 후보 Python 생성·소비·평가 완료. 모델 timeout을 fixture/다른 모델 성공으로 대체하지 않는다.
3. Ubuntu x86_64 native loop: 현재 로컬은 Mac/ARM64 daemon으로 실행 조건이 다르다. PR 코어 CI와 실모델 native 검증을 구별한다.
4. 추가 CID/row 범위, 설치형 native 실모델, Ecdysis의 새 실모델 실행, 일반화 성능은 이번 성공으로 주장하지 않는다.
