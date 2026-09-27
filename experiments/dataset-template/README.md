# Dataset 담당: 공개 과제와 별도 평가기

코어 환경을 준비한 뒤 `provider.py`를 `experiments/<team>/`에 복사하고 `prepare()`와 읽기 전용
`doctor()`를 구현합니다. `src/agent_optimizer/registry.py`의 `PROJECT_COMPONENTS`에 ID와 파일을
등록하며 기존 항목은 유지합니다. 예:

```python
"datasets": {"team_dataset": "experiments/my-team/provider.py:Provider"},
"evaluators": {"team_evaluator": "experiments/my-team/evaluator.py:Evaluator"},
```

추가 helper 경로는 `PROJECT_DEPENDENCIES`에
`"datasets/team_dataset": ["experiments/my-team/importer.py"]`처럼 선언합니다.
CLI 선택지와 설치 entry point는 수정하지 않습니다. `describe()`는 과제 형태와 evaluator ID를
알려주어 사용자가 데이터셋을 직접 선택할 수 있게 합니다.

`prepare(cache, offline=False)`는 공개 과제의 버전 고정 `benchmark` 경로, **등록된** `evaluator`
이름, 출처·버전·검증된 hash를 담은 `provenance`를 반환해야 합니다. 템플릿 stub은 실제 자산과
private 채점기가 연결될 때까지 `UnavailableError`를 냅니다. `doctor(cache)`는 `id`, `area`,
`status`, `message`, `remedy`가 있는 검사 목록을 반환하고 설치·다운로드·빌드·평가·모델 호출을
하지 않습니다. 공개 과제 파일에는 private 정답이나 키를 넣지 마세요.

```bash
.venv/bin/agent-opt datasets list
.venv/bin/agent-opt doctor --dataset team_dataset --json
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_plugin_contracts.py -v
```

앞의 두 명령은 **목록/선택 자산의 정적 진단**, 세 번째는 임시 합성 fixture 계약 검사입니다.
실제 데이터 준비 후 `agent-opt doctor --plan <실험.toml> --json`을 확인하고 공개 과제의 작은
`run`으로 실제 Agent 산출물·채점 근거와 `report.html`을 별도로 검증하세요. 보류된 기능이나
미구현 stub의 실패를 합성 점수로 대체하지 않습니다. 실험별 `[plugins.*]` 파일 등록도 유지합니다.
