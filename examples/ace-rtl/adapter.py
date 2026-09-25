"""OpenCode skill profile. This does not impersonate ACE's native runner."""
from dataclasses import replace
import importlib.util
from pathlib import Path
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.harnesses.opencode import OpenCodeHarness
from agent_optimizer.workspace import safe_path


def with_ace_guidance(request):
    """Domain prompt preparation reusable by another Harness adapter."""
    prefix = """Use the ACE-RTL skill below as reusable role guidance.
The candidate ACE source is in ./agent/skills/ace-rtl/.
Read its role-guidance and relevant Generator/Reflector/Coordinator components.
This experiment supplies one public task in ./task; write the requested targets there.
Do not download a dataset, inspect hidden tests, or invoke ACE benchmark runners.
The external evaluator runs official CVDP after you finish. Do not claim a test pass.
Use bounded reasoning and available public-source checks within this invocation.
This profile evaluates ACE skill usage through a coding Harness, not ACE's native iterative runner.
"""
    guidance = safe_path(request.agent_dir, "skills/ace-rtl/references/role-guidance.md")
    if guidance.is_file():
        prefix += "\nCandidate role guidance:\n" + guidance.read_text(encoding="utf-8") + "\n\n"
    return replace(request, prompt=prefix + request.prompt)


class ACEOpenCode(OpenCodeHarness):
    @staticmethod
    def launch_existing(spec):
        root = Path(__file__).resolve().parents[2]
        example = root / "examples/ace-rtl/experiment.toml"
        if spec["_source"].resolve() != example or spec["_root"] != root:
            raise ConfigurationError("ACE 실행은 기존 examples/ace-rtl/experiment.toml에서만 지원합니다")
        path = safe_path(root, "examples/ace-rtl/environment/lifecycle.py")
        loaded = importlib.util.spec_from_file_location("ace_selected_lifecycle", path)
        if loaded is None or loaded.loader is None:
            raise ConfigurationError("ACE 연동 실행 파일이 없습니다")
        lifecycle = importlib.util.module_from_spec(loaded)
        loaded.loader.exec_module(lifecycle)
        return lifecycle.run(root)

    def run(self, request):
        return super().run(with_ace_guidance(request))
