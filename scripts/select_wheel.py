"""Select exactly one current-version wheel for the isolated CLI check."""

import sys
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path


def main(argv):
    if len(argv) != 1:
        print("사용법: python scripts/select_wheel.py dist", file=sys.stderr)
        return 2
    with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    wheels = sorted(Path(argv[0]).glob("*.whl"))
    if (len(wheels) != 1 or wheels[0].is_symlink() or not wheels[0].is_file()
            or not wheels[0].name.startswith(f"agent_optimizer-{version}-")):
        print(f"현재 버전 {version}의 wheel 파일이 정확히 하나여야 합니다: {argv[0]}", file=sys.stderr)
        return 2
    try:
        with zipfile.ZipFile(wheels[0]) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("wheel METADATA 개수가 올바르지 않습니다")
            metadata = BytesParser().parsebytes(archive.read(names[0]))
            if metadata["Name"] != "agent-optimizer" or metadata["Version"] != version:
                raise ValueError("wheel 메타데이터의 이름 또는 버전이 현재 프로젝트와 다릅니다")
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"wheel 검증 실패: {exc}", file=sys.stderr)
        return 2
    print(wheels[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
