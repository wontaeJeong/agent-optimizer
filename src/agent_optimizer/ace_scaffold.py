"""기준 후보에 복사할 공개 과제용 ACE/OpenCode 선행 scaffold."""
from pathlib import Path


def prepare_task(task_dir: Path) -> None:
    """Only modify public task inputs inside the trial workspace."""
    for path in sorted(task_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError("Scaffold refuses symlink task files")
        if path.is_file() and path.suffix in {".sv", ".v"}:
            path.write_text(path.read_text(encoding="utf-8") + "\n// ACE scaffold prepared this public task\n",
                            encoding="utf-8")
