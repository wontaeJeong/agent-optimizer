"""Prepare pinned upstream sources and reuse the official OSS simulation image."""
import json
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
REPOS = {
    "ACE-RTL": ("https://github.com/NVlabs/ACE-RTL.git", "fead921f18bb57345b5a41ef93ba625be208e99c"),
    "cvdp_benchmark": ("https://github.com/NVlabs/cvdp_benchmark.git", "8e894cf74414ab1eaea1e2b4e80a02f123df07b6"),
}

def run(args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)

def main():
    external = ROOT / "external"
    external.mkdir(exist_ok=True)
    for name, (url, sha) in REPOS.items():
        path = external / name
        if not path.exists():
            run(["git", "clone", "--no-checkout", url, str(path)])
            run(["git", "checkout", "--detach", sha], path)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path, text=True).strip()
        if actual != sha or dirty:
            raise SystemExit(f"Existing checkout differs/dirty: {path}; preserve it and choose a fresh external directory")
    venv = external / "cvdp-venv"
    run([sys.executable, "-m", "venv", str(venv)])
    cvdp = external / "cvdp_benchmark"
    run([str(venv / "bin/python"), "-m", "pip", "install", "-r", str(cvdp / "requirements.txt")])
    run(["docker", "build", "-f", "docker/Dockerfile.sim", "-t", "nvidia/cvdp-sim:v1.0.0", "."], cvdp)
    image = subprocess.check_output(["docker", "image", "inspect", "nvidia/cvdp-sim:v1.0.0", "--format", "{{.Id}}"], text=True).strip()
    freeze = subprocess.check_output([str(venv / "bin/python"), "-m", "pip", "freeze"], text=True)
    (external / "environment-lock.json").write_text(json.dumps({"repos": REPOS, "image_id": image, "python_packages": freeze}, indent=2))
    print("OSS CVDP environment ready. Build the separate OpenCode Agent image next.")

if __name__ == "__main__":
    main()
