# 장시간 명령 진행 표시 전수 보완 설계

## 목표와 조사 범위

모델·Docker·다운로드 작업 중 사용자가 **현재 단계와 경과 시간**을 볼 수 있어야 한다. TTY에서는 기존 Rich spinner와 단조 증가 경과 시간을 갱신하고, 출력 리다이렉트 시에는 단계별 시작·완료 또는 실패를 줄 단위로 남긴다. 진도를 모르면 백분율·ETA를 추측하지 않는다. 진행 메시지는 stderr에 두고 JSON 결과가 나오는 stdout은 단일 문서로 유지한다. 평가 결과나 실행 이벤트의 의미는 바꾸지 않는다.

| 사용자 경로 | 조사 결과 | 보완 |
|---|---|---|
| `make live`, 메뉴 5번 | `examples/ace-rtl/environment/checks.py:live`가 이벤트 callback 없이 runner를 호출한다. 현재 두 실제 실행에서 `events.jsonl`에는 `agent_started`가 기록됐지만 터미널은 비어 있었다. | 준비 상태를 먼저 표시하고, 기존 `ProgressDisplay`에 예산과 runner 이벤트를 전달한다. |
| `make smoke` | 실제 도구 9개·toy 3개·공식 CVDP 2개를 순차 평가하나 마지막 JSON 전에는 상태가 없다. | 검사의 시작·경과·종료를 stderr에 표시하고 기존 최종 JSON/summary를 유지한다. |
| `make setup --core` 및 전체 `make setup`, 메뉴 1·7번 | 단계의 시작·끝과 로그 경로는 보이나 셸의 uv 동기화, 다운로드·이미지 빌드 등 긴 단계 중 경과가 갱신되지 않는다. | Python 준비 전 POSIX 셸 경과 표시, 이후 기존 단계 메시지와 함께 Python 상태 표시를 사용한다. |
| `make setup --dataset ID` | provider의 `prepare()`와 최종 doctor가 무출력으로 오래 걸릴 수 있다. | provider 선택과 진단 단계를 구분해 표시한다. |
| `make doctor`의 전체/선택 데이터셋 검사, `--model`, 메뉴 2·4번 | 수집 중 결과까지 대기하며, 특히 host API·Docker 도구 호출은 최대 수십~백여 초 걸릴 수 있다. | 읽기 전용 진단과 모델의 호스트/컨테이너 각 단계를 표시한다. `--json`도 stdout에는 JSON 하나만 쓴다. |
| `agent-opt doctor --dataset ID` / `--plan PATH --model`; `agent-opt report RUN --html` / `--csv` | 선택 provider 진단·모델 probe 또는 대형 보고서 재생성/CSV 출력 중 상태가 없다. | 호출 경계에서 진행 상태를 표시한다. |
| `agent-opt run`, `run-session`, TUI, `init`/`datasets prepare`, `make demo` | 이벤트 기반 `ProgressDisplay` 또는 데이터셋 `PreparationStatus`가 이미 연결됐다. | 이 경로의 기존 동작을 회귀로 확인한다. |

짧고 즉시 끝나는 `help`, `lint`, 일반적인 목록·정적 검증은 작업 단위가 없어 별도 spinner를 만들지 않는다. `make test`는 테스트 러너 자체 출력을 계속 보여준다.

## 구조와 출력 계약

- `src/agent_optimizer/terminal_report.py`의 기존 상태 표시를 단계 종류와 이름에 맞게 재사용한다. TTY의 표시를 끝낼 때 마지막 단계·결과를 남기고, 비TTY에서는 시작/끝 한 쌍을 stderr에 기록한다. 실제 성공·실패·중단과 상태 문자열을 일치시키며 민감한 명령 인수·모델 요청 본문·private 평가 데이터는 표시하지 않는다.
- 실행 이벤트가 이미 있는 ACE `live`는 새 이벤트나 별도 watcher를 만들지 않고 `run_experiment(..., on_event=ProgressDisplay)`로 연결한다. 긴 Agent 호출 중에는 현재 `agent_started` 단계의 spinner와 경과 시간을 갱신한다. 아직 run이 시작되지 않은 환경 진단도 별도 단계로 보인다.
- `smoke`는 도구/Toy/CVDP 각 검사를 한 단계로 표시한다. 단계의 `complete`는 검사 명령이 끝났다는 뜻이며 정답 판정은 기존 `require_verdict`와 최종 `summary.json`이 소유한다. 실패/중단은 성공으로 표시하지 않는다.
- 셸 `bootstrap.sh`의 uv 설치·동기화처럼 Python이 없는 단계는 POSIX 도구만 사용해 경과를 표시하고, 성공·실패·시그널 경로에서 표시용 자식을 정리한다. 출력 리다이렉트나 `--json`에서 진행용 ANSI/반복 라인을 남기지 않는다.
- 모델 진단은 호스트 tool-call과 Docker OpenCode 도구 실행을 따로 표시한다. 기존 자격증명 필터링·진단 실패 처리·JSON 단일 stdout을 유지한다. 선택 데이터셋과 보고서 재생성도 호출 경계만 감싸며 provider·평가기·report의 내부 인터페이스는 바꾸지 않는다.

## 검증과 전달

실제 API·평가 기준·고정 버전 없이 지연된 합성 fixture로 `live` 이벤트가 실행 중 stderr에 도달하는지 확인한다. `smoke`는 각 검사 순서와 실패 시 완료 오표기를 확인한다. 셸/Python 준비·doctor·데이터셋·보고서는 각각 TTY spinner·비TTY 시작/끝, JSON stdout 순도, 시간/중단 정리, 비밀값 비노출을 검사한다. 기존 전체 suite·lint·합성 demo, 실제 Docker 환경이 준비되면 `smoke`를 수행하고 실행 범위를 `docs/verification.md`에 남긴다.

터미널 UX 변경 PR에는 변경 전·후 캡처와 재현 명령을 넣는다. 캡처가 불가능한 실행 환경이면 이유를 PR 본문에 밝힌다. 이미 시작된 사용자의 두 `make live` 프로세스는 건드리지 않으며 수정은 새 실행부터 적용된다.

## 대안과 선택

모든 subprocess를 공통 wrapper로 감싸면 광범위한 인수·로그·종료 처리 변경과 비밀정보 노출 위험이 커진다. 실행 파일만 사후 `tail -f`로 감시하면 초기 다운로드/진단 무출력과 TTY UX를 해결하지 못한다. 기존 이벤트·상태 출력 계약을 호출 경계에서 재사용하고 Python 이전 단계만 셸에서 처리하는 접근을 선택한다.
