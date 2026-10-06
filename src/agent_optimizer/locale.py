"""사람에게 표시하는 문구의 언어를 고릅니다. 실행 데이터는 번역하지 않습니다."""

import os
import re
from pathlib import Path


MESSAGES = {
    '보고서': ('보고서', 'report'),
    'Native CID·row 선택': ('Native CID·row 선택', 'Native CID and row selection'),
    'Native row 선택': ('Native row 선택', 'Native row selection'),
    '선택 row의 split 지정': ('선택 row의 split 지정', 'Assign the selected row split'),
    '세션 개별 실행': ('세션 개별 실행', 'Individual session runs'),
    'HTML 보고서 보기': ('HTML 보고서 보기', 'View HTML report'),
    '미설정': ('미설정', 'Not configured'),
    '미선택': ('미선택', 'Not selected'),
    '현재': ('현재', 'Current'),
    '도구': ('도구', 'Tools'),
    'CID(쉼표 구분): cid002/cid004/cid007/cid016': ('CID(쉼표 구분): cid002/cid004/cid007/cid016', 'CID (comma-separated): cid002/cid004/cid007/cid016'),
    'row ID → split JSON: {"ROW_A":"train","ROW_B":"validation"}': ('row ID → split JSON: {"ROW_A":"train","ROW_B":"validation"}', 'Row ID → split JSON: {"ROW_A":"train","ROW_B":"validation"}'),
    '고정 원본 CVDP JSONL 절대경로(trusted)': ('고정 원본 CVDP JSONL 절대경로(trusted)', 'Absolute pinned CVDP JSONL path (trusted)'),
    '준비된 native source 절대경로(upstream과 배타)': ('준비된 native source 절대경로(upstream과 배타)', 'Absolute prepared native source path (exclusive with upstream)'),
    '고정 로컬 upstream 절대경로(source와 배타)': ('고정 로컬 upstream 절대경로(source와 배타)', 'Absolute pinned local upstream path (exclusive with source)'),
    'native Python 3.12 경로(미입력: 현재 interpreter)': ('native Python 3.12 경로(미입력: 현재 interpreter)', 'Native Python 3.12 path (default: current interpreter)'),
    '공식 evaluator repo/python/sim_image/sim_image_id JSON': ('공식 evaluator repo/python/sim_image/sim_image_id JSON', 'Official evaluator repo/python/sim_image/sim_image_id JSON'),
    '고정 데이터의 row 목록에서 선택': ('고정 데이터의 row 목록에서 선택', 'Select from pinned dataset rows'),
    'CID와 dataset 경로 입력 후 과제 ID·target·지원 상태를 확인하고 split을 직접 선택합니다.': ('CID와 dataset 경로 입력 후 과제 ID·target·지원 상태를 확인하고 split을 직접 선택합니다.', 'Enter CID and dataset path, inspect task IDs, targets and support, then explicitly select splits.'),
    '모델 설정으로 계속': ('모델 설정으로 계속', 'Continue to model settings'),
    '선택을 검증합니다. 준비·다운로드·모델 호출 없음.': ('선택을 검증합니다. 준비·다운로드·모델 호출 없음.', 'Validate selection without preparation, downloads or model calls.'),
    'Native 설정으로 돌아가기': ('Native 설정으로 돌아가기', 'Back to native settings'),
    '선택한 row·split을 보존합니다.': ('선택한 row·split을 보존합니다.', 'Preserve selected rows and splits.'),
    'Optimizer 이력·변이 근거에 사용할 공개 과제': ('Optimizer 이력·변이 근거에 사용할 공개 과제', 'Public tasks for optimizer history and mutation evidence'),
    '수치 비교·후보 선택; private 평가 자료는 공개하지 않음': ('수치 비교·후보 선택; private 평가 자료는 공개하지 않음', 'Numeric comparison and candidate selection; private evaluation remains hidden'),
    '선택 고정 후 최종 평가에만 사용': ('선택 고정 후 최종 평가에만 사용', 'Final evaluation only after selection is frozen'),
    '이 row 선택을 제거': ('이 row 선택을 제거', 'Remove this row selection'),
    'row 형태 검토만 완료; 실환경 not_run. Enter로 split을 명시하세요.': ('row 형태 검토만 완료; 실환경 not_run. Enter로 split을 명시하세요.', 'Row shape reviewed only; live not_run. Press Enter to assign a split.'),
    'CID007: PNR·상용 helper row는 선택 후 검증에서 명시 거부됩니다.': ('CID007: PNR·상용 helper row는 선택 후 검증에서 명시 거부됩니다.', 'CID007: PNR and commercial-helper rows explicitly fail selection validation.'),
    '브라우저': ('브라우저', 'Browser'),
    '열기 요청 성공': ('열기 요청 성공', 'Open request succeeded'),
    '자동 열기 없음/실패; URL을 직접 여세요': ('자동 열기 없음/실패; URL을 직접 여세요', 'Automatic opening unavailable/failed; open the URL directly'),
    'localhost는 실행 머신입니다. SSH에서는 포트포워딩이 필요합니다. HTML 한 파일만 제공됩니다.': ('localhost는 실행 머신입니다. SSH에서는 포트포워딩이 필요합니다. HTML 한 파일만 제공됩니다.', 'localhost is the execution machine. SSH requires port forwarding. Only one HTML file is served.'),
    'native CVDP CID 명시 선택(반복 가능)': ('native CVDP CID 명시 선택(반복 가능)', 'Explicit native CVDP CID selection (repeatable)'),
    '준비된 고정 native source': ('준비된 고정 native source', 'Prepared pinned native source'),
    "필요": ("필요", "Requires"),
    "조합": ("조합", "Compatible with"),
    "범위": ("범위", "Status scope"),
    "도구·모델·평가 실행은 조회에서 검사하지 않습니다": (
        "도구·모델·평가 실행은 조회에서 검사하지 않습니다",
        "Tool, model and evaluator execution are not checked by catalog"),
    "등록됨; 실행 환경은 별도 진단": (
        "등록됨; 실행 환경은 별도 진단", "Registered; diagnose execution environment separately"),
    "준비 확인 필요": ("준비 확인 필요", "Preparation required"),
    "등록됨": ("등록됨", "Registered"),
    "고정 ACE 스킬 소스; 자산 준비 및 모델 필요": (
        "고정 ACE 스킬 소스; 자산 준비 및 모델 필요", "Pinned ACE skill source; assets and model required"),
    "등록된 Harness adapter; 실행 프로필/도구는 별도 확인": (
        "등록된 Harness adapter; 실행 프로필/도구는 별도 확인",
        "Registered Harness adapter; check profile and tools separately"),
    "등록된 Harness 프로필; Agent 지원과 실행 도구 확인 필요": (
        "등록된 Harness 프로필; Agent 지원과 실행 도구 확인 필요",
        "Registered Harness profile; verify Agent support and runtime tools"),
    "ACE-RTL 전용 프로필; 고정 자산·도구·모델 준비 필요": (
        "ACE-RTL 전용 프로필; 고정 자산·도구·모델 준비 필요",
        "Dedicated ACE-RTL profile; pinned assets, tools and model required"),
    "수정 없는 기준 평가; Optimizer 모델 불필요": (
        "수정 없는 기준 평가; Optimizer 모델 불필요", "Unchanged baseline evaluation; no optimizer model"),
    "train 피드백으로 텍스트 후보 생성, validation 비교; merge 미지원": (
        "train 피드백으로 텍스트 후보 생성, validation 비교; merge 미지원",
        "Use training feedback to edit text candidates and compare on validation; merge unavailable"),
    "후보별 활성 Python scaffold 수정·실행; train/validation 필요": (
        "후보별 활성 Python scaffold 수정·실행; train/validation 필요",
        "Edit and execute each candidate Python scaffold; train/validation tasks required"),
    "등록된 Optimizer; 필요한 파일·모델·과제는 설정에서 확인": (
        "등록된 Optimizer; 필요한 파일·모델·과제는 설정에서 확인",
        "Registered Optimizer; check required files, model and tasks in its configuration"),
    "선택 후 데이터·평가기 준비 확인 필요": (
        "선택 후 데이터·평가기 준비 확인 필요", "Check selected data and evaluator preparation"),
    "1, 2, 3, 4 또는 5를 선택하세요": (
        "1, 2, 3, 4 또는 5를 선택하세요", "Choose 1, 2, 3, 4 or 5"),
    "준비된 실험 실행 및 보고서 작성(후보·Harness·평가기 외부 호출 가능).": (
        "준비된 실험 실행 및 보고서 작성(후보·Harness·평가기 외부 호출 가능).",
        "Run an experiment with prepared candidates, Harness and evaluator; write a report (may call external services)."),
    '저장소에서 시작: make setup-core. 기존 실험을 선택하려면 agent-opt tui의 "기존 실험 실행", 새 설정은 agent-opt init(대화형)을 사용하세요. 네 구성요소는 agent-opt catalog에서 조회, 비대화형 선택은 init --help. 데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.': (
        '저장소에서 시작: make setup-core. 기존 실험을 선택하려면 agent-opt tui의 "기존 실험 실행", 새 설정은 agent-opt init(대화형)을 사용하세요. 네 구성요소는 agent-opt catalog에서 조회, 비대화형 선택은 init --help. 데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.',
        'Start in the repository: make setup-core. Select an existing experiment in agent-opt tui, use agent-opt catalog for choices, and init --help for noninteractive setup. Select a dataset explicitly; README.md has a model-free fixture.'),
    "준비·모델 호출 없이 등록된 네 구성요소 조회": (
        "준비·모델 호출 없이 등록된 네 구성요소 조회", "Browse the four registered components without preparation or model calls"),
    "구현된 구성요소와 준비 상태 조회(읽기 전용).": (
        "구현된 구성요소와 준비 상태 조회(읽기 전용).", "List implemented components and preparation status (read-only)."),
    "등록 ID의 역할·제약과 준비 조건 표시(읽기 전용).": (
        "등록 ID의 역할·제약과 준비 조건 표시(읽기 전용).", "Show a registered component's role and requirements (read-only)."),
    "단일 JSON 목록": ("단일 JSON 목록", "One JSON list"),
    "단일 JSON 객체": ("단일 JSON 객체", "One JSON object"),
    "선택한 ACE/CVDP 고정 자산 준비·재사용(다운로드·Docker 빌드 가능).": (
        "선택한 ACE/CVDP 고정 자산 준비·재사용(다운로드·Docker 빌드 가능).",
        "Prepare or reuse selected pinned ACE/CVDP assets (may download or build Docker images)."),
    "Agent 경로/프리셋 설정 생성; --yes는 선택 자산 준비를 승인합니다.": (
        "Agent 경로/프리셋 설정 생성; --yes는 선택 자산 준비를 승인합니다.",
        "Create an experiment from an Agent path or preset; --yes approves asset preparation."),
    "등록된 Agent 프리셋 ID(--agent와 배타)": (
        "등록된 Agent 프리셋 ID(--agent와 배타)", "Registered Agent preset ID (exclusive with --agent)"),
    "전용 Harness 프로필 ID(--harness와 배타)": (
        "전용 Harness 프로필 ID(--harness와 배타)", "Harness profile ID (exclusive with --harness)"),
    "일반 Harness adapter ID(기본 command; --harness-profile과 배타)": (
        "일반 Harness adapter ID(기본 command; --harness-profile과 배타)",
        "Generic Harness adapter ID (default command; exclusive with --harness-profile)"),
    "선택 데이터·고정 소스 다운로드/Docker 빌드 가능성을 승인": (
        "선택 데이터·고정 소스 다운로드/Docker 빌드 가능성을 승인",
        "Approve downloads of selected data/pinned sources and possible Docker builds"),
    "명시적으로 선택할 Optimizer ID(필수, 반복 가능; 예: baseline)": (
        "명시적으로 선택할 Optimizer ID(필수, 반복 가능; 예: baseline)",
        "Select a registered Optimizer ID (required, repeatable; e.g. baseline)"),
    "선택한 실험 준비 확인 · 실제 실행 아님": (
        "선택한 실험 준비 확인 · 실제 실행 아님", "Prepare the selected experiment · not an execution"),
    "일반 실험 preflight 확인 또는 ACE/CVDP 자산 준비·재사용(다운로드·Docker 빌드 가능).": (
        "일반 실험 preflight 확인 또는 ACE/CVDP 자산 준비·재사용(다운로드·Docker 빌드 가능).",
        "Check generic experiment preflight or prepare/reuse ACE/CVDP assets (may download/build Docker images)."),
    "ACE 준비: 고정 소스·데이터·driver 및 Docker 이미지 준비/재사용": (
        "ACE 준비: 고정 소스·데이터·driver 및 Docker 이미지 준비/재사용",
        "Preparing or reusing pinned ACE sources, data, driver and Docker images"),
    "OpenAI API 404 without version path at {endpoint}": (
        "OpenAI API에서 HTTP 404가 발생했습니다 (요청 경로: {endpoint}). API 기본 주소에 /v1이 누락됐습니다. AGENT_OPT_MODEL_BASE_URL=https://api.openai.com/v1로 설정하고 AGENT_OPT_MODEL_ID를 확인하세요.",
        "OpenAI API returned HTTP 404 at {endpoint}. The /v1 API path is missing. Set AGENT_OPT_MODEL_BASE_URL=https://api.openai.com/v1 and verify AGENT_OPT_MODEL_ID."),
    "OpenCode API authentication failed at {endpoint}": (
        "OpenCode 모델 API 인증에 실패했습니다 (HTTP 401, 요청 경로: {endpoint}). AGENT_OPT_MODEL_API_KEY의 유효성과 권한을 확인하세요.",
        "OpenCode model API authentication failed (HTTP 401) at {endpoint}. Verify AGENT_OPT_MODEL_API_KEY and its access."),
    "OpenCode API access denied at {endpoint}": (
        "OpenCode 모델 API 접근 권한이 없습니다 (HTTP 403, 요청 경로: {endpoint}). 계정 권한과 모델 사용 가능 여부를 확인하세요.",
        "OpenCode model API access was denied (HTTP 403) at {endpoint}. Verify account access and model availability."),
    "OpenCode API route or model not found at {endpoint}": (
        "OpenCode 모델 API에서 HTTP 404가 발생했습니다 (요청 경로: {endpoint}). API 기본 주소의 경로와 AGENT_OPT_MODEL_ID를 확인하세요.",
        "OpenCode model API returned HTTP 404 at {endpoint}. Verify the API base path and AGENT_OPT_MODEL_ID."),
    "OpenCode API rate or usage limit reached at {endpoint}": (
        "OpenCode 모델 API 요청 또는 사용량 한도를 초과했습니다 (HTTP 429, 요청 경로: {endpoint}). 한도와 요금제 상태를 확인하세요.",
        "OpenCode model API rate or usage limit was reached (HTTP 429) at {endpoint}. Check the account limits and plan."),
    "OpenCode API request failed with HTTP {status} at {endpoint}": (
        "OpenCode 모델 API 요청이 HTTP {status}로 실패했습니다 (요청 경로: {endpoint}). API 주소·모델 ID와 서비스 상태를 확인하세요.",
        "OpenCode model API request failed with HTTP {status} at {endpoint}. Check the API endpoint, model ID and service status."),
    "OpenCode API error event has no safe HTTP status": (
        "OpenCode API 오류에 HTTP 상태 코드가 없습니다. 실행 요약과 원시 추적을 확인하세요.",
        "OpenCode API error did not include an HTTP status. Check the run summary and raw trace."),
    "Unknown API endpoint": ("알 수 없는 경로", "unknown endpoint"),
    "Failure cause": ("실패 원인", "Failure cause"),
    "Run summary": ("실행 요약", "Run summary"),
    "Correct the API base path and model ID from the failure cause.": (
        "실패 원인에 따라 AGENT_OPT_MODEL_BASE_URL의 API 경로와 AGENT_OPT_MODEL_ID를 수정하세요.",
        "Correct the API path in AGENT_OPT_MODEL_BASE_URL and AGENT_OPT_MODEL_ID as indicated by the failure cause."),
    "실험 시작: 5. 프리셋 선택형 새 최적화  1. 기존 실험 실행  2. 고급 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제  4. 이전 실행 보기": (
        "실험 시작: 5. 프리셋 선택형 새 최적화  1. 기존 실험 실행  2. 고급 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제  4. 이전 실행 보기",
        "Start an experiment: 5. New preset optimization  1. Run existing experiment  2. Advanced new experiment  3. Legacy ACE-RTL + CVDP example  4. View previous runs"),
    "선택 [5/1/2/3/4]: ": ("선택 [5/1/2/3/4]: ", "Choice [5/1/2/3/4]: "),
    "세션 대기": ("대기", "queued"),
    "세션 실행 중": ("실행 중", "running"),
    "세션 완료": ("완료", "completed"),
    "세션 실패": ("실패", "failed"),
    "세션 중단": ("중단", "interrupted"),
    "세션 전체": ("전체", "overall"),
    "세션 집계 완료": ("완료", "done"),
    "세션 집계 실행": ("실행", "running"),
    "세션 집계 대기": ("대기", "queued"),
    "세션 집계 실패": ("실패", "failed"),
    "선택한 데이터셋마다 독립 평가기로 병렬 실행(기본 2개).": (
        "선택한 데이터셋마다 독립 평가기로 병렬 실행(기본 2개).",
        "Run selected datasets in parallel with independent evaluators (2 workers by default)."),
    "remedy": ("해결", "Remedy"),
    "readiness": ("준비 상태", "readiness"),
    "Synthetic fixture tasks are valid": ("합성 예제 과제를 사용할 수 있습니다", "Synthetic fixture tasks are valid"),
    "Synthetic fixture evaluator is available": ("합성 예제 채점기를 사용할 수 있습니다", "Synthetic fixture evaluator is available"),
    "Core development environment: ": ("코어 개발 환경: ", "Core development environment: "),
    "Selected dataset environment: ": ("선택한 데이터셋 환경: ", "Selected dataset environment: "),
    "Development environment: ": ("개발 환경: ", "Development environment: "),
    "ready": ("준비됨", "ready"),
    "not ready": ("준비되지 않음", "not ready"),
    "Fix:": ("해결:", "Fix:"),
    "ACE evaluation and model readiness not checked; use full setup/doctor (menu option 7 prepares ACE).": ("ACE 평가와 모델 준비 상태는 검사하지 않았습니다. 전체 setup/doctor를 실행하세요 (메뉴 7번으로 ACE 환경 준비).", "ACE evaluation and model readiness not checked; use full setup/doctor (menu option 7 prepares ACE)."),
    "Selected dataset checks are read-only; no ACE Agent image or model was checked.": ("선택한 데이터셋의 읽기 전용 검사입니다. ACE Agent 이미지와 모델은 검사하지 않았습니다.", "Selected dataset checks are read-only; no ACE Agent image or model was checked."),
    "Explicit model probes: ": ("명시적으로 실행한 모델 검사: ", "Explicit model probes: "),
    "Live checks validate configuration only; no model endpoint or smoke was exercised. Use doctor --model for actual calls.": ("실행 진단은 설정만 검사했습니다. 모델 API와 smoke는 실행하지 않았습니다. 실제 호출에는 doctor --model을 사용하세요.", "Live checks validate configuration only; no model endpoint or smoke was exercised. Use doctor --model for actual calls."),
    "TUI requires a TTY for both input and output": ("TUI에는 입력과 출력 모두 TTY가 필요합니다", "TUI requires a TTY for both input and output"),
    "개발 명령: setup → doctor → demo. 어느 작업 디렉터리에서나 실행할 수 있습니다.": ("개발 명령: setup → doctor → demo. 어느 작업 디렉터리에서나 실행할 수 있습니다.", "Development commands: setup → doctor → demo. Run from any directory."),
    "프로젝트 .venv에서 unittest 실행(Docker 불필요)": ("프로젝트 .venv에서 unittest 실행(Docker 불필요)", "Run unittest in project .venv (no Docker required)"),
    "프로젝트 .venv에서 Ruff 검사 실행": ("프로젝트 .venv에서 Ruff 검사 실행", "Run Ruff in project .venv"),
    "Docker/API 없이 최소 합성 데모 실행": ("Docker/API 없이 최소 합성 데모 실행", "Run minimal synthetic demo without Docker/API"),
    "실제 RTL/CVDP 평가기 검사 실행": ("실제 RTL/CVDP 평가기 검사 실행", "Check real RTL/CVDP evaluators"),
    "설정한 모델로 반복 최적화 실행(인증 필요)": ("설정한 모델로 반복 최적화 실행(인증 필요)", "Run optimization with a configured model (authentication required)"),
    "대화형 번호 메뉴 열기(TTY 필요, 모델 설정은 세션에서만 유지)": ("대화형 번호 메뉴 열기(TTY 필요, 모델 설정은 세션에서만 유지)", "Open numbered menu (TTY required; model settings remain in session)"),
    "도구 조회나 설치 없이 이 도움말 표시": ("도구 조회나 설치 없이 이 도움말 표시", "Show help without probing or installing tools"),
    "코어 사전 준비: Git. ACE 전체 준비에는 Docker Engine/Compose도 필요합니다. Python이나 make가 없다면 sh scripts/bootstrap.sh setup --core를 사용하세요. make ARGS는 인용된 옵션 값을 허용하지만 셸 코드를 실행하지 않습니다. 복잡한 인수는 sh scripts/bootstrap.sh <명령> [옵션]으로 전달하세요.": ("코어 사전 준비: Git. ACE 전체 준비에는 Docker Engine/Compose도 필요합니다. Python이나 make가 없다면 sh scripts/bootstrap.sh setup --core를 사용하세요. make ARGS는 인용된 옵션 값을 허용하지만 셸 코드를 실행하지 않습니다. 복잡한 인수는 sh scripts/bootstrap.sh <명령> [옵션]으로 전달하세요.", "Core prerequisite: Git. Full ACE also needs Docker Engine/Compose. Without Python or make use sh scripts/bootstrap.sh setup --core. make ARGS accepts quoted option values without running shell code. For complex arguments use sh scripts/bootstrap.sh <command> [options]."),
    "--core/--dataset 없이: ACE 전체 준비; --core: 코어와 합성 fixture; --dataset ID: 선택한 데이터셋 준비. --offline도 캐시 동기화·진단을 수행하며 코어/전체는 데모도 실행합니다.": ("--core/--dataset 없이: ACE 전체 준비; --core: 코어와 합성 fixture; --dataset ID: 선택한 데이터셋 준비. --offline도 캐시 동기화·진단을 수행하며 코어/전체는 데모도 실행합니다.", "Default: full ACE setup; --core: core and synthetic fixture; --dataset ID: selected assets. --offline still syncs and checks; core/full setup also runs the demo."),
    "--core/--dataset 없이: ACE 전체 읽기 전용 진단; --core: 코어 진단; --dataset ID: 선택한 데이터셋 읽기 전용 진단; --model: 실제 API·컨테이너 도구 호출(ACE 전체 전용)": ("--core/--dataset 없이: ACE 전체 읽기 전용 진단; --core: 코어 진단; --dataset ID: 선택한 데이터셋 읽기 전용 진단; --model: 실제 API·컨테이너 도구 호출(ACE 전체 전용)", "Default: read-only full ACE checks; --core: core; --dataset ID: read-only selected assets; --model: real API/container tool calls (full ACE only)"),
    "다운로드·빌드 없이 캐시 재사용; 동기화·진단 및 코어/전체 데모 결과 생성": ("다운로드·빌드 없이 캐시 재사용; 동기화·진단 및 코어/전체 데모 결과 생성", "Reuse caches without download/build; sync, diagnose and generate a demo for core/full setup"),
    "실제 호스트 API와 컨테이너 OpenCode 도구 호출(로그 생성 가능)": ("실제 호스트 API와 컨테이너 OpenCode 도구 호출(로그 생성 가능)", "Call the real host API and container OpenCode tool (may write logs)"),
    "선택: ": ("선택: ", "Choice: "),
    "TTY 필요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.": ("TTY 필요. 자동화에는 setup/doctor/demo/live 명령을 사용하세요.", "TTY required. For automation use setup/doctor/demo/live commands."),
    "대화형 번호 메뉴. 자동화에는 명시적 명령을 사용합니다.": ("대화형 번호 메뉴. 자동화에는 명시적 명령을 사용합니다.", "Interactive numbered menu. Use explicit commands for automation."),
    "1. 코어 개발 환경 설치": ("1. 코어 개발 환경 설치", "1. Set up core development environment"),
    "2. 코어 환경 진단": ("2. 코어 환경 진단", "2. Check core environment"),
    "3. LLM 없이 데모·최적화 반복 테스트": ("3. LLM 없이 데모·최적화 반복 테스트", "3. Run demo and optimizer tests without an LLM"),
    "4. 모델 설정·연결 검사": ("4. 모델 설정·연결 검사", "4. Configure and check model connection"),
    "5. ACE 최적화 실행 — 반복 횟수 선택": ("5. ACE 최적화 실행 — 반복 횟수 선택", "5. Run ACE optimization — choose iterations"),
    "6. 실행 결과·보고서 확인": ("6. 실행 결과·보고서 확인", "6. View runs and reports"),
    "7. ACE 전체 환경 준비 — Docker·평가/모델 실행 자산": ("7. ACE 전체 환경 준비 — Docker·평가/모델 실행 자산", "7. Prepare full ACE environment — Docker, evaluator, and model assets"),
    "8. 일반 Agent 최적화 TUI": ("8. 일반 Agent 최적화 TUI", "8. General Agent optimization TUI"),
    "0. 종료": ("0. 종료", "0. Exit"),
    "│  Agent Optimizer   ·   new optimization experiment     │": ("│  Agent Optimizer   ·   새 최적화 실험             │", "│  Agent Optimizer   ·   new optimization experiment     │"),
    "Experiment name": ("실험 이름", "Experiment name"),
    "실험 이름은 영문·숫자로 시작하고 영문·숫자·_·.·-만 사용할 수 있습니다": (
        "실험 이름은 영문·숫자로 시작하고 영문·숫자·_·.·-만 사용할 수 있습니다",
        "Experiment name must start with a letter/digit and contain only letters, digits, _, . or -"),
    "Agent source directory or pinned Git URL": ("Agent 소스 디렉터리 또는 고정 Git URL", "Agent source directory or pinned Git URL"),
    "Git commit (leave blank for local source)": ("Git commit (로컬 소스이면 빈칸)", "Git commit (leave blank for local source)"),
    "Agent execution argv (e.g. python agent.py {task_dir})": ("Agent 실행 인수 (예: python agent.py {task_dir})", "Agent execution argv (e.g. python agent.py {task_dir})"),
    "Editable files (comma separated)": ("수정 가능한 파일 (쉼표로 구분)", "Editable files (comma separated)"),
    "Choose a dataset; there is no automatic recommendation:": ("데이터셋을 직접 선택하세요. 자동 추천은 없습니다:", "Choose a dataset; there is no automatic recommendation:"),
    "Dataset numbers or local tasks.json paths (comma separated)": ("데이터셋 번호 또는 로컬 tasks.json 경로 (쉼표로 구분)", "Dataset numbers or local tasks.json paths (comma separated)"),
    "Evaluator file.py:Symbol or registered name": ("채점기 file.py:Symbol 또는 등록 이름", "Evaluator file.py:Symbol or registered name"),
    "Evaluator score metric (Enter for passed)": ("채점 지표 (Enter: passed)", "Evaluator score metric (Enter for passed)"),
    "Score direction maximize/minimize (Enter for maximize)": ("점수 방향 maximize/minimize (Enter: maximize)", "Score direction maximize/minimize (Enter for maximize)"),
    "Select optimizer algorithms:": ("Optimizer 알고리즘 선택:", "Select optimizer algorithms:"),
    "Optimizer numbers (comma separated)": ("Optimizer 번호 (쉼표로 구분)", "Optimizer numbers (comma separated)"),
    "Select an Agent harness:": ("Agent 하네스 선택:", "Select an Agent harness:"),
    "Harness number": ("하네스 번호", "Harness number"),
    "Active runtime harness .py file (Enter to auto-detect one match)": ("실행 중인 하네스 .py 파일 (Enter: 하나만 자동 탐지)", "Active runtime harness .py file (Enter to auto-detect one match)"),
    "Editable text target (Enter to auto-detect one match)": ("수정할 텍스트 파일 (Enter: 하나만 자동 탐지)", "Editable text target (Enter to auto-detect one match)"),
    "Prepare dataset and run? [y/N]": ("데이터셋을 준비하고 실행할까요? [y/N]", "Prepare dataset and run? [y/N]"),
    "Score direction must be maximize or minimize": ("점수 방향은 maximize 또는 minimize여야 합니다", "Score direction must be maximize or minimize"),
    "Choose one or more listed optimizer numbers": ("목록에서 Optimizer 번호를 하나 이상 고르세요", "Choose one or more listed optimizer numbers"),
    "Choose one or more listed optimizers": ("목록에서 Optimizer를 하나 이상 고르세요", "Choose one or more listed optimizers"),
    "Choose a listed harness number": ("목록의 하네스 번호를 고르세요", "Choose a listed harness number"),
    "목록의 데이터셋 번호 또는 로컬 tasks.json 경로를 입력하세요": (
        "목록의 데이터셋 번호 또는 로컬 tasks.json 경로를 입력하세요",
        "Choose a listed dataset number or a local tasks.json path"),
    "잘못된 Agent 실행 명령": ("잘못된 Agent 실행 명령", "Invalid Agent execution command"),
    "결과: runs/<run-id>/report.html. 의존성 다운로드가 가능하며 ACE 전체는 Docker 자산도 준비합니다.": (
        "결과: runs/<run-id>/report.html. 의존성 다운로드가 가능하며 ACE 전체는 Docker 자산도 준비합니다.",
        "Result: runs/<run-id>/report.html. Dependencies may download; full ACE prepares Docker assets."),
    "실제 모델 API 호출은 --model에서만 수행합니다. ready는 Agent 실행 성공이 아닙니다; 설치하지 않습니다.": (
        "실제 모델 API 호출은 --model에서만 수행합니다. ready는 Agent 실행 성공이 아닙니다; 설치하지 않습니다.",
        "Actual model API calls require --model. Ready does not prove Agent execution; no installation."),
    "unittest를 기존 .venv에서 실행합니다. 설치 없이 실패하면 setup --core로 복구하세요.": (
        "unittest를 기존 .venv에서 실행합니다. 설치 없이 실패하면 setup --core로 복구하세요.",
        "Run unittest in the existing .venv. No installation; repair with setup --core."),
    "Ruff를 기존 .venv에서 실행합니다. 설치 없이 실패하면 setup --core로 복구하세요.": (
        "Ruff를 기존 .venv에서 실행합니다. 설치 없이 실패하면 setup --core로 복구하세요.",
        "Run Ruff in the existing .venv. No installation; repair with setup --core."),
    "합성 fixture의 report.html을 runs/<run-id>/에 생성합니다. 실제 모델·공식 평가가 아닙니다.": (
        "합성 fixture의 report.html을 runs/<run-id>/에 생성합니다. 실제 모델·공식 평가가 아닙니다.",
        "Write a synthetic fixture report.html in runs/<run-id>/; not actual model/official evaluation."),
    "공식 CVDP 정답·오답과 실도구를 검사합니다. 모델 호출은 없으며 전체 setup이 먼저 필요합니다.": (
        "공식 CVDP 정답·오답과 실도구를 검사합니다. 모델 호출은 없으며 전체 setup이 먼저 필요합니다.",
        "Check official CVDP positive/negative cases and real tools; no model calls; requires full setup."),
    "실제 모델·Agent·공식 평가를 실행합니다. 전체 setup과 모델 인증이 필요합니다.": (
        "실제 모델·Agent·공식 평가를 실행합니다. 전체 setup과 모델 인증이 필요합니다.",
        "Run the actual model, Agent and official evaluation; requires full setup and credentials."),
    "TTY에서만 실행하며 시작만으로 설치·모델 호출을 하지 않습니다.": (
        "TTY에서만 실행하며 시작만으로 설치·모델 호출을 하지 않습니다.",
        "Requires TTY; starting the menu does not install or call a model."),
    "도구 조회·설치 없이 도움말만 표시합니다.": (
        "도구 조회·설치 없이 도움말만 표시합니다.", "Show help without probing or installing tools."),
    "고정 Git·데이터·Python driver·Docker 공식 채점 필요": (
        "고정 Git·데이터·Python driver·Docker 공식 채점 필요",
        "Pinned Git/data, Python driver, Docker official scorer required"),
    "고정 Git·데이터·Docker/Icarus 평가 필요": (
        "고정 Git·데이터·Docker/Icarus 평가 필요", "Pinned Git/data and Docker/Icarus evaluation required"),
    "합성 fixture · 모델/Docker 불필요 · 내장 과제·채점기": (
        "합성 fixture · 모델/Docker 불필요 · 내장 과제·채점기",
        "Synthetic fixture · no model/Docker · bundled tasks/scorer"),
    "팀 제공 데이터·채점기/준비 조건 확인": (
        "팀 제공 데이터·채점기/준비 조건 확인", "Team dataset · check scorer/preparation requirements"),
    "로컬 tasks.json은 별도 evaluator.py:Symbol이 필요합니다": (
        "로컬 tasks.json은 별도 evaluator.py:Symbol이 필요합니다",
        "Local tasks.json requires a separate evaluator.py:Symbol"),
    "변경 없음 · 모델 API 불필요": ("변경 없음 · 모델 API 불필요", "No mutation · no model API"),
    "변형 파일/설정 필요 · 모델 API 불필요": (
        "변형 파일/설정 필요 · 모델 API 불필요", "Variant files/config needed · no model API"),
    "모델 API·train 과제·수정 가능 텍스트 파일 필요": (
        "모델 API·train 과제·수정 가능 텍스트 파일 필요", "Model API, train tasks and editable text file required"),
    "모델 API·train 과제·수정 가능 .py 파일 필요": (
        "모델 API·train 과제·수정 가능 .py 파일 필요", "Model API, train tasks and editable .py file required"),
    "팀 구현 · 의존성/추가 파일 확인": (
        "팀 구현 · 의존성/추가 파일 확인", "Team implementation · check dependencies/extra files"),
    "합성 예제 전용 · 외부 모델/도구 불필요": (
        "합성 예제 전용 · 외부 모델/도구 불필요", "Synthetic example only · no external model/tool"),
    "Agent 실행 argv 입력 · 외부 도구/모델은 지정한 명령에 따름": (
        "Agent 실행 argv 입력 · 외부 도구/모델은 지정한 명령에 따름",
        "Supply Agent argv · external tool/model depends on your command"),
    "OpenCode CLI·모델 선택자/인증 필요": (
        "OpenCode CLI·모델 선택자/인증 필요", "OpenCode CLI and model selector/credentials required"),
    "Claude Code CLI·인증/모델 필요": (
        "Claude Code CLI·인증/모델 필요", "Claude Code CLI, credentials and model required"),
    "팀 구현 · 전용 프로필/도구 확인": (
        "팀 구현 · 전용 프로필/도구 확인", "Team implementation · check dedicated profile/tools"),
    "수정 가능 경로": ("수정 가능 경로", "Editable paths"),
    "준비 작업": ("준비 작업", "Preparation"),
    "선택한 합성 fixture·채점기 사용; 고정 데이터셋 다운로드 없음": (
        "선택한 합성 fixture·채점기 사용; 고정 데이터셋 다운로드 없음",
        "No pinned dataset download for the selected fixture; use bundled tasks/scorer"),
    "로컬 tasks.json·명시적 채점기를 확인; 팀 provider가 있으면 추가 조건 확인": (
        "로컬 tasks.json·명시적 채점기를 확인; 팀 provider가 있으면 추가 조건 확인",
        "Check local tasks.json and explicit scorer; check any team provider requirements"),
    "선택한 과제·채점기 준비; 팀 provider의 다운로드/도구 조건은 구현 확인": (
        "선택한 과제·채점기 준비; 팀 provider의 다운로드/도구 조건은 구현 확인",
        "Prepare selected tasks/scorer; check team provider download/tool requirements"),
    "선택한 데이터셋의 과제·채점기 준비; 고정 데이터셋에는 다운로드·Docker 빌드 가능": (
        "선택한 데이터셋의 과제·채점기 준비; 고정 데이터셋에는 다운로드·Docker 빌드 가능",
        "Prepare selected tasks/scorer; pinned datasets may download data and build Docker images"),
    "기본 예산": ("기본 예산", "Default budget"),
    "예약 trial 수": ("예약 trial 수", "reserved trials"),
    "모델·도구 호출": ("모델·도구 호출", "Model/tool calls"),
    "합성 fixture는 외부 모델/도구를 호출하지 않음": (
        "합성 fixture는 외부 모델/도구를 호출하지 않음",
        "Synthetic fixture does not call an external model/tool"),
    "실행 시 모델/외부 도구 호출 가능; 설정 생성만으로는 호출하지 않음": (
        "실행 시 모델/외부 도구 호출 가능; 설정 생성만으로는 호출하지 않음",
        "Run may call a model/external tool; config generation alone does not"),
    "Agent 실행 명령에 따라 외부 도구/모델 호출 가능; 설정 생성만으로는 호출하지 않음": (
        "Agent 실행 명령에 따라 외부 도구/모델 호출 가능; 설정 생성만으로는 호출하지 않음",
        "Agent command may call an external tool/model; config generation alone does not"),
    "설정 위치": ("설정 위치", "Configuration path"),
    "예상 보고서": ("예상 보고서", "Expected report"),
    "Experiment cancelled without preparing data": ("데이터 준비 전에 실험을 취소했습니다", "Experiment cancelled without preparing data"),
    "Docker·ACE 평가/모델 실행 자산이 필요하면 먼저 7번 ACE 전체 환경 준비를 선택하세요.": ("Docker·ACE 평가/모델 실행 자산이 필요하면 먼저 7번 ACE 전체 환경 준비를 선택하세요.", "If you need Docker and ACE evaluation/model assets, choose full ACE setup (option 7) first."),
    "이 작업은 doctor --model로 실제 모델 API·컨테이너 도구를 호출합니다. 설정은 현재 세션에만 유지됩니다.": ("이 작업은 doctor --model로 실제 모델 API·컨테이너 도구를 호출합니다. 설정은 현재 세션에만 유지됩니다.", "This runs doctor --model against the actual model API and container tools. Settings remain in this session only."),
    "{name} (빈 입력: 기존 값 유지): ": ("{name} (빈 입력: 기존 값 유지): ", "{name} (blank: keep current value): "),
    "AGENT_OPT_MODEL_ID (빈 입력: 기존 값 또는 glm5.3-flash): ": ("AGENT_OPT_MODEL_ID (빈 입력: 기존 값 또는 glm5.3-flash): ", "AGENT_OPT_MODEL_ID (blank: current value or glm5.3-flash): "),
    "Bearer token (숨김, 빈 입력: 기존 값 유지): ": ("Bearer token (숨김, 빈 입력: 기존 값 유지): ", "Bearer token (hidden; blank: keep current value): "),
    "모델 API 키 (숨김): ": ("모델 API 키 (숨김): ", "Model API key (hidden): "),
    "{key} (OpenCode 모델): ": ("{key} (OpenCode 모델): ", "{key} (OpenCode model): "),
    "ACE 실행에는 7번 전체 환경 준비와 4번 모델 설정이 필요합니다.": ("ACE 실행에는 7번 전체 환경 준비와 4번 모델 설정이 필요합니다.", "ACE runs require full setup (option 7) and model configuration (option 4)."),
    "모델 설정이 없거나 잘못되었습니다.": ("모델 설정이 없거나 잘못되었습니다.", "Model configuration is missing or invalid."),
    "먼저 4번 모델 설정·연결 검사를 선택하세요.": ("먼저 4번 모델 설정·연결 검사를 선택하세요.", "Choose model configuration and connection check (option 4) first."),
    "반복 횟수 [3] (1..20): ": ("반복 횟수 [3] (1..20): ", "Iterations [3] (1..20): "),
    "반복 횟수는 1..20 정수여야 합니다.": ("반복 횟수는 1..20 정수여야 합니다.", "Iterations must be an integer from 1 to 20."),
    "설정한 모델로 실제 ACE 최적화를 실행합니다.": ("설정한 모델로 실제 ACE 최적화를 실행합니다.", "Running ACE optimization with the configured model."),
    "보고서가 없습니다.": ("보고서가 없습니다.", "No reports found."),
    "3번 데모 또는 5번 실행 후 확인하세요.": ("3번 데모 또는 5번 실행 후 확인하세요.", "Run the demo (option 3) or optimization (option 5) first."),
    "보고서 번호 (0: 돌아가기): ": ("보고서 번호 (0: 돌아가기): ", "Report number (0: back): "),
    "목록의 보고서 번호를 선택하세요.": ("목록의 보고서 번호를 선택하세요.", "Choose a listed report number."),
    "Agent Optimizer · 개발자 메뉴": ("Agent Optimizer · 개발자 메뉴", "Agent Optimizer · Developer menu"),
    "생성된 리포트 없음": ("생성된 리포트 없음", "No report produced"),
    "데이터셋 리포트 열기 ↗": ("데이터셋 리포트 열기 ↗", "Open dataset report ↗"),
    "데이터셋": ("데이터셋", "Dataset"),
    "상태": ("상태", "Status"),
    "데이터셋 세션": ("데이터셋 세션", "Dataset session"),
    "데이터셋별 독립 평가": ("데이터셋별 독립 평가", "Independent evaluations"),
    "각 데이터셋은 자체 채점기를 사용합니다. ": ("각 데이터셋은 자체 채점기를 사용합니다. ", "Each dataset uses its own scorer. "),
    "결과를 함께 순위화하지 마세요.": ("결과를 함께 순위화하지 마세요.", "Do not rank results from different evaluators together."),
    "독립 평가": ("독립 평가", "Independent evaluation"),
    "서로 다른 채점기의 점수를 직접 비교하거나 순위를 매기지 않습니다.": ("서로 다른 채점기의 점수를 직접 비교하거나 순위를 매기지 않습니다.", "Scores from different evaluators must not be compared or ranked directly."),
    "세션 summary.json": ("세션 summary.json", "Session summary.json"),
    "실험": ("실험", "Experiment"),
    "실험 분석": ("실험 분석", "Experiment analysis"),
    "리포트 목차": ("리포트 목차", "Report sections"),
    "점수 비교": ("점수 비교", "Comparison"),
    "최종 테스트": ("최종 테스트", "Held-out test"),
    "최적화 과정": ("최적화 과정", "Journey"),
    "평가 근거": ("평가 근거", "Evaluations"),
    "후보 변경": ("후보 변경", "Candidates"),
    "실패 근거": ("실패 근거", "Failures"),
    "단계와 사용량": ("단계와 사용량", "Stages & usage"),
    "재현 정보": ("재현 정보", "Reproduce"),
    "합성 예제": ("합성 예제", "Synthetic fixture"),
    "연결 확인용 예제이며 실제 모델 성능을 입증하지 않습니다.": ("연결 확인용 예제이며 실제 모델 성능을 입증하지 않습니다.", "Connection-only fixture; not evidence of model performance."),
    "실제 모델 성능 근거 아님": ("실제 모델 성능 근거 아님", "not a model-performance claim"),
    "벤치마크 기록 · 모델 근거는 별도 확인 필요": ("벤치마크 기록 · 모델 근거는 별도 확인 필요", "Benchmark evidence · verify model evidence separately"),
    "Agent × 하네스 그룹": ("Agent × 하네스 그룹", "Agent × Harness groups"),
    "하나의 Agent와 실행 하네스를 짝지어 독립적으로 평가한 단위입니다.": ("하나의 Agent와 실행 하네스를 짝지어 독립적으로 평가한 단위입니다.", "An independently evaluated Agent and Harness pairing."),
    "완료된 평가": ("완료된 평가", "Completed evaluations"),
    "과제별로 실제 종료되어 기록된 평가 건수입니다.": ("과제별로 실제 종료되어 기록된 평가 건수입니다.", "The number of task evaluations that actually completed."),
    "통과한 평가": ("통과한 평가", "Passed evaluations"),
    "실패한 평가": ("실패한 평가", "Failed evaluations"),
    "예산 사용 횟수": ("예산 사용 횟수", "Trials used (budget)"),
    "예약되어 사용된 평가 예산입니다. 완료된 평가 건수와 다를 수 있습니다.": ("예약되어 사용된 평가 예산입니다. 완료된 평가 건수와 다를 수 있습니다.", "Reserved trial budget; it may differ from the count of completed evaluations."),
    "기준 후보": ("기준 후보", "Baseline"),
    "최적화하기 전의 Agent를 동일 조건에서 평가한 결과입니다.": ("최적화하기 전의 Agent를 동일 조건에서 평가한 결과입니다.", "The unoptimized Agent evaluated under the same conditions."),
    "검증": ("검증", "validation"),
    "후보를 선택할 때 사용하는 데이터입니다. 최종 테스트와 분리됩니다.": ("후보를 선택할 때 사용하는 데이터입니다. 최종 테스트와 분리됩니다.", "Data used to select candidates, separate from the final test."),
    "선택된 ": ("선택된 ", "selected "),
    " 결과": (" 결과", " results"),
    "같은 그룹의 검증 집계만 비교합니다. 지표 방향과 차이는 기록된 리포트를 따르며 없는 점수는 0으로 취급하지 않습니다.": ("같은 그룹의 검증 집계만 비교합니다. 지표 방향과 차이는 기록된 리포트를 따르며 없는 점수는 0으로 취급하지 않습니다.", "Compare within-group validation aggregates only. Direction and difference come from the recorded report; missing scores are not zero."),
    "일부만 기록된 하네스 사용량을 전체 사용량으로 표시하지 않습니다. 데이터·모델·예산이 같은 실험끼리 비교하세요. ": ("일부만 기록된 하네스 사용량을 전체 사용량으로 표시하지 않습니다. 데이터·모델·예산이 같은 실험끼리 비교하세요. ", "Partial Harness usage is never labeled complete. Compare only runs with equivalent data, models, and budgets. "),
    "명령 실패 (exit {code}).": ("명령 실패 (exit {code}).", "Command failed (exit {code})."),
    "위 출력을 확인하세요; 자동 재시도하지 않습니다.": ("위 출력을 확인하세요; 자동 재시도하지 않습니다.", "Inspect the output above; there is no automatic retry."),
    "프로젝트 .venv가 필요합니다:": ("프로젝트 .venv가 필요합니다:", "Project .venv is required:"),
    "합성 최소 데모 후 로컬 HTTP fixture 기반 Optimizer 회귀 테스트 (외부 LLM·Docker 없음).": ("합성 최소 데모 후 로컬 HTTP fixture 기반 Optimizer 회귀 테스트 (외부 LLM·Docker 없음).", "Run a minimal synthetic demo, then Optimizer regression tests using a local HTTP fixture (no external LLM or Docker)."),
    "menu requires a TTY;": ("menu에는 TTY가 필요합니다;", "menu requires a TTY;"),
    "자동화에는 setup/doctor/demo/live 등 명시적 명령을 사용하세요.": ("자동화에는 setup/doctor/demo/live 등 명시적 명령을 사용하세요.", "For automation use explicit setup/doctor/demo/live commands."),
    "0..8 중 번호를 선택하세요.": ("0..8 중 번호를 선택하세요.", "Choose a number from 0 to 8."),
    "실행하지 못했습니다:": ("실행하지 못했습니다:", "Unable to run:"),
    "숨김 토큰 입력이 불가능하여 취소했습니다.": ("숨김 토큰 입력이 불가능하여 취소했습니다.", "Cancelled because hidden token input is unavailable."),
    "TTY를 확인하세요.": ("TTY를 확인하세요.", "Check the TTY."),
    "명령 또는 보고서 처리 실패.": ("명령 또는 보고서 처리 실패.", "Command or report processing failed."),
    "코어는 1번, ACE 평가/모델 실행 자산은 7번 준비 후 다시 확인하세요.": ("코어는 1번, ACE 평가/모델 실행 자산은 7번 준비 후 다시 확인하세요.", "Prepare core with option 1 and ACE evaluation/model assets with option 7, then retry."),
    "종료합니다.": ("종료합니다.", "Exiting."),
    "중단했습니다.": ("중단했습니다.", "Interrupted."),
    "Experiment report": ("실험 보고서", "Experiment report"),
    "Status": ("상태", "Status"),
    "Synthetic": ("합성", "Synthetic"),
    "Observed run wall time": ("실측 실행 시간", "Observed run wall time"),
    "Agent": ("Agent", "Agent"),
    "Harness": ("하네스", "Harness"),
    "Candidate": ("후보", "Candidate"),
    "Split": ("데이터 구분", "Split"),
    "Metrics": ("지표", "Metrics"),
    "Group comparison and completed evaluations": ("그룹 비교와 완료된 평가", "Group comparison and completed evaluations"),
    "Reserved trials": ("사용한 평가 예산", "Reserved trials"),
    "completed evaluations": ("완료된 평가", "completed evaluations"),
    "Trend": ("변화", "Trend"),
    "Completed": ("완료", "Completed"),
    "Passed": ("통과", "Passed"),
    "Failed": ("실패", "Failed"),
    "Metric": ("지표", "Metric"),
    "Baseline": ("기준 후보", "Baseline"),
    "Selected": ("선택 후보", "Selected"),
    "Delta": ("점수 차이", "Delta"),
    "Agent usage (Harness-reported partial; not complete totals)": ("Agent 사용량 (하네스 보고 일부, 전체 합계 아님)", "Agent usage (Harness-reported partial; not complete totals)"),
    "IO tokens": ("입출력 토큰", "IO tokens"),
    "Cost USD": ("비용 USD", "Cost USD"),
    "Optimization": ("최적화", "Optimization"),
    "Stage": ("단계", "Stage"),
    "Checkpoint": ("체크포인트", "Checkpoint"),
    "Optimizer usage": ("Optimizer 사용량", "Optimizer usage"),
    "Candidate changes: see this group's candidates/*/changes.diff.": ("후보 변경 내역: 이 그룹의 candidates/*/changes.diff를 확인하세요.", "Candidate changes: see this group's candidates/*/changes.diff."),
    "Structure": ("구조", "Structure"),
    "Failure": ("실패", "Failure"),
    "Run failure": ("실행 실패", "Run failure"),
    "not reported": ("기록되지 않음", "not reported"),
    "Reproducibility": ("재현 정보", "Reproducibility"),
    "Dataset": ("데이터셋", "Dataset"),
    "Datasets": ("데이터셋", "Datasets"),
    "Optimizers": ("Optimizer", "Optimizers"),
    "Benchmark SHA-256": ("벤치마크 SHA-256", "Benchmark SHA-256"),
    "Objective": ("목적 지표", "Objective"),
    "Budget": ("예산", "Budget"),
    "not recorded": ("기록 없음", "not recorded"),
    "Missing metrics are null, not zero. Empty usage lists mean unreported usage, not free execution.": ("미수집 지표는 0이 아닌 null입니다. 빈 사용량 목록은 무료 실행이 아니라 미보고를 뜻합니다.", "Missing metrics are null, not zero. Empty usage lists mean unreported usage, not free execution."),
    "Harness-reported usage can be partial. Compare only identical datasets, models and budgets.": ("하네스 보고 사용량은 일부일 수 있습니다. 같은 데이터셋·모델·예산의 실행만 비교하세요.", "Harness-reported usage can be partial. Compare only identical datasets, models and budgets."),
    "example environment": ("예제 환경", "example environment"),
    "dataset preparation": ("데이터셋 준비", "dataset preparation"),
    "실험 시작: 1. 기존 실험 실행  2. 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제  4. 이전 실행 보기": (
        "실험 시작: 1. 기존 실험 실행  2. 새 실험 만들고 실행  3. ACE-RTL + CVDP 예제  4. 이전 실행 보기",
        "Start an experiment: 1. Run an existing experiment  2. Create and run a new experiment  3. ACE-RTL + CVDP example  4. View previous runs"),
    "기존 실험·새 실험 실행 또는 이전 실행 보기(TTY 필요).": (
        "기존 실험·새 실험 실행 또는 이전 실행 보기(TTY 필요).",
        "Run an existing or new experiment, or view previous runs (TTY required)."),
    '저장소에서 시작: make setup-core. 기존 실험을 선택하려면 agent-opt tui의 "기존 실험 실행", 새 설정은 agent-opt init(대화형)을 사용하세요. 데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.': (
        '저장소에서 시작: make setup-core. 기존 실험을 선택하려면 agent-opt tui의 "기존 실험 실행", 새 설정은 agent-opt init(대화형)을 사용하세요. 데이터셋은 직접 선택하며 모델 없는 합성 예제는 README.md를 참고하세요.',
        'Start in the repository: make setup-core. Select an existing experiment with agent-opt tui or create a configuration with interactive agent-opt init. Choose datasets explicitly; see README.md for a synthetic example without a model.'),
    "선택 [1/2/3/4]: ": ("선택 [1/2/3/4]: ", "Choice [1/2/3/4]: "),
    "실행 기록이 없습니다.": ("실행 기록이 없습니다.", "No previous runs found."),
    "실행 번호 (0: 돌아가기): ": ("실행 번호 (0: 돌아가기): ", "Run number (0: back): "),
    "목록의 실행 번호를 선택하세요": ("목록의 실행 번호를 선택하세요", "Choose a listed run number"),
    "보고서를 안전하게 확인할 수 없습니다": ("보고서를 안전하게 확인할 수 없습니다", "Cannot safely verify the report"),
    "보고서 경로": ("보고서 경로", "Report path"),
    "ACE-RTL 작업공간 경로: ": ("ACE-RTL 작업공간 경로: ", "ACE-RTL workspace path: "),
    "ACE-RTL 작업공간 경로를 입력하세요": ("ACE-RTL 작업공간 경로를 입력하세요", "Enter an ACE-RTL workspace path"),
    "선택한 작업공간": ("선택한 작업공간", "Selected workspace"),
    "준비 작업: 고정 Git 소스·CVDP 데이터·driver·Docker 이미지": (
        "준비 작업: 고정 Git 소스·CVDP 데이터·driver·Docker 이미지",
        "Preparation: pinned Git sources, CVDP data, driver, Docker images"),
    "ACE-RTL 연동을 준비할까요? [y/N]: ": ("ACE-RTL 연동을 준비할까요? [y/N]: ",
                                           "Prepare the ACE-RTL integration? [y/N]: "),
    "실험 준비를 취소했습니다": ("실험 준비를 취소했습니다", "Experiment preparation cancelled"),
    "기존 experiment.toml 경로: ": ("기존 experiment.toml 경로: ", "Existing experiment.toml path: "),
    "최근 생성된 실험 설정 (번호 또는 경로 직접 입력):": (
        "최근 생성된 실험 설정 (번호 또는 경로 직접 입력):",
        "Recently created experiment configs (number or explicit path):"),
    "최근 생성 설정이 없습니다. 경로를 직접 입력하세요.": (
        "최근 생성 설정이 없습니다. 경로를 직접 입력하세요.", "No recent generated config; enter a path."),
    "목록의 설정 번호를 선택하세요": ("목록의 설정 번호를 선택하세요", "Choose a listed config number"),
    "실험 설정 경로를 입력하세요": ("실험 설정 경로를 입력하세요", "Enter an experiment configuration path"),
    "실험 설정": ("실험 설정", "Experiment config"),
    "계획 진단": ("계획 진단", "Plan readiness"),
    "실도구 진단": ("실도구 진단", "Tool readiness"),
    "준비됨": ("준비됨", "ready"),
    "준비 부족": ("준비 부족", "not ready"),
    "이 실험을 실행할까요? [y/N]: ": ("이 실험을 실행할까요? [y/N]: ", "Run this experiment? [y/N]: "),
    "실험 실행을 취소했습니다": ("실험 실행을 취소했습니다", "Experiment run cancelled"),
    "1, 2, 3 또는 4를 선택하세요": ("1, 2, 3 또는 4를 선택하세요", "Choose 1, 2, 3 or 4"),
    "데이터셋을 준비하고 실행할까요? [y/N]": ("데이터셋을 준비하고 실행할까요? [y/N]", "Prepare dataset and run? [y/N]"),
    "데이터셋을 준비하고 설정을 만들까요? [y/N]": ("데이터셋을 준비하고 설정을 만들까요? [y/N]", "Prepare dataset and create config? [y/N]"),
    "명령 하네스의 Agent argv: 인용을 분리하지만 셸 확장·파이프·리다이렉션은 실행하지 않음": (
        "명령 하네스의 Agent argv: 인용을 분리하지만 셸 확장·파이프·리다이렉션은 실행하지 않음",
        "Command harness Agent argv: split quotes without shell expansion, pipes, or redirection"),
    "기존 방식: Agent argv의 JSON 문자열 배열": ("기존 방식: Agent argv의 JSON 문자열 배열", "Legacy JSON string array for Agent argv"),
    "--agent와 --editable을 지정하세요": ("--agent와 --editable을 지정하세요", "Specify --agent and --editable"),
    "전용 하네스 프로필이 필요합니다. 기존 experiment.toml을 사용하세요": ("전용 하네스 프로필이 필요합니다. 기존 experiment.toml을 사용하세요", "A dedicated Harness profile is required; use an existing experiment.toml"),
    "Agent 실행 명령을 입력하세요": ("Agent 실행 명령을 입력하세요", "Enter an Agent execution command"),
    "입력이 종료되어 설정을 만들지 않았습니다": ("입력이 종료되어 설정을 만들지 않았습니다", "Input ended; configuration was not created"),
    "설정 만들기가 중단되었습니다": ("설정 만들기가 중단되었습니다", "Configuration creation interrupted"),
    "설정 생성": ("설정 생성", "Configuration created"),
    "다음": ("다음", "Next"),
    "결과 HTML": ("결과 HTML", "Result HTML"),
    "정적 계획 확인; 실행 성공 아님": ("정적 계획 확인; 실행 성공 아님", "Static plan check; not an execution result"),
    "계획 진단은 정적 검사입니다. Agent·채점기·모델 실행은 확인하지 않았습니다.": (
        "계획 진단은 정적 검사입니다. Agent·채점기·모델 실행은 확인하지 않았습니다.",
        "Plan diagnosis is static; Agent, scorer and model execution were not checked."),
    "--model은 모델 API 연결을 호출하지만 Agent 실행 성공은 확인하지 않습니다.": (
        "--model은 모델 API 연결을 호출하지만 Agent 실행 성공은 확인하지 않습니다.",
        "--model calls the model API but does not verify Agent execution."),
    "저장된 자료로 재생성할 때만": (
        "저장된 자료로 재생성할 때만", "Only when rebuilding from stored data"),
    "각 데이터셋의 계획 진단": ("각 데이터셋의 계획 진단", "check each dataset plan"),
    "final doctor": ("최종 진단", "final doctor"),
    "minimal demo": ("최소 데모", "minimal demo"),
    "starting": ("시작", "starting"),
    "complete": ("완료", "complete"),
    "failed": ("실패", "failed"),
    "read-only": ("읽기 전용", "read-only"),
    "logs": ("로그", "logs"),
    "output": ("출력", "output"),
    "results": ("결과", "results"),
    "inspect the command output above. If dependencies are missing, run sh scripts/bootstrap.sh setup --core.": (
        "위 명령 출력을 확인하세요. 의존성이 없으면 sh scripts/bootstrap.sh setup --core를 실행하세요.",
        "inspect the command output above. If dependencies are missing, run sh scripts/bootstrap.sh setup --core."),
    "trial_started": ("평가 시작", "trial started"),
    "waiting for events": ("이벤트 대기 중", "waiting for events"),
    "trial_completed": ("평가 완료", "trial completed"),
    "agent_started": ("Agent 실행 시작", "Agent execution started"),
    "evaluation_started": ("채점 시작", "evaluation started"),
    "optimizer_iteration_started": ("Optimizer 반복 시작", "optimizer iteration started"),
    "optimizer_iteration_completed": ("Optimizer 반복 완료", "optimizer iteration completed"),
    "optimizer_review_started": ("Optimizer 검토 시작", "optimizer review started"),
    "optimizer_merge_started": ("후보 병합 시작", "candidate merge started"),
    "optimizer_merge_completed": ("후보 병합 완료", "candidate merge completed"),
    "stage_started": ("단계 시작", "stage started"),
    "stage_completed": ("단계 완료", "stage completed"),
    "candidate_created": ("후보 생성", "candidate created"),
    "candidate_evaluated": ("후보 평가 완료", "candidate evaluated"),
    "stage_budget_exhausted": ("단계 예산 소진", "stage budget exhausted"),
    "budget_exhausted": ("평가 예산 소진", "trial budget exhausted"),
    "source_error": ("Agent 소스 오류", "Agent source error"),
    "error": ("오류", "error"),
    "interrupted": ("중단", "interrupted"),
    "rerank is deferred; configure the objective for a new run. Stored reports and frozen selections remain available; see deferred/README.md": (
        "rerank는 보류 중입니다. 새 실행의 objective를 설정하세요. 저장된 보고서와 고정 선택 결과는 그대로 볼 수 있습니다. deferred/README.md를 참고하세요.",
        "rerank is deferred; configure the objective for a new run. Stored reports and frozen selections remain available; see deferred/README.md"),
    "pinned sources": ("고정 소스", "pinned sources"),
    "verified dataset": ("검증된 데이터셋", "verified dataset"),
    "evaluation image": ("평가 이미지", "evaluation image"),
    "agent image": ("Agent 이미지", "agent image"),
    "example tool checks": ("예제 도구 검사", "example tool checks"),
    "checkout": ("체크아웃", "checkout"),
    "cache": ("캐시", "cache"),
    "log": ("로그", "log"),
    "terminal": ("터미널", "terminal"),
    "verify cached": ("캐시 검증", "verify cached"),
    "build": ("빌드", "build"),
    "코어 도구만 준비·진단; Docker/ACE 제외(--dataset/--platform/--model과 함께 사용 불가)": ("코어 도구만 준비·진단; Docker/ACE 제외(--dataset/--platform/--model과 함께 사용 불가)", "Prepare or diagnose core tools only; excludes Docker/ACE (cannot combine with --dataset/--platform/--model)"),
    "등록 데이터셋 하나 준비(--core/--platform/--model과 함께 사용 불가)": ("등록 데이터셋 하나 준비(--core/--platform/--model과 함께 사용 불가)", "Prepare one registered dataset (cannot combine with --core/--platform/--model)"),
    "등록 데이터셋 하나 진단, 읽기 전용(--core/--platform/--model과 함께 사용 불가)": ("등록 데이터셋 하나 진단, 읽기 전용(--core/--platform/--model과 함께 사용 불가)", "Read-only check of one registered dataset (cannot combine with --core/--platform/--model)"),
    "기본값: Docker daemon의 기본 플랫폼": ("기본값: Docker daemon의 기본 플랫폼", "Default: the Docker daemon's platform"),
    "검증된 캐시 자산만 재사용; 다운로드·빌드 없음": ("검증된 캐시 자산만 재사용; 다운로드·빌드 없음", "Reuse verified cached assets only; no download or build"),
    "단일 JSON 진단 결과 출력": ("단일 JSON 진단 결과 출력", "Print one JSON diagnostic result"),
    "호스트 API와 컨테이너 OpenCode 도구를 명시적으로 호출": ("호스트 API와 컨테이너 OpenCode 도구를 명시적으로 호출", "Explicitly call the host API and container OpenCode tool"),
    "최적화 반복 횟수 지정(1..20, 기본값 3)": ("최적화 반복 횟수 지정(1..20, 기본값 3)", "Set optimization iterations (1..20; default 3)"),
    "여러 Agent의 최적화 실험을 위한 작업 도구": ("여러 Agent의 최적화 실험을 위한 작업 도구", "Optimization experiments for multiple Agents"),
    '저장소에서 시작: make setup ARGS="--core" 후 agent-opt datasets list로 데이터셋을 확인하세요. 대화형은 agent-opt tui(TTY 필요), 비대화형은 agent-opt init --help를 사용합니다. 모델 없는 합성 예제는 README.md를 참고하세요.': (
        '저장소에서 시작: make setup ARGS="--core" 후 agent-opt datasets list로 데이터셋을 확인하세요. 대화형은 agent-opt tui(TTY 필요), 비대화형은 agent-opt init --help를 사용합니다. 모델 없는 합성 예제는 README.md를 참고하세요.',
        'Start with make setup ARGS="--core", then agent-opt datasets list. For interactive setup use agent-opt tui (TTY required); for noninteractive setup use agent-opt init --help. See README.md for an example without a model.'),
    "데이터셋 목록 표시 및 명시적으로 선택한 데이터셋 준비": ("데이터셋 목록 표시 및 명시적으로 선택한 데이터셋 준비", "List datasets and prepare the selected dataset"),
    "구현된 연동 목록 표시.": ("구현된 연동 목록 표시.", "List implemented integrations."),
    "도구·선택 데이터셋·실험 계획의 준비 상태 진단. --dataset/--plan은 읽기 전용.": ("도구·선택 데이터셋·실험 계획의 준비 상태 진단. --dataset/--plan은 읽기 전용.", "Check tool, dataset, or experiment readiness. --dataset/--plan are read-only."),
    "등록 데이터셋 목록 표시.": ("등록 데이터셋 목록 표시.", "List registered datasets."),
    "직접 선택한 데이터셋 준비.": ("직접 선택한 데이터셋 준비.", "Prepare the selected dataset."),
    "직접 선택한 데이터셋으로 실험 설정 생성.": ("직접 선택한 데이터셋으로 실험 설정 생성.", "Create an experiment using a selected dataset."),
    "대화형 설정 및 실행 진행 상황 표시(TTY 필요).": ("대화형 설정 및 실행 진행 상황 표시(TTY 필요).", "Configure interactively and show live progress (TTY required)."),
    "선택한 데이터셋마다 독립 평가기로 실행.": ("선택한 데이터셋마다 독립 평가기로 실행.", "Run each selected dataset with its own evaluator."),
    "독립 등록된 Agent 대상 목록 표시.": ("독립 등록된 Agent 대상 목록 표시.", "List registered Agent targets."),
    "준비된 실험 설정과 연동 계약 검사.": ("준비된 실험 설정과 연동 계약 검사.", "Validate the experiment and integration contracts."),
    "실행 없이 실험 조합 확인.": ("실행 없이 실험 조합 확인.", "Inspect experiment combinations without running."),
    "준비된 실험 실행 및 보고서 작성.": ("준비된 실험 실행 및 보고서 작성.", "Run an experiment and write reports."),
    "실행 요약 확인 또는 HTML 재생성.": ("실행 요약 확인 또는 HTML 재생성.", "Show a run summary or regenerate HTML."),
    "기계가 읽을 수 있는 단일 진단 결과 출력": ("기계가 읽을 수 있는 단일 진단 결과 출력", "Print one machine-readable diagnostic result"),
    "--plan 필요; 모델 API를 명시적으로 호출": ("--plan 필요; 모델 API를 명시적으로 호출", "Requires --plan; calls the model API explicitly"),
    "등록된 데이터셋 ID 또는 로컬 tasks.json": ("등록된 데이터셋 ID 또는 로컬 tasks.json", "Registered dataset ID or local tasks.json"),
    "로컬 tasks.json에는 필수: file.py:Symbol": ("로컬 tasks.json에는 필수: file.py:Symbol", "Required for local tasks.json: file.py:Symbol"),
    "검증된 캐시 자산만 재사용": ("검증된 캐시 자산만 재사용", "Reuse only verified cached assets"),
    "로컬 소스 경로 또는 Git URL(Git이면 --revision 지정)": ("로컬 소스 경로 또는 Git URL(Git이면 --revision 지정)", "Local source path or Git URL (requires --revision)"),
    "대시(-)로 시작하는 Agent 옵션도 포함하는 JSON 인수 배열": ("대시(-)로 시작하는 Agent 옵션도 포함하는 JSON 인수 배열", "JSON argv array, including Agent options starting with -"),
    "수정 허용 Agent 경로/패턴(반복 가능)": ("수정 허용 Agent 경로/패턴(반복 가능)", "Editable Agent path/pattern (repeatable)"),
    "데이터셋 직접 선택: 등록 ID 또는 로컬 tasks.json(반복 가능)": ("데이터셋 직접 선택: 등록 ID 또는 로컬 tasks.json(반복 가능)", "Select a dataset ID or local tasks.json (repeatable)"),
    "등록된 Optimizer ID(반복 가능; 기본값: gepa)": ("등록된 Optimizer ID(반복 가능; 기본값: gepa)", "Registered Optimizer ID (repeatable; default: gepa)"),
    "TTY 없이 준비를 확인하고 진행": ("TTY 없이 준비를 확인하고 진행", "Confirm preparation without a TTY"),
    "독립 HTML 보고서 재생성": ("독립 HTML 보고서 재생성", "Regenerate the standalone HTML report"),
}

# 보고서의 고정 UI 문구만 번역합니다. 평가 근거/사용자 데이터는 이 목록을 거치지 않습니다.
_REPORT_EN = {
    "Agent × 하네스": "Agent × Harness",
    "Agent와 실행 하네스를 짝지어 평가한 조합입니다.": "An Agent and Harness evaluated together.",
    "검증으로 후보를 고른 뒤에만 확인하는 별도 데이터입니다. 탐색에 사용하지 않습니다.": "Held-out data checked only after candidate selection; never used for search.",
    "후보": "Candidate", "원본 Agent의 스냅샷을 바탕으로 만든 변경 버전입니다.": "A changed version of the original Agent's snapshot.",
    "선택 후보": "Selected candidate", "검증 결과에 따라 선택된 변경 버전입니다.": "The candidate selected using validation results.",
    "평가 횟수": "Evaluation count", "한 후보를 한 과제에 실행해 평가한 건수입니다.": "Number of evaluated tasks for this candidate.",
    "예산": "Budget", "실험에서 허용한 평가 횟수와 실행 시간의 상한입니다.": "Limits on trials and run time.",
    "점수 차이": "Score difference", "선택 후보 점수에서 기준 후보 점수를 뺀 값입니다.": "Selected candidate score minus baseline score.",
    "퍼센트포인트: 두 비율의 차이를 백분율 단위로 나타낸 값입니다.": "Percentage points: the difference between two percentages.",
    "단계": "Stage", "각 Optimizer가 기준 후보에서 시작해 독립적으로 탐색하는 구간입니다.": "Each Optimizer explores independently from the baseline.",
    "체크포인트": "Checkpoint", "Optimizer가 단계 실행 중 기록한 원본 상태입니다.": "Recorded original state of the Optimizer stage.",
    "사용량": "Usage", "기록된 실행 비용과 토큰입니다. 값이 없으면 전체 사용량을 알 수 없습니다.": "Recorded cost and tokens; missing values do not imply zero total usage.",
    "하네스": "Harness", "Agent 실행과 결과 수집을 연결하는 구성 요소입니다.": "Connects Agent execution to result collection.",
    "기록 없음": "Not reported", "평가 기록 없음": "Not evaluated", "회": " trials",
    "초 총 실행 제한": "s wall limit", "초/평가": "s/trial", "초": "s",
    "벤치마크 ID": "Benchmark ID", "벤치마크 경로": "Benchmark path", "목적 지표": "Objective",
    "선택 방식": "Selection mode", "유지 후보 수=": "keep=", "실행 ID": "Run ID",
    "실측 실행 시간": "Observed run wall time", "높을수록 좋음": "maximize", "낮을수록 좋음": "minimize",
    "우선순위 순서": "lexicographic", "평균": "mean", "합계": "sum",
    "검증에서 선택된 후보: ": "Selected on validation: ",
    "기록된 선택 (유효한 검증 결과 아님): ": "Recorded selection (not valid validation): ",
    "검증 선택 결과: ": "Validation selection: ", "선택된 후보 없음": "No candidate selected",
    "완료": "Completed", "통과": "Passed", "실패": "Failed", "건 · ": " · ", "건": " evaluations",
    "검증 · 기준 후보 → 선택 후보": "Validation · baseline → selected",
    "지표": "Metric", "방향": "Direction", "변화": "Trend",
    "검증으로 후보를 확정한 뒤 기록한 테스트입니다. 탐색에는 사용하지 않으며 Agent × 하네스 그룹별 점수를 따로 보여줍니다.": "Held-out test recorded after validation selection; not used during search. Scores are reported separately by Agent × Harness group.",
    "최종 테스트 · 기록된 집계": "Held-out test · recorded aggregates",
    "그룹": "Group", "데이터 구분": "Split", "테스트": "test", "학습": "train",
    "기록된 탐색 구조가 없습니다. 아래 평가 표를 확인하세요.": "No search structure recorded. See evaluations below.",
    "기록된 그룹 이벤트를 로그 순서로 보여줍니다. 나머지 필드는 원본 기록에서 확인하세요.": "Recorded group events in log order. See the original event for remaining fields.",
    "기록된 탐색 구조가 없어 그룹 이벤트를 로그 순서로 보여줍니다. 나머지 필드는 원본 기록에서 확인하세요.": "No search structure recorded; group events are shown in log order. See the original event for remaining fields.",
    "시각": "Time", "작업": "Phase", "과제": "Task", "이벤트 원본": "Original event",
    "그룹 이벤트 기록 · 원본 근거": "Recorded group events · original evidence",
    "기록된 근거": "Recorded evidence", "반복": "Iteration", "상위 단위": "Parent unit",
    "평가 참조": "Evaluation references", "기록된 후보 부모 관계": "Recorded candidate parents",
    "피드백 전체 · ": "Full feedback · ", "표준 출력 로그": "stdout log", "표준 오류 로그": "stderr log",
    "한 행은 한 과제의 평가 기록입니다. 과제별 지표는 전체 점수가 아닙니다.": "Each row is one task evaluation. Per-task metrics are not overall scores.",
    "기록된 평가": "Recorded evaluations", "평가 ID": "Evaluation ID", "상태 / 원인": "Status / cause",
    "관측 지표": "Observed metrics", "피드백 / 로그": "Feedback / logs",
    "후보 변경 내역": "Candidate changes", "기록된 선택과 후보": "Recorded selections and candidates",
    "부모 후보": "Parent candidate", "생성 주체": "Producer", "변경 파일": "Changed files",
    "스냅샷 묶음": "Snapshot bundle", "변경 사항 미리보기": "Diff preview",
    "기록된 후보 파일 없음": "No recorded candidate files", "평가 이력": "Evaluation history",
    "검증에서 선택": "Selected on validation", "기록된 선택 · 유효한 검증 결과 아님": "Recorded selection · not valid validation",
    "집계": "aggregate", "건의 평가": "evaluations", "기록된 후보": "Recorded candidate",
    "실행 중단": "Run stopped", "실행 오류 원문": "Original run error",
    "실패 메시지 원문": "Original failure message", "분류된 실패 기록 없음": "No classified failures recorded",
    "실측 단계 실행 시간": "Observed stage wall time", "단계별 검증 선택 집계": "Selected validation aggregates by stage",
    "단계 평가 집계 및 체크포인트 원본": "Stage evaluation aggregates and original checkpoint",
    "단계별 평가 집계": "Stage evaluation aggregates",
    "Optimizer 사용량은 단계별 관측값입니다. 하네스가 보고한 Agent 사용량은 예상된 모든 유효 평가의 값이 있을 때만 전체값이며, 빠진 값은 미수집입니다.": "Optimizer usage is observed per stage. Harness-reported Agent usage is complete only when every expected valid evaluation reports a value; missing values are uncollected.",
    "Agent 사용량 (하네스 보고)": "Agent usage (Harness-reported)",
    "Optimizer 사용량": "Optimizer usage", "벤치마크 SHA-256": "Benchmark SHA-256",
    "재현 정보와 출처": "Reproducibility & provenance", "실험 설정 원본": "Original experiment configuration",
    "소스 고정 버전 · 모델 · 플러그인 해시 원본": "Original source locks, models, and plugin hashes",
    "벤치마크": "Benchmark", "목적 지표 · 우선순위": "Objectives · priority order",
    "검증 집계와 실행 건수 · 상세": "Validation aggregates and evaluation counts · details",
    "기록된 탐색 구조가 없습니다. 이벤트 순서와 원본은 아래에서 확인하세요.": "No search structure recorded. Open the events below for original evidence.",
    "설정 개요 · 식별자와 실행 근거": "Configuration · identifiers and run evidence",
    "비교 가능한 검증 선택 없음": "No comparable validation selection",
    "기준": "baseline", "검증 경로 보기 →": "View validation journey →",
    "예약된 평가": "Reserved trials", "실측 벽시계": "Observed wall time",
    "실험 요약": "Run summary", "최적화 결과": "Optimization result",
    "그룹별 검증 선택을 독립적으로 표시합니다. 점수가 없는 경우 0으로 간주하지 않습니다.": "Validation selections are shown separately by group; missing scores are not zero.",
    "기록된 그룹 없음": "No groups recorded", "실패 상세": "Failure details",
    "미해결": "unsolved", "반복 결과 혼합": "mixed repeats", "미확인": "unknown",
    "시간 초과": "timeout", "실행 환경 오류": "infrastructure error", "실행 오류": "execution error",
    "실험 오류": "run error", "채점 실패": "scored failure", "미지원": "unsupported",
    "중단": "interrupted", "무효": "invalid", "최고점 갱신": "best updated",
    "동률": "equal", "최고점 미달": "below best", "첫 관측": "first observed",
    "평가 없음": "not evaluated", "점수 미기록": "score not recorded",
    "마지막 최고점 갱신: 후보 평가": "Last best update: candidate evaluation",
    "이후": "Followed by", "건의 후보 평가에서 갱신 없음.": " candidate evaluations without improvement.",
    "첫 후보 평가 이후 {count}건에서 최고점 갱신 없음.": "No best-score update across {count} candidate evaluations after the first.",
    "나머지 후보 평가": "Additional candidate evaluations:",
    "검증 집계": "Validation aggregates", "최적화 개선 추이": "Optimization progress",
    "동일 그룹의 후보별 검증 집계만 비교합니다. 점은 후보 점수, 계단선은 지금까지의 최고점입니다. 최종 선택은 별도로 표시합니다.": "Compare candidate validation aggregates within one group only. Dots are candidate scores, the step line is best-so-far; final selection is marked separately.",
    "검증 점수 추이": "Validation score progression",
    "후보 점수와 누적 최고점; 아래 목록에 각 후보의 실제 값과 선택 상태가 있습니다.": "candidate scores and best-so-far; the list below gives exact values and selection states.",
    "후보 평가 순서 →": "Candidate evaluation order →", "후보 점수": "Candidate score",
    "최고점": "Best-so-far", "기준 점수": "Baseline score", "단계 경계": "Stage boundary",
    "최종 선택": "Final selection", "확정된 선택": "Final selection",
    "기준 후보와 최종 선택": "Baseline vs selected candidate",
    "↑ 높을수록 좋음": "↑ maximize", "↓ 낮을수록 좋음": "↓ minimize",
    "비교 막대에 필요한 유효한 비음수 값이 없습니다.": "No comparable nonnegative values for bars.",
    "동일 그룹의 기준 후보와 검증에서 최종 선택된 후보입니다. 막대는 각 지표 내에서만 비교합니다.": "Compare the baseline and the final validation selection within one group. Each metric has its own bar scale.",
    "다중 지표": "Multiple objectives", "목적 지표 관계": "Objective trade-off",
    "후보별 검증 값입니다. 두 지표는 우선순위 순서로 선택하며, 두 축의 교환 관계만 표시합니다.": "Candidate validation values. Selection remains lexicographic; this plot shows the relationship between two metrics.",
    "와": "and", "후보 관계; 기준은 빈 원, 선택은 강조 원": "candidate relationship; baseline is hollow, selected is filled",
    "후보별 목적 지표 관계": "Candidate objective relationship",
    "점의 실제 수치는 아래 후보 점수 목록에서 확인합니다.": "Exact point values appear in the candidate list below.",
    "세로축:": "Vertical axis:", "진한 원: 최종 선택 · 빈 원: 기준 후보": "Filled dot: final selection · hollow dot: baseline",
    "후보 계보": "Candidate lineage", "선택 후보까지의 경로": "Path to selected candidate",
    "기록된 부모 관계의 한 경로만 표시합니다. 병합·다른 후보의 관계는 아래 최적화 과정과 후보 변경 내역에서 확인할 수 있습니다.": "Only one recorded parent path is shown. Inspect the journey and candidate changes below for merges and other branches.",
    "이 경로 외 기록된 후보": "Other recorded candidates:", "개": " more",
    "반복 ": "Iteration ", "외": "plus", "개 후보": " candidates",
    "연결된 후보 미기록": "No candidates linked", "나머지 탐색 단위": "Additional search units:",
    "탐색 단위": "Search units", "탐색 흐름": "Search trail",
    "Optimizer가 명시적으로 기록한 반복·세대·단계의 순서입니다. 후보 점수는 기록된 검증 집계가 있을 때만 표시합니다.": "Recorded iteration, generation, and phase order. Candidate scores appear only when validation aggregates were recorded.",
    "새로 해결": "newly solved", "해결 후 미해결": "previously solved, now unsolved",
    "과제별 변화": "Task changes", "과제별 전후 비교": "Task-level comparison",
    "같은 검증 과제 {tasks}개 중 새로 해결 {fixed}개, 해결 후 미해결 {lost}개.": "Across {tasks} shared validation tasks: {fixed} newly solved, {lost} newly unsolved.",
    "검증 과제 · 기준 후보 → 최종 선택": "Validation tasks · baseline → final selection",
    "나머지 평가": "Additional evaluations:", "실행 진단": "Execution diagnostics",
    "평가 실행 시간": "Trial execution time",
    "막대는 실제 과제 실행 시간이며 후보 점수와 별개입니다. 미측정 시간은 빈 막대로 표시합니다.": "Bars show observed task duration, not candidate scores. Missing durations have no bar.",
    "결과 분포": "Outcome distribution", "평가 결과 분포": "Trial outcomes",
    "과제별 평가 기록의 상태 분류입니다. 후보 단위 개선 건수와 다릅니다.": "Task evaluation outcomes; these counts are not candidate improvements.",
}
for _ko, _en in _REPORT_EN.items():
    MESSAGES.setdefault(_ko, (_ko, _en))

_DEVELOPMENT_KO = {
    "Next:": "다음:",
    "Log:": "로그:",
    "Then rerun offline with:": "그 다음 오프라인으로 다음 명령을 다시 실행하세요:",
    "Cause:": "원인:",
    "Blocked by:": "선행 검사:",
    "Fix:": "해결:",
    "Retry:": "재실행:",
    "Host OS and diagnostic Python compatibility (Mac/Linux, Python >=3.11).": "호스트 OS와 진단 Python 호환성 (Mac/Linux, Python >=3.11).",
    "Use Mac or Ubuntu with Python >=3.11; run sh scripts/bootstrap.sh setup.": "Python >=3.11을 지원하는 Mac 또는 Ubuntu에서 sh scripts/bootstrap.sh setup을 실행하세요.",
    "Use Mac or Ubuntu with Python >=3.11; run sh scripts/bootstrap.sh setup --core.": "Python >=3.11을 지원하는 Mac 또는 Ubuntu에서 sh scripts/bootstrap.sh setup --core를 실행하세요.",
    "example environment": "예제 환경",
    "ACE-RTL source checkout": "ACE-RTL 소스 checkout",
    "cvdp_benchmark source checkout": "cvdp_benchmark 소스 checkout",
    "ACE-RTL source verification": "ACE-RTL 소스 검증",
    "cvdp_benchmark source verification": "cvdp_benchmark 소스 검증",
    "driver requirements lock": "driver requirements lock 검증",
    "driver lock validation": "CVDP driver lock 검증",
    "environment lock validation": "ACE environment lock 검증",
    "CVDP evaluation lock validation": "CVDP evaluation lock 검증",
    "CVDP dataset lock validation": "CVDP dataset lock 검증",
    "CVDP evaluation image identity": "CVDP evaluation image identity 검증",
    "CVDP driver package lock": "CVDP driver package lock 검증",
    "CVDP imported task provenance": "CVDP imported task provenance 검증",
    "evaluation image identity": "evaluation image identity 검증",
    "uv installer": "uv 설치 프로그램",
    "project dependency sync": "프로젝트 의존성 동기화",
    "offline project dependency sync": "프로젝트 오프라인 의존성 동기화",
    "project Python validation": "프로젝트 Python 검증",
    "Python dispatch": "Python 실행 전달",
    "existing project .venv validation": "기존 프로젝트 .venv 검증",
    "driver Python validation": "CVDP driver Python 검증",
    "driver package inspection": "driver package 검사",
    "Docker platform detection": "Docker platform 검사",
    "evaluation image inspection": "평가 이미지 검사",
    "agent image inspection": "Agent 이미지 검사",
    "example tool verification": "예제 도구 검증",
    "minimal demo": "최소 데모",
    "dataset download": "데이터셋 다운로드",
    "dataset cache": "데이터셋 cache",
    "Verilog-Eval image cache": "Verilog-Eval 이미지 cache",
    "Verilog-Eval evaluation image build": "Verilog-Eval 평가 이미지 빌드",
    "Verilog-Eval image inspection": "Verilog-Eval 이미지 검사",
    "Verilog-Eval Icarus v12 runtime": "Verilog-Eval Icarus v12 실행환경",
    "Verilog-Eval simulator verification": "Verilog-Eval simulator 검증",
    "Check network, proxy, and CA trust settings.": "네트워크, proxy 및 CA trust 설정을 확인하세요.",
    "Inspect the log cause and repair uv installation or execution permissions.": "로그 원인을 확인하고 uv 설치 또는 실행 권한을 수정하세요.",
    "Check Python, uv, and the frozen dependency lock.": "Python, uv와 고정 의존성 lock을 확인하세요.",
    "Prepare the missing package cache with online setup first.": "먼저 online setup으로 누락된 package cache를 준비하세요.",
    "Check Python 3.11+ installation and project .venv execution permissions.": "Python 3.11+ 설치와 프로젝트 .venv 실행 권한을 확인하세요.",
    "Preserve and move the existing .venv aside, then rerun setup.": "기존 .venv를 보존해 옮긴 뒤 setup을 다시 실행하세요.",
    "Check Git, network access, and the pinned source commit.": "Git·네트워크 접근과 고정 source commit을 확인하세요.",
    "Check source availability and preserve the pinned commit.": "source 접근성을 확인하고 고정 commit을 보존하세요.",
    "Preserve the cache and repair the pinned source checkout.": "cache를 보존하고 고정 source checkout을 복구하세요.",
    "Prepare the pinned source checkout while online before using offline mode.": "offline 모드 전에 online으로 고정 source checkout을 준비하세요.",
    "Repair the command, access, or selected environment input.": "명령·접근 권한 또는 선택한 환경 입력을 수정하세요.",
    "Repair the reported tool, network, permission, or pinned input issue.": "표시된 도구·네트워크·권한 또는 고정 입력 문제를 수정하세요.",
    "Prepare the pinned dataset asset while online before using offline mode.": "offline 모드 전에 online으로 고정 데이터셋 자산을 준비하세요.",
    "Check write permission for the selected dataset cache directory.": "선택한 데이터셋 cache 디렉터리의 쓰기 권한을 확인하세요.",
    "Check Docker daemon access and rebuild the pinned evaluation image.": "Docker daemon 접근을 확인하고 고정 평가 이미지를 다시 빌드하세요.",
    "Rebuild the pinned evaluation image for the locked platform.": "고정 평가 이미지를 lock의 platform으로 다시 빌드하세요.",
    "Rebuild the pinned evaluation image and verify its simulator versions.": "고정 평가 이미지를 다시 빌드하고 simulator 버전을 확인하세요.",
    "Confirm the CVDP driver environment and uv cache are available.": "CVDP driver 환경과 uv cache를 확인하세요.",
    "Check Docker daemon access and restore the pinned image identity.": "Docker daemon 접근을 확인하고 고정 image identity를 복구하세요.",
    "Restore the pinned image identity for the selected platform.": "선택한 platform에 맞는 고정 image identity를 복구하세요.",
    "Build the image for the selected Docker platform.": "선택한 Docker platform으로 이미지를 빌드하세요.",
    "Repair the reported driver, simulator, or OpenCode tool issue.": "표시된 driver·simulator·OpenCode 도구 문제를 수정하세요.",
    "Check Docker build trust/registry access and preserve the pinned Dockerfile.": "Docker build trust와 registry 접근을 확인하고 고정 Dockerfile을 보존하세요.",
    "Review the upstream requirements and recompile the pinned CVDP driver lock.": "upstream requirements를 검토하고 고정 CVDP driver lock을 다시 생성하세요.",
    "Restore the pinned CVDP driver lock with online setup.": "online setup으로 고정 CVDP driver lock을 복구하세요.",
    "Restore the prepared CVDP driver packages with online setup.": "online setup으로 준비된 CVDP driver package를 복구하세요.",
    "Run online setup with the selected CA bundle to rebuild and pin the images.": "선택한 CA bundle로 online setup을 실행해 이미지를 다시 만들고 고정하세요.",
    "Run online setup for the selected platform to build and pin the ACE images.": "선택한 platform으로 online setup을 실행해 ACE 이미지를 다시 만들고 고정하세요.",
    "Build the image for the selected Docker platform with online setup before offline retry.": "offline 재시도 전에 선택한 Docker platform으로 online setup을 실행해 이미지를 빌드하세요.",
    "Run online CVDP setup with the selected platform and CA bundle before offline retry.": "offline 재시도 전에 선택한 platform과 CA bundle로 online CVDP setup을 실행하세요.",
    "Run online CVDP setup to restore the pinned dataset lock.": "online CVDP setup으로 고정 데이터셋 lock을 복구하세요.",
    "Run online CVDP setup to rebuild and pin the evaluation image for this platform.": "online CVDP setup으로 현재 platform의 평가 이미지를 다시 만들고 고정하세요.",
    "Run online CVDP setup to restore the pinned driver packages.": "online CVDP setup으로 고정 driver package를 복구하세요.",
    "Run online setup to rebuild and pin the evaluation image for the selected platform.": "선택한 platform으로 online setup을 실행해 평가 이미지를 다시 만들고 고정하세요.",
    "Run online setup to rebuild and pin the agent image for the selected platform.": "선택한 platform으로 online setup을 실행해 Agent 이미지를 다시 만들고 고정하세요.",
    "Run online CVDP setup to restore pinned imported-task provenance before retrying offline.": "offline 재시도 전에 online CVDP setup으로 고정 imported task provenance를 복구하세요.",
    "Rebuild the selected CVDP image for the expected platform.": "선택한 CVDP 이미지를 기대 platform으로 다시 빌드하세요.",
    "Check Docker daemon access and rebuild the selected CVDP image.": "Docker daemon 접근을 확인하고 선택한 CVDP 이미지를 다시 빌드하세요.",
    "Rebuild the selected CVDP image and preserve the expected platform.": "선택한 CVDP 이미지를 다시 빌드하고 기대 platform을 보존하세요.",
    "Check Docker daemon access and rebuild the selected CVDP image. Run online CVDP setup to rebuild and pin the selected image before offline retry.": "Docker daemon 접근을 확인하고 선택한 CVDP 이미지를 다시 빌드하세요. offline 재시도 전에 online CVDP setup으로 선택한 이미지를 다시 만들고 고정하세요.",
    "Rebuild the selected CVDP image for the expected platform. Run online CVDP setup to rebuild and pin the selected image before offline retry.": "선택한 CVDP 이미지를 기대 platform으로 다시 빌드하세요. offline 재시도 전에 online CVDP setup으로 선택한 이미지를 다시 만들고 고정하세요.",
    "Check Docker daemon access and rebuild the pinned evaluation image. Run online CVDP setup to rebuild and pin the evaluation image before offline retry.": "Docker daemon 접근을 확인하고 고정 평가 이미지를 다시 빌드하세요. offline 재시도 전에 online CVDP setup으로 평가 이미지를 다시 만들고 고정하세요.",
    "Rebuild the pinned evaluation image and verify its simulator versions. Run online CVDP setup to rebuild and pin the evaluation image before offline retry.": "고정 평가 이미지를 다시 빌드하고 simulator 버전을 확인하세요. offline 재시도 전에 online CVDP setup으로 평가 이미지를 다시 만들고 고정하세요.",
    "Prepare and verify the pinned Icarus v12 image while online before offline use.": "offline 사용 전에 online으로 고정 Icarus v12 이미지를 준비하고 검증하세요.",
    "Check Docker daemon access and restore the pinned Icarus v12 image.": "Docker daemon 접근을 확인하고 고정 Icarus v12 이미지를 복구하세요.",
    "Restore the pinned Icarus v12 image identity.": "고정 Icarus v12 image identity를 복구하세요.",
    "Check Docker daemon access and the pinned Icarus v12 runtime.": "Docker daemon 접근과 고정 Icarus v12 실행환경을 확인하세요.",
    "Rebuild and verify the pinned Icarus v12 image.": "고정 Icarus v12 이미지를 다시 빌드하고 검증하세요.",
    "Inspect the setup log, repair the failed stage, and retry.": "setup 로그를 확인하고 실패 단계를 수정한 뒤 다시 실행하세요.",
    "Inspect the complete doctor report and repair the failing environment checks.": "전체 doctor 보고서를 확인하고 실패한 환경 검사를 수정하세요.",
    "Repair the failing readiness check.": "준비 상태 검사에서 표시한 원인을 수정하세요.",
    "Check the setup options and required configuration.": "setup 옵션과 필요한 설정을 확인하세요.",
    "Repair or complete the interrupted setup step.": "중단된 setup 단계를 수정하거나 완료하세요.",
    "final readiness report is not ready": "최종 준비 상태 검사에서 해결되지 않은 항목이 있습니다",
    "Host git executable.": "호스트 Git 실행 파일을 사용할 수 있습니다.",
    "Host uv executable.": "호스트 uv 실행 파일을 사용할 수 있습니다.",
    "Install Git: Mac: xcode-select --install; Ubuntu: sudo apt install git.": "Git 설치: Mac: xcode-select --install; Ubuntu: sudo apt install git.",
    "Run sh scripts/bootstrap.sh setup (or python3 scripts/dev.py setup).": "sh scripts/bootstrap.sh setup(또는 python3 scripts/dev.py setup)을 실행하세요.",
    "Run sh scripts/bootstrap.sh setup --core (or python3 scripts/dev.py setup --core).": "sh scripts/bootstrap.sh setup --core(또는 python3 scripts/dev.py setup --core)를 실행하세요.",
    "Project .venv Python >=3.11.": "프로젝트 .venv에 Python >=3.11이 있습니다.",
    "Interpreter belongs to the project virtualenv.": "인터프리터가 프로젝트 가상환경에 속합니다.",
    "Installed project package in .venv.": "프로젝트 패키지가 .venv에 설치되어 있습니다.",
    "Installed agent-opt executable.": "agent-opt 실행 파일이 설치되어 있습니다.",
    "Project ruff development tool.": "프로젝트 Ruff 개발 도구가 있습니다.",
    "Project build development tool.": "프로젝트 build 개발 도구가 있습니다.",
    "Optional proxy and CA configuration.": "선택적 프록시와 CA 설정입니다.",
    "Correct or unset AGENT_OPT_CA_BUNDLE; provide a readable valid full PEM trust bundle without private keys, then rerun doctor.": "AGENT_OPT_CA_BUNDLE을 수정하거나 해제하세요. 개인 키가 없는 읽기 가능한 PEM 신뢰 번들을 준비한 뒤 doctor를 다시 실행하세요.",
    "Resolve core.python first. Run sh scripts/bootstrap.sh setup --core (or python3 scripts/dev.py setup --core).": "먼저 core.python을 해결하고 sh scripts/bootstrap.sh setup --core(또는 python3 scripts/dev.py setup --core)를 실행하세요.",
    "Choose a dataset name or a local tasks.json": "데이터셋 이름 또는 로컬 tasks.json을 지정하세요",
    "Select a dataset explicitly with --dataset": "데이터셋을 --dataset으로 직접 선택하세요",
    "Agent argv must be a nonempty string array": "Agent 실행 인수는 비어 있지 않은 문자열 배열이어야 합니다",
    "Inspect the choices then pass --yes to confirm preparation": "선택 항목을 확인한 뒤 --yes로 준비를 승인하세요",
    "A pinned Git Agent requires a revision": "고정 Git Agent에는 commit revision이 필요합니다",
    "git source requires url and a full commit SHA; branch/tag names are not accepted": "Git 소스에는 전체 commit SHA가 필요합니다. branch/tag 이름은 사용할 수 없습니다",
    "--model requires --plan": "--model에는 --plan이 필요합니다",
    "run-session requires at least two prepared experiments": "run-session에는 준비된 실험이 최소 두 개 필요합니다",
    "TUI cancelled:": "TUI 취소:",
    "input ended": "입력이 종료되었습니다",
    "TUI interrupted": "TUI가 중단되었습니다",
    "Preparing the selected dataset…": "선택한 데이터셋 준비 중…",
    "Dataset provider is unavailable": "데이터셋 제공자를 사용할 수 없습니다",
    "Use agent-opt datasets list and register the selected provider": "agent-opt datasets list로 확인하고 선택한 제공자를 등록하세요",
    "Central component inventory is incomplete": "중앙 컴포넌트 목록이 불완전합니다",
    "Restore missing registered integration files": "누락된 등록 연동 파일을 복원하세요",
    "Dataset provider has no read-only readiness check": "데이터셋 제공자에 읽기 전용 진단이 없습니다",
    "Implement doctor(cache) for this dataset provider": "이 데이터셋 제공자에 doctor(cache)를 구현하세요",
    "Dataset inspection failed": "데이터셋 검사에 실패했습니다",
    "Inspect the selected provider and its local cache": "선택한 제공자와 로컬 캐시를 확인하세요",
    "Local Agent sources are available": "로컬 Agent 소스를 사용할 수 있습니다",
    "Agent source declarations checked; pinned Git source contents unverified until run snapshot": "Agent 소스 선언을 확인했습니다. 고정 Git 소스의 내용은 실행 스냅샷 전까지 미검증입니다",
    "Provide existing local Agent sources or prepare pinned Git sources": "존재하는 로컬 Agent 소스를 제공하거나 고정 Git 소스를 준비하세요",
    "Declared Agent prompt sources are available": "선언한 Agent 프롬프트 소스를 사용할 수 있습니다",
    "Declared Agent prompt paths checked; pinned Git source contents unverified until run snapshot": "선언한 Agent 프롬프트 경로를 확인했습니다. 고정 Git 소스의 내용은 실행 스냅샷 전까지 미검증입니다",
    "Provide each declared prompt_file in Agent source": "Agent 소스에 선언한 prompt_file을 각각 제공하세요",
    "Editable Agent files exist": "수정 가능한 Agent 파일이 존재합니다",
    "Declared editable Agent paths checked; pinned Git source contents unverified until run snapshot": "수정 가능한 Agent 경로를 확인했습니다. 고정 Git 소스의 내용은 실행 스냅샷 전까지 미검증입니다",
    "Declare editable paths matching existing Agent files": "실제 Agent 파일과 일치하는 editable 경로를 선언하세요",
    "Research optimizer options and editable source files are valid": "연구 Optimizer 옵션과 수정 가능한 소스 파일이 유효합니다",
    "Declare an existing editable optimizer file, train tasks, and positive iteration allowance": "존재하는 수정 가능 Optimizer 파일·train 과제·양수 반복 허용량을 선언하세요",
    "Experiment file is missing or invalid": "실험 파일이 없거나 잘못되었습니다",
    "Provide a valid experiment.toml": "유효한 experiment.toml을 제공하세요",
    "Experiment project_root is invalid": "실험 project_root가 잘못되었습니다",
    "Set project_root to a directory path string": "project_root를 디렉터리 경로 문자열로 설정하세요",
    "Experiment schema is valid": "실험 스키마가 유효합니다",
    "Experiment schema or referenced input is invalid": "실험 스키마 또는 참조한 입력이 잘못되었습니다",
    "Correct the experiment, Agent, harness, and benchmark declarations": "실험·Agent·하네스·벤치마크 선언을 수정하세요",
    "Registered component files and declared dependencies are available": "등록된 컴포넌트 파일과 선언한 의존성을 사용할 수 있습니다",
    "Restore the selected registered component and declared dependency files": "선택한 등록 컴포넌트와 선언한 의존성 파일을 복원하세요",
    "Agent execution argv is declared": "Agent 실행 argv가 선언되어 있습니다",
    "Declare a nonempty harness.command argv array": "비어 있지 않은 harness.command argv 배열을 선언하세요",
    "Harnesses are registered": "하네스가 등록되어 있습니다",
    "Harness or declared plugin files are unavailable": "하네스 또는 선언한 플러그인 파일을 사용할 수 없습니다",
    "Register the harness and provide its declared plugin files": "하네스를 등록하고 선언한 플러그인 파일을 제공하세요",
    "Declared runtime binaries are available": "선언한 실행 도구를 사용할 수 있습니다",
    "Install the declared Docker, OpenCode, or Claude Code (claude) runtime executable":
        "선언한 Docker, OpenCode 또는 Claude Code (claude) 실행 파일을 설치하세요",
    "Evaluator is registered": "채점기가 등록되어 있습니다",
    "Evaluator is not registered": "채점기가 등록되지 않았습니다",
    "Register the selected evaluator or supply an explicit evaluator plugin": "선택한 채점기를 등록하거나 평가기 플러그인을 명시하세요",
    "Optimizers are registered": "Optimizer가 등록되어 있습니다",
    "Optimizer is not registered": "Optimizer가 등록되지 않았습니다",
    "Select a registered optimizer": "등록된 Optimizer를 선택하세요",
    "Task output files are declared": "과제 출력 파일이 선언되어 있습니다",
    "Declare task output file paths in the benchmark": "벤치마크에 과제 출력 파일 경로를 선언하세요",
    "Selected dataset and evaluator match": "선택한 데이터셋과 채점기가 일치합니다",
    "Use the registered evaluator ID from the selected dataset provider": "선택한 데이터셋 제공자에 등록된 채점기 ID를 사용하세요",
    "Custom benchmark schema and splits are valid": "사용자 벤치마크 스키마와 분할이 유효합니다",
    "Required model configuration is present": "필요한 모델 설정이 있습니다",
    "Model connectivity probe passed": "모델 연결 검사가 통과했습니다",
    "Model connectivity probe failed": "모델 연결 검사가 실패했습니다",
    "Verify model credentials, endpoint, connectivity, and tool-call support": "모델 자격증명·endpoint·연결·tool-call 지원을 확인하세요",
}

_DIAGNOSTIC_CAUSE_KO = {
    "Docker daemon/socket failure": "Docker daemon/socket 연결 실패",
    "TLS/certificate failure": "TLS 인증서 검증 실패",
    "DNS/connection failure": "DNS/네트워크 연결 실패",
    "offline cache miss": "오프라인 cache 누락",
    "lock/platform mismatch": "lock/platform 불일치",
    "required file is missing": "필요한 파일이 없습니다",
    "command returned a non-zero exit code": "명령이 0이 아닌 종료 코드를 반환했습니다",
    "unknown failure": "분류되지 않은 오류",
    "TLS certificate verification failed": "TLS 인증서 검증에 실패했습니다",
    "pinned source is missing from offline cache": "고정 source가 offline cache에 없습니다",
    "Pinned source checkout differs or has local changes": "고정 source checkout이 다르거나 로컬 변경이 있습니다",
    "CVDP requirements input hash differs from the pinned lock": "CVDP requirements 입력 hash가 고정 lock과 다릅니다",
    "CVDP driver lock differs or is missing": "CVDP driver lock이 다르거나 없습니다",
    "Installed CVDP driver packages differ from the prepared lock": "설치된 CVDP driver package가 준비된 lock과 다릅니다",
    "Offline CVDP lock is missing or platform/CA differs": "offline CVDP lock이 없거나 platform/CA가 다릅니다",
    "Offline CVDP dataset lock differs from the prepared cache": "offline CVDP 데이터셋 lock이 준비된 cache와 다릅니다",
    "Offline evaluation image identity differs from the lock": "offline 평가 이미지 identity가 lock과 다릅니다",
    "Offline CVDP driver packages differ from the prepared lock": "offline CVDP driver package가 준비된 lock과 다릅니다",
    "Offline environment lock is missing or platform differs": "offline environment lock이 없거나 platform이 다릅니다",
    "image OS/architecture differs from the selected platform": "이미지 OS/architecture가 선택한 platform과 다릅니다",
    "Offline image identity differs from the prepared lock": "offline 이미지 identity가 준비된 lock과 다릅니다",
    "evaluation image identity or platform differs from the selected platform": "평가 이미지 identity 또는 platform이 선택한 platform과 다릅니다",
    "CVDP imported-task provenance is missing from the offline cache": "CVDP imported task provenance가 offline cache에 없습니다",
    "CVDP imported-task digest differs from its offline lock": "CVDP imported task digest가 offline lock과 다릅니다",
    "CVDP imported-task file is missing from the offline cache": "CVDP imported task 파일이 offline cache에 없습니다",
}
for _en, _ko in _DEVELOPMENT_KO.items():
    MESSAGES.setdefault(_en, (_ko, _en))


def current_language(raw: str | None = None) -> str:
    selected = os.environ.get("AGENT_OPT_LANG", "") if raw is None else raw
    if selected in ("", "ko"):
        return "ko"
    if selected == "en":
        return "en"
    raise ValueError("AGENT_OPT_LANG must be ko or en")


def t(key: str, *, lang: str | None = None, **values: object) -> str:
    ko, en = MESSAGES[key]
    template = en if (lang or current_language()) == "en" else ko
    return template.format(**values) if values else template


def human(text: str, *, lang: str | None = None) -> str:
    """Known static UI text is translated; component-provided text is unchanged."""
    return t(text, lang=lang) if text in MESSAGES else text


def human_diagnostic_cause(text: str, *, lang: str | None = None) -> str:
    """Translate fixed classifier phrases while preserving safe raw error detail."""
    selected = lang or current_language()
    if selected != "ko":
        return text
    translated = text
    for source, target in _DIAGNOSTIC_CAUSE_KO.items():
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bexecutable not found\b", "실행 파일을 찾을 수 없습니다",
                        translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bcould not run: permission denied\b", "실행 권한이 거부되었습니다",
                        translated, flags=re.IGNORECASE)
    translated = re.sub(r"\boperation timed out\b", "작업 시간 초과",
                        translated, flags=re.IGNORECASE)
    translated = re.sub(r"\btimed out(?=:|$)", "시간 초과", translated, flags=re.IGNORECASE)
    return re.sub(r"\bexited (\d+)\b", r"종료 코드 \1", translated, flags=re.IGNORECASE)


def opencode_error_detail(status: int | None, endpoint: str | None, *,
                          missing_openai_version: bool = False) -> str:
    safe_endpoint = endpoint or t("Unknown API endpoint")
    if status == 404 and missing_openai_version:
        return t("OpenAI API 404 without version path at {endpoint}", endpoint=safe_endpoint)
    messages = {
        401: "OpenCode API authentication failed at {endpoint}",
        403: "OpenCode API access denied at {endpoint}",
        404: "OpenCode API route or model not found at {endpoint}",
        429: "OpenCode API rate or usage limit reached at {endpoint}",
    }
    if status is None:
        return t("OpenCode API error event has no safe HTTP status")
    template = messages.get(status, "OpenCode API request failed with HTTP {status} at {endpoint}")
    return t(template, status=status, endpoint=safe_endpoint)


def render_diagnostic(row: dict, *, lang: str | None = None) -> str:
    """Render the stable check strings as concise, labeled terminal lines."""
    selected = lang or current_language()
    message = row["message"]
    cause = blocked_by = ""
    message, marker, cause = message.partition("\nCause: ")
    if not marker:
        message, marker, blocked_by = row["message"].partition("\nBlocked by: ")
    remedy, marker, retry = row["remedy"].partition("\nRetry: ")

    if selected == "ko" and row["id"] == "budget.trials":
        count = re.fullmatch(r"Trial budget must reserve at least (\d+) trials", message)
        if count:
            number = count.group(1)
            message = f"평가 예산은 최소 {number}회 예약해야 합니다"
            if remedy.startswith("Set budget.max_trials to at least "):
                remedy = f"budget.max_trials를 최소 {number}으로 설정하거나 단계 허용량을 줄이세요"
        cause_count = re.fullmatch(
            r"configured budget is (\d+) trials; required reserve is (\d+) trials", cause)
        if cause_count:
            cause = (f"설정된 예산은 {cause_count.group(1)}회이며 "
                     f"최소 {cause_count.group(2)}회가 필요합니다")
    if selected == "ko" and row["id"] == "model.configuration" and remedy:
        prefix = ("Set AGENT_OPT_MODEL_BASE_URL and "
                  "AGENT_OPT_MODEL_API_KEY for research optimizers; set ")
        suffix = " for OpenCode harnesses"
        if remedy.startswith(prefix) and remedy.endswith(suffix):
            harness_keys = remedy[len(prefix):-len(suffix)]
            remedy = ("연구 Optimizer에는 AGENT_OPT_MODEL_BASE_URL과 "
                      f"AGENT_OPT_MODEL_API_KEY를, OpenCode 하네스에는 {harness_keys}를 설정하세요")

    lines = [human(message, lang=selected)]
    if cause:
        lines.append(f"  {human('Cause:', lang=selected)} {human_diagnostic_cause(cause, lang=selected)}")
    if blocked_by:
        lines.append(f"  {human('Blocked by:', lang=selected)} {human(blocked_by, lang=selected)}")
    if remedy:
        lines.append(f"  {human('Fix:', lang=selected)} {human(remedy, lang=selected)}")
    if retry:
        lines.append(f"  {human('Retry:', lang=selected)} {retry}")
    return "\n".join(lines)


def report_language(summary: dict, root: Path, *, override: str | None = None) -> str:
    """Keep the run language across regeneration; override only this rendering."""
    if override:
        return current_language(override)
    if summary.get("report_language") in ("ko", "en"):
        return summary["report_language"]
    previous = root / "report.html"
    if previous.is_file() and not previous.is_symlink():
        with previous.open("rb") as stream:
            found = re.search(rb'<html\s+lang="(ko|en)"', stream.read(1024))
        if found:
            return found.group(1).decode("ascii")
    return "en"
