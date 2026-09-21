from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol


class ConfigurationError(ValueError):
    pass


class UnavailableError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    kind: str
    path: Path | None = None
    url: str | None = None
    revision: str | None = None
    subdir: str = "."
    include: tuple[str, ...] = ("*",)
    exclude: tuple[str, ...] = (".env", ".env.*", "**/.env", "**/.env.*")
    timeout_seconds: float = 60


@dataclass(frozen=True)
class AgentSpec:
    id: str
    root: Path
    bundle: Path | None
    description: str
    supported_harnesses: tuple[str, ...]
    editable: tuple[str, ...]
    prompt_file: str = "prompts/system.md"
    build: tuple[str, ...] = ()
    source: SourceSpec | None = None


@dataclass(frozen=True)
class Candidate:
    id: str
    agent_id: str
    path: Path
    content_hash: str
    parents: tuple[str, ...] = ()
    producer: str = "baseline"


@dataclass(frozen=True)
class Task:
    id: str
    split: Literal["train", "validation", "test"]
    prompt: str
    files: dict[str, str]
    evaluation: dict[str, Any]
    required_simulator: str | None = None
    family: str = ""


@dataclass(frozen=True)
class RunRequest:
    workspace: Path
    agent_dir: Path
    task_dir: Path
    prompt: str
    seed: int
    timeout_seconds: float
    profile: dict[str, Any]
    logs: Path


@dataclass
class ExecutionResult:
    status: str
    returncode: int | None
    wall_time_seconds: float
    stdout_path: str
    stderr_path: str
    metrics: dict[str, float | None] = field(default_factory=dict)
    detail: str = ""


@dataclass
class Evaluation:
    status: str
    metrics: dict[str, float | None]
    feedback: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    candidates: list[Candidate]
    checkpoint: dict[str, Any] = field(default_factory=dict)


def jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value




class OptimizationContext(Protocol):
    """Train-only evaluation; final test data never enters the public context."""

    def evaluate(self, candidate: Candidate) -> dict[str, Any]: ...
    def propose(self, parent: Candidate, files: dict[str, str], producer: str) -> Candidate: ...
    def history(self) -> list[dict[str, Any]]: ...
    def record_usage(self, input_tokens: int | None, output_tokens: int | None, cost_usd: float | None) -> None: ...


class Optimizer(Protocol):
    def optimize(
        self, context: OptimizationContext, seeds: list[Candidate], config: dict[str, Any]
    ) -> OptimizationResult: ...


class HarnessAdapter(Protocol):
    def run(self, request: RunRequest) -> ExecutionResult: ...


class Evaluator(Protocol):
    def evaluate(self, task: Task, output_dir: Path, timeout_seconds: float) -> Evaluation: ...


@dataclass(frozen=True)
class HarnessCapabilities:
    trace: str  # json_events or stdout_only
    complete_token_accounting: bool
    model_seed_control: bool
    isolated_runtime_available: bool
    notes: str = ""


BUILTIN_HARNESSES = {
    "fixture": HarnessCapabilities("stdout_only", False, False, False, "Synthetic trusted local fixture"),
    "command": HarnessCapabilities("stdout_only", False, False, True, "Wrapper-defined protocol"),
    "opencode": HarnessCapabilities("json_events", False, False, True,
                                     "Child-session usage totals not verified; requested seed is not a model seed"),
}
