# MVP 첫 실행·복구 경로 명확화

## 목적과 범위

최신 `origin/main`의 기존 CLI·TUI·개발 명령을 통해 준비 범위, 입력, 실제 실행 근거와 다음 행동을 알 수 있게 한다. 새 프레임워크·상태 저장소·자동 데이터셋 추천·평가 대체는 만들지 않는다. 코어의 원본/후보/평가 격리와 train/validation/test 계약, JSON 키·종료 코드·기존 명령을 유지한다.

## 확인한 마찰과 재현 근거

| 흐름 | 실제 명령·관찰 | 수정 대상 |
|---|---|---|
| 새 개발자 | `make setup-core`가 `.venv` 준비·코어 진단 후 7-trial 합성 실행을 자동으로 수행하고 `runs/<id>/report.html`을 생성했다. `make test`는 687개 중 672개 통과, 15개 환경 의존 검사 skip. setup의 마지막 JSON은 `results: runs/`까지만 가리킨다. | 첫 결과 경로와 합성/실평가 차이 안내 |
| Agent 사용자 | `agent-opt init --agent ... --editable ... --dataset examples/minimal/tasks.json --evaluator ... --optimizer baseline --yes` → `doctor --plan` → `plan` → `run`에서 2-trial 합성 결과가 생성되었다. `doctor --plan`은 정적 준비를 확인하지만 Agent/평가기의 실행은 하지 않는다. `run` JSON에는 `run_dir`만 있고 TUI의 `report_html`과 다르다. `report RUN`은 전체 summary JSON만 출력한다. | CLI 후속 명령·보고서 위치, 진단 범위 표기 |
| 마법사 | 빈 editable 뒤 확인하면 `editable[0]`에서 `IndexError`; Optimizer 0은 음수 인덱스로 마지막 ID를 선택한다. `-1`도 뒤에서 선택되며, 범위 밖 번호만 오류다. 번호 목록에는 실행 의존성 설명이 없고 확인 화면에는 예산·예상 경로가 없다. | 사전 검증, 선택 설명, 실행 전 확인 |
| 팀 개발자 | `experiments/<team>/` 템플릿은 fixture를 이용하는 계약 검사를 제공한다. 등록된 `sample_text`/`sample_command`/`sample_baseline`의 `init` → 정적 `doctor --plan` → 2-trial 실행을 확인했다. 템플릿의 stub은 실제 연결 전 명시적 실패이며, Dataset 템플릿 안내는 다른 안내와 언어가 다르다. | fixture와 실환경 검증의 분리, 템플릿 안내 정돈 |
| 선택적 ACE | Docker daemon은 사용 가능하지만 현재 워크트리에는 고정 ACE/CVDP 자산이 없다. `doctor --plan examples/ace-rtl/experiment.toml --json`은 `ready=false`, `doctor --dataset cvdp --json`은 10개 준비 부족, `make smoke`는 `blocked`/exit 2다. 모델·공식 평가는 실행하지 않았다. | 자산 준비·정적/실평가 성공 의미와 복구 명령 |
| 개발 명령 | `make doctor ARGS='--core; touch …'`가 진단 이후 추가 명령을 실제 실행했다. `sh scripts/bootstrap.sh doctor --help`는 doctor 전용이 아닌 전체 도움말이다. CI wheel 경로와 CONTRIBUTING은 `0.3.0`을 고정하며, 참조처 없는 `scripts/run_demo.sh`는 `.venv` 대신 시스템 Python을 사용한다. `docs/status.md`의 보고서 버전 v2는 현재 v3 구현과 다르다. | 셸 주입 방지·도움말·wheel 선택·문서 |

## 설계

### 사용자 CLI와 TUI

- `setup_wizard.py`에서 이름·Agent·editable 비어 있음, 데이터셋 숫자(0/음수/범위 밖), Optimizer 번호와 하네스 번호를 준비/실행 전 검사한다. 로컬 데이터셋 경로 입력은 그대로 허용하지만 숫자로 보이는 잘못된 번호를 파일 경로로 해석하지 않는다. 취소/EOF는 기존 종료 코드 및 자산 미생성을 유지한다.
- 등록 목록의 각 항목 옆에 실제 조건을 짧게 표시한다. CVDP/Verilog-Eval의 고정 자산·Docker, `sample_text`/`fixture`의 합성 성격, `command`의 사용자 실행 argv, `opencode`/`claude_code`의 외부 도구·모델 설정, GEPA/Meta-Harness/Ecdysis의 모델 API·train 과제·수정 파일 조건, 팀 플러그인의 별도 문서를 구분한다. 목록은 등록된 ID만 보여주며 추천하지 않는다.
- 확인 화면은 선택한 입력, 준비될 자산·다운로드/도구/모델 호출 가능성, `init` 기본 `max_tasks=9`, `max_trials=max(80, 필요한 예약치)`, 시간 3600초·trial 120초, `runs/configs/<name>/...`의 설정과 `runs/<run-id>/report.html` 또는 session별 보고서 예상 위치를 표시한다. 계산할 수 없는 실행 비용·성공·실측 trial 수는 단정하지 않는다.
- TUI의 기존 실험 분기에만 프로젝트의 `runs/configs/**/experiment.toml` 최근 수정 설정을 최대 몇 개 보여주고 번호 또는 명시적 경로를 받는다. 읽기 범위를 프로젝트 내부의 정상 파일로 제한하고 사라진 파일을 무시한다. 예제/외부 임의 경로와 기존 ACE 분기는 직접 입력을 유지한다. 저장 DB나 이력 화면은 만들지 않는다.
- 조사 중 `origin/main`에 새로 합류한 TUI 4번 **이전 실행 보고서 보기**는 결과 요약·HTML을 열람하는 읽기 전용 기능이다. 1번의 최근 **실험 설정을 다시 실행**하는 선택과 목적이 다르므로 4번의 안전한 실행 기록 검사·정렬을 참고하되 기능을 복제하거나 수정하지 않는다.
- `init`, `run`, `run-session`, `report`의 stdout은 기존 단일 JSON과 기존 필드를 보존한다. 읽기 쉬운 후속 명령을 stderr에 추가하고 `run`의 JSON에는 기존 TUI와 같은 `report_html`을 추가한다. `report` 기본 출력은 summary 그대로 두고 HTML 위치와 재생성 명령만 별도로 안내한다. `plan`, `doctor --plan`은 정적 검사, `doctor --model`은 명시적 모델 연결 probe, demo는 합성, smoke는 공식 정답/오답 도구 검사, 실제 run은 저장된 평가 근거로 확인한다는 안내를 실제 검사 범위에 맞춰 넣는다.

### 개발 명령·패키징

- Makefile은 `ARGS`를 recipe의 명령 텍스트로 직접 펼치지 않는다. 안전하게 인용한 한 인수로 bootstrap에 전달하고, bootstrap은 허용한 옵션용 공백/짝지은 따옴표 인수 구문을 **평가 없이** 분리한다. 미지원 셸 연산/깨진 인용은 도구 준비 전에 오류로 종료한다. 기존 `ARGS='--dataset verilog-spec --json'`, `ARGS='--platform "linux/arm64"'`, `--core` 같은 정상 옵션을 동일하게 전달한다. 변수의 중첩 Make 확장도 명령으로 실행하지 않는다.
- bootstrap의 명령별 `--help`는 Python/설치/도구 조회 없이 옵션·허용 조합·부작용·결과 위치를 표시한다. dev.py의 argparse 도움말도 같은 뜻으로 유지한다. `setup`만 의존성 설치와 선택 자산 준비를 수행하며 인수 없는 `setup`/`doctor`의 ACE 전체 의미는 바꾸지 않는다. `doctor --json` stdout은 단일 JSON이다.
- `scripts/run_demo.sh`는 기존 호환 진입점을 유지하되 `.venv`에서 실행하고 코어 준비 복구를 알려준다. CI는 `dist/`에서 **현재 pyproject 버전의 wheel 정확히 한 개**를 확인하고 그 파일을 독립 설치 검사에 넘긴다. CONTRIBUTING의 직접 검증 예도 같은 방법을 사용한다.

### 문서와 검증

- README: 5분 코어 실행과 자동 생성된 HTML 찾기. CONTRIBUTING: 변경 종류별 검증. `docs/development.md`: bootstrap/Make/dev.py의 정확한 역할·옵션·복구. `AGENTS.md`: 최신 에이전트 개발 경로/제품 안전 경계. `docs/status.md`·`docs/FUTURE.md`: 구현 v3와 미검증/보류. website: 사용자 선택·첫 실행·결과 의미. 같은 긴 명령 설명은 development 한 곳에 두고 다른 문서는 링크한다.
- 회귀 테스트는 `tests/test_cli_experience.py`, `tests/test_dev_onboarding.py`, 관련 TUI·패키징 검사에 필요한 만큼 추가한다. 잘못된 입력이 준비 호출 전에 차단되는지, 취소가 쓰기 전 종료인지, 선택 부재/모델 설정 부재가 실제 성공으로 둔갑하지 않는지, 기존 JSON·종료 코드·정상 ARGS 전달 및 셸 주입 차단을 검증한다. 팀 fixture와 선택형 ACE 차단을 각각 관찰한다.
- 변경 후 네 사용자 흐름을 가능한 범위에서 재실행하고 `make lint`, `make test`, `make demo`, `git diff --check`, website 변경 시 `npm ci && npm run build`를 실행한다. Docker 자산·외부 모델·공식 평가가 준비되지 않으면 미실행으로 기록한다. UI 변경 PR에는 변경 전후 텍스트/화면 캡처와 재현 명령을 포함한다.

## 제외와 결정

전체 화면 이력, 범용 설정 생성기, 플러그인 자동 발견, scheduler/resume, native ACE 및 보류 연구 기능은 추가하지 않는다. 최근 설정은 사용자가 승인한 대로 프로젝트가 생성한 설정만 대상으로 한다. 명시적 경로는 언제나 사용 가능하다. 기록이 없는 곳에서 실제 비용, 모델 응답 또는 외부 평가 성공을 추정하지 않는다.

## 최신 main 합류 후 실행 경로

작업 중 `origin/main`에 개발 명령 개편이 합류했다. 최종 구현은 그 변경의
`scripts/make_args.sh`에 안전한 인수 분리를 적용하고, `scripts/select_wheel.py`에서 빌드 결과의
현재 버전·wheel 메타데이터를 검사한다. 참조처 없는 `scripts/run_demo.sh`는 해당 main에서
삭제되었으므로 복원하지 않는다. 검증된 합성 데모 진입점은 `make demo`다.
