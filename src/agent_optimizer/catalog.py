"""Read-only descriptions of opt-in first-party datasets; implementations are separate."""

DATASETS = {
    "cvdp": {"name": "cvdp", "task_form": "rtl-generation", "evaluator": "cvdp",
             "revision": "8e894cf74414ab1eaea1e2b4e80a02f123df07b6", "requires_preparation": True},
    "verilog-spec": {"name": "verilog-spec", "task_form": "spec-to-rtl",
                     "evaluator": "verilog_eval",
                     "revision": "c498220d0a52248f8e3fdffe279075215bde2da6",
                     "requires_preparation": True},
    "verilog-completion": {"name": "verilog-completion", "task_form": "code-complete-iccad2023",
                           "evaluator": "verilog_eval",
                           "revision": "c498220d0a52248f8e3fdffe279075215bde2da6",
                           "requires_preparation": True},
}

_FIRST_PARTY_SOURCE = {
    "url": "https://github.com/wontaeJeong/agent-optimizer.git",
    "revision": "ae0874fb94d94284a07a17d84ef60058ed9a97b6",
    "contract": 1,
}

INTEGRATIONS = {name: dict(_FIRST_PARTY_SOURCE) for name in
                 ("ace-rtl", "cvdp", "verilog-spec", "verilog-completion")}


def list_choices(kind, root):
    """Describe declared choices without preparing sources, tools, or models."""
    from agent_optimizer.config import load_agent, read_toml
    from agent_optimizer.contracts import ConfigurationError
    from agent_optimizer.registry import Registry, is_source_checkout

    if kind not in {"agent", "harness", "optimizer", "dataset"}:
        raise ConfigurationError("kind: agent, harness, optimizer 또는 dataset 중에서 선택하세요")
    root = root.absolute()
    registry = Registry()
    if is_source_checkout(root):
        registry.load_project(root)
    rows = {}
    if kind == "agent":
        rows["ace-rtl"] = {"id": "ace-rtl", "name": "ACE-RTL", "implemented": True,
                           "ready": False, "description": "ACE Agent 선택; Python native 또는 명시 legacy skill 프로필. 고정 자산·모델 필요",
                           "requirements": ["고정 Git 소스", "선택 Harness 프로필"]}
        if is_source_checkout(root):
            for path in sorted({*(root / "examples").glob("*/source*.toml"),
                                *(root / "examples").glob("*/agent.toml")}):
                agent = load_agent(path)
                rows[agent.id] = {**rows.get(agent.id, {}), "id": agent.id,
                                  "name": agent.id, "implemented": True,
                                  "ready": agent.source.kind == "local" and agent.source.path.is_dir(),
                                  "description": agent.description,
                                  "supported_harnesses": list(agent.supported_harnesses)}
            for path in sorted((root / "examples/minimal").glob("*.toml")):
                if path.name in {"solo.toml", "team.toml"}:
                    agent = load_agent(path)
                    rows[agent.id] = {"id": agent.id, "name": agent.id, "implemented": True,
                                      "ready": agent.source.path.is_dir(),
                                      "description": agent.description,
                                      "supported_harnesses": list(agent.supported_harnesses)}
    elif kind == "harness":
        for name in sorted(registry.factories["harnesses"]):
            rows[name] = {"id": name, "name": name, "implemented": True, "ready": True,
                          "description": "등록된 Harness adapter; 실행 프로필/도구는 별도 확인"}
        for identifier, adapter in (("ace-opencode", "ace_opencode"),
                                    ("ace-claude-code", "ace_claude_code")):
            rows[identifier] = {"id": identifier, "name": identifier, "implemented": True,
                                "ready": False, "adapter": adapter,
                                "description": "ACE-RTL 전용 프로필; 고정 자산·도구·모델 준비 필요"}
        rows['ace-native'] = {'id': 'ace-native', 'name': 'Python native (ACE-RTL)',
                              'adapter': 'ace_native', 'implemented': True, 'ready': False,
                              'execution_mode': 'native', 'requires_model_api': True,
                              'model_roles': ['generator', 'reflector', 'coordinator'],
                              'edit_surfaces': {'gepa': 'native/guidance.md', 'meta_harness': 'native/orchestration.py'},
                              'reviewed_cids': ['cid002', 'cid004', 'cid007', 'cid016'],
                              'description': '고정 Python run_attempt 연결; 명시 CID/row 선택 필요. cid007 PNR·상용 helper row 제외. 실환경 not_run',
                              'requirements': ['고정 native 소스', 'Python 3.12/yaml/pydantic_settings', 'CVDP 고정 데이터·OSS 평가 환경', 'Agent 모델 API']}
        rows['ace_native'] = {**rows['ace-native'], 'id': 'ace_native', 'profile_id': 'ace-native'}
        if is_source_checkout(root):
            for path in sorted((root / "examples").glob("*/harness*.toml")):
                profile = read_toml(path)
                rows.setdefault(profile["id"], {
                    "id": profile["id"], "name": profile["id"], "implemented": True,
                    "ready": False, "description": "등록된 Harness 프로필; Agent 지원과 실행 도구 확인 필요"})
                rows[profile["id"]].update(adapter=profile["adapter"],
                                            runtime=profile.get("runtime", {}))
                if profile.get('adapter') == 'ace_native':
                    metadata = profile.get('compatibility', {})
                    rows[profile['id']].update(execution_mode=metadata.get('execution_mode'),
                        model_roles=metadata.get('roles', []), model_fields=metadata.get('model_fields', []),
                        reviewed_cids=metadata.get('reviewed_cids', []))
    elif kind == "optimizer":
        descriptions = {"baseline": "수정 없는 기준 평가; Optimizer 모델 불필요",
                        "gepa": "train 피드백으로 텍스트 후보 생성, validation 비교; merge 미지원",
                        "meta_harness": "후보별 활성 Python scaffold 수정·실행; train/validation 필요"}
        for name in sorted(registry.factories["optimizers"]):
            rows[name] = {"id": name, "name": name, "implemented": True,
                          "ready": False, "description": descriptions.get(
                              name, "등록된 Optimizer; 필요한 파일·모델·과제는 설정에서 확인")}
    else:
        for name in sorted(set(registry.factories["datasets"]) | set(DATASETS)):
            details = (registry.factories["datasets"][name]().describe()
                       if name in registry.factories["datasets"] else DATASETS[name])
            rows[name] = {"id": name, **details, "implemented": True,
                          "ready": False, "description": "선택 후 데이터·평가기 준비 확인 필요"}
    display = {"ace-rtl": "ACE-RTL", "ace-opencode": "OpenCode (ACE-RTL)",
               "ace-claude-code": "Claude Code (ACE-RTL)", "gepa": "GEPA",
               "meta_harness": "Meta-Harness", "cvdp": "CVDP"}
    requirements = {
        "ace-rtl": ["고정 ACE 소스", "native API 또는 legacy 모델 선택자", "선택 평가 환경"],
        "ace-opencode": ["ACE-RTL", "고정 OpenCode Docker image", "AGENT_OPT_MODEL"],
        "ace-claude-code": ["ACE-RTL", "Claude CLI 및 인증"],
        "gepa": ["editable 텍스트 파일", "train/validation 과제", "Optimizer 모델 API"],
        "meta_harness": ["실제로 호출되는 editable .py 파일", "train/validation 과제",
                         "Optimizer 모델 API"],
        "baseline": ["validation 과제", "Evaluator"],
        "cvdp": ["고정 공개 CVDP 과제", "cvdp 평가기", "Docker/driver"]}
    related = {"ace-rtl": ["ace-native", "ace-opencode", "ace-claude-code"],
               'ace-rtl-native': ['ace-native'], 'ace-native': ['ace-rtl-native', 'cvdp'],
               'ace_native': ['ace-rtl-native', 'cvdp'],
               "ace-opencode": ["ace-rtl"], "ace-claude-code": ["ace-rtl"],
               "gepa": ["editable 텍스트 Agent", "예: ace-rtl/ace-opencode/cvdp"],
               "meta_harness": ["실제로 실행되는 editable Python Agent", "예: ace-rtl/ace-opencode/cvdp"],
               "cvdp": ["ace-rtl/ace-opencode"]}
    return [{**rows[name], "name": display.get(name, rows[name]["name"]),
             "requirements": rows[name].get("requirements", requirements.get(name, [])),
             "supported_with": related.get(name, []),
             "reason": ("도구·모델·평가 실행은 조회에서 검사하지 않습니다"
                        if not rows[name]["ready"] else "등록됨; 실행 환경은 별도 진단")}
            for name in sorted(rows)]


def describe_choice(kind, identifier, root):
    from agent_optimizer.contracts import ConfigurationError

    row = next((item for item in list_choices(kind, root) if item["id"] == identifier), None)
    if row is None:
        raise ConfigurationError(f"등록되지 않은 {kind}: {identifier}; agent-opt catalog list --kind {kind}")
    return row
