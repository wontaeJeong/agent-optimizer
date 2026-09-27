"""Coding-Harness skill profiles. These do not impersonate ACE's native runner."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import re
from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.harnesses.claude_code import ClaudeCodeHarness
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


class ACEClaudeCode(ClaudeCodeHarness):
    @staticmethod
    def launch_existing(spec):
        root = Path(__file__).resolve().parents[2]
        example = root / "examples/ace-rtl/experiment-claude.toml"
        if spec["_source"].resolve() != example or spec["_root"] != root:
            raise ConfigurationError("ACE Claude 실행은 examples/ace-rtl/experiment-claude.toml에서만 지원합니다")
        path = safe_path(root, "examples/ace-rtl/environment/lifecycle.py")
        loaded = importlib.util.spec_from_file_location("ace_claude_selected_lifecycle", path)
        if loaded is None or loaded.loader is None:
            raise ConfigurationError("ACE 연동 실행 파일이 없습니다")
        lifecycle = importlib.util.module_from_spec(loaded)
        loaded.loader.exec_module(lifecycle)
        return lifecycle.run(root, experiment_file="experiment-claude.toml")

    def run(self, request):
        # The importer declares public targets in the task prompt; verify each against
        # the materialized public task, never the private evaluation metadata.
        declarations = re.findall(r"^Write target files: (.+)$", request.prompt, re.M)
        if len(declarations) != 1 or request.task_dir != request.workspace / "task":
            raise ConfigurationError("ACE Claude 공개 과제의 출력 대상 경로를 확인할 수 없습니다")
        targets = [target.strip() for target in declarations[0].split(",")]
        for target in targets:
            if (not re.fullmatch(r"rtl/[A-Za-z0-9_./-]+\.(?:sv|v)", target)
                    or any(part in {"", ".", ".."} for part in target.split("/"))
                    or not safe_path(request.task_dir, target).is_file()):
                raise ConfigurationError("ACE Claude 공개 과제의 출력 대상 파일을 확인할 수 없습니다")
        guided = with_ace_guidance(request)
        targets_in_workspace = "\n".join(f"- ./task/{target}" for target in targets)
        return super().run(replace(guided, prompt=guided.prompt + "\n\n"
            "The task description is already in this prompt; prioritize it over exploring upstream source. "
            "Do not search for task.json or prompt.txt or run upstream benchmark runners. "
            "Use Write/Edit on these existing public target files, relative to the workspace root:\n"
            + targets_in_workspace + "\n"))
