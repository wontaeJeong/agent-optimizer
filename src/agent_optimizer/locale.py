"""사람에게 표시하는 문구의 언어를 고릅니다. 실행 데이터는 번역하지 않습니다."""

import os


MESSAGES = {
    "remedy": ("해결", "Remedy"),
    "readiness": ("준비 상태", "readiness"),
    "Synthetic fixture tasks are valid": ("합성 예제 과제를 사용할 수 있습니다", "Synthetic fixture tasks are valid"),
    "Synthetic fixture evaluator is available": ("합성 예제 채점기를 사용할 수 있습니다", "Synthetic fixture evaluator is available"),
    "TUI requires a TTY for both input and output": ("TUI에는 입력과 출력 모두 TTY가 필요합니다", "TUI requires a TTY for both input and output"),
    "개발 명령: setup → doctor → demo. 어느 작업 디렉터리에서나 실행할 수 있습니다.": ("개발 명령: setup → doctor → demo. 어느 작업 디렉터리에서나 실행할 수 있습니다.", "Development commands: setup → doctor → demo. Run from any directory."),
    "--core/--dataset 없이: ACE 전체 준비; --core: 코어와 합성 fixture; --dataset ID: 선택한 데이터셋 준비": ("--core/--dataset 없이: ACE 전체 준비; --core: 코어와 합성 fixture; --dataset ID: 선택한 데이터셋 준비", "Prepare the full ACE environment by default; --core: core and synthetic fixture; --dataset ID: selected dataset"),
    "--core/--dataset 없이: ACE 전체 진단; --core: 코어 진단; --dataset ID: 선택한 데이터셋 읽기 전용 진단; --model: ACE 전체 전용": ("--core/--dataset 없이: ACE 전체 진단; --core: 코어 진단; --dataset ID: 선택한 데이터셋 읽기 전용 진단; --model: ACE 전체 전용", "Check the development environment: full ACE by default, --core for core, --dataset ID for read-only dataset checks; --model for full ACE"),
    "프로젝트 .venv에서 unittest 실행(Docker 불필요)": ("프로젝트 .venv에서 unittest 실행(Docker 불필요)", "Run unittest in project .venv (no Docker required)"),
    "프로젝트 .venv에서 Ruff 검사 실행": ("프로젝트 .venv에서 Ruff 검사 실행", "Run Ruff in project .venv"),
    "Docker/API 없이 최소 합성 데모 실행": ("Docker/API 없이 최소 합성 데모 실행", "Run minimal synthetic demo without Docker/API"),
    "실제 RTL/CVDP 평가기 검사 실행": ("실제 RTL/CVDP 평가기 검사 실행", "Check real RTL/CVDP evaluators"),
    "설정한 모델로 반복 최적화 실행(인증 필요)": ("설정한 모델로 반복 최적화 실행(인증 필요)", "Run optimization with a configured model (authentication required)"),
    "대화형 번호 메뉴 열기(TTY 필요, 모델 설정은 세션에서만 유지)": ("대화형 번호 메뉴 열기(TTY 필요, 모델 설정은 세션에서만 유지)", "Open numbered menu (TTY required; model settings remain in session)"),
    "도구 조회나 설치 없이 이 도움말 표시": ("도구 조회나 설치 없이 이 도움말 표시", "Show help without probing or installing tools"),
    "코어 사전 준비: Git. ACE 전체 준비에는 Docker Engine/Compose도 필요합니다. Python이나 make가 없다면 sh scripts/bootstrap.sh setup --core를 사용하세요. make <명령> ARGS='...'에는 일반 셸 인수를 전달합니다.": ("코어 사전 준비: Git. ACE 전체 준비에는 Docker Engine/Compose도 필요합니다. Python이나 make가 없다면 sh scripts/bootstrap.sh setup --core를 사용하세요. make <명령> ARGS='...'에는 일반 셸 인수를 전달합니다.", "Core prerequisite: Git. Full ACE also needs Docker Engine/Compose. Without Python or make use sh scripts/bootstrap.sh setup --core. make <command> ARGS='...' passes normal shell arguments."),
    "Agent Optimizer · 개발자 메뉴": ("Agent Optimizer · 개발자 메뉴", "Agent Optimizer · Developer menu"),
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
    "Experiment cancelled without preparing data": ("데이터 준비 전에 실험을 취소했습니다", "Experiment cancelled without preparing data"),
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


def human(text: str) -> str:
    """Known static UI text is translated; component-provided text is unchanged."""
    return t(text) if text in MESSAGES else text
