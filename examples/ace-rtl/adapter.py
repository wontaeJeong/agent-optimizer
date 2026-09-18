"""OpenCode skill profile. This does not impersonate ACE's native runner."""
from dataclasses import replace
from agent_optimizer.harnesses.opencode import OpenCodeHarness

class ACEOpenCode(OpenCodeHarness):
    def run(self, request):
        prefix = """Use the ACE-RTL skill below as reusable role guidance.
The candidate ACE source is in ./agent/skills/ace-rtl/.
Read its role-guidance and relevant Generator/Reflector/Coordinator components.
This experiment supplies one public task in ./task; write the requested targets there.
Do not download a dataset, inspect hidden tests, or invoke ACE benchmark runners.
The external evaluator runs official CVDP after you finish. Do not claim a test pass.
Use bounded reasoning and available public-source checks within this invocation.
This profile evaluates ACE skill usage through OpenCode, not ACE's native iterative runner.
"""
        return super().run(replace(request, prompt=prefix+request.prompt))
