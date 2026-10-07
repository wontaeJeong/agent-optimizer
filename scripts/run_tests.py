"""평평한 unittest 모듈을 격리 프로세스로 실행하고 시간·결과를 합산한다."""
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append((time.perf_counter() - self.started, test.id()))
        super().stopTest(test)


def worker(directory, modules, report):
    # Match `python -m unittest`: the working tree is importable, including examples.
    sys.path.insert(0, str(Path.cwd()))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.discover(str(directory), pattern=name) for name in modules)
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(suite)
    report.write_text(json.dumps({
        "tests": result.testsRun, "skipped": len(result.skipped),
        "failures": len(result.failures), "errors": len(result.errors),
        "timings": result.timings,
    }), encoding="utf-8")
    return int(not result.wasSuccessful())


def cancel(signum, _frame):
    raise SystemExit(128 + signum)


def stop_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("tests"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--worker", nargs="+", help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.worker:
        return worker(directory, args.worker, args.report)
    if args.jobs < 1:
        parser.error("--jobs는 1 이상이어야 합니다")
    modules = sorted(directory.glob("test*.py"), key=lambda path: (-path.stat().st_size, path.name))
    if not modules:
        parser.error("실행할 테스트 모듈이 없습니다")
    groups = [[] for _ in range(min(args.jobs, len(modules)))]
    sizes = [0] * len(groups)
    for module in modules:
        index = min(range(len(groups)), key=sizes.__getitem__)
        groups[index].append(module.name)
        sizes[index] += module.stat().st_size
    started = time.perf_counter()
    summary = dict(tests=0, skipped=0, failures=0, errors=0)
    timings = []
    failed = False
    with tempfile.TemporaryDirectory(prefix="agent-opt-ci-") as temporary:
        processes = []
        handlers = {sig: signal.signal(sig, cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            for index, group in enumerate(groups):
                report = Path(temporary) / f"{index}.json"
                log = open(Path(temporary) / f"{index}.log", "w+", encoding="utf-8")
                process = subprocess.Popen(
                    [sys.executable, "-B", str(Path(__file__).resolve()), "--directory", str(directory),
                     "--worker", *group, "--report", str(report)],
                    stdout=log, stderr=subprocess.STDOUT, shell=False, start_new_session=True,
                )
                processes.append((process, log, report))
            print(f"테스트 모듈 {len(modules)}개 · 격리 프로세스 {len(groups)}개 실행 중", flush=True)
            pending = set(range(len(processes)))
            while pending:
                for index in sorted(pending):
                    process, log, report = processes[index]
                    code = process.poll()
                    if code is None:
                        continue
                    pending.remove(index)
                    failed |= code != 0
                    log.seek(0)
                    print(f"\n=== 테스트 프로세스 {index + 1}/{len(groups)} · 종료 코드 {code} ===", flush=True)
                    print(log.read(), end="", flush=True)
                    if report.exists():
                        result = json.loads(report.read_text(encoding="utf-8"))
                        for key in summary:
                            summary[key] += result[key]
                        timings.extend(result["timings"])
                    else:
                        failed = True
                if pending:
                    time.sleep(0.1)
        finally:
            # Finish bounded cleanup even if Actions sends another cancellation signal.
            for sig in handlers:
                signal.signal(sig, signal.SIG_IGN)
            for process, log, _ in processes:
                stop_group(process, signal.SIGTERM)
            for process, log, _ in processes:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                # Descendants can survive even after their worker exits on SIGTERM.
                stop_group(process, signal.SIGKILL)
                process.wait(timeout=2)
                log.close()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print("\n느린 테스트 (상위 10개):")
    for duration, name in sorted(timings, reverse=True)[:10]:
        print(f"{duration:.3f}s {name}")
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    print("CI_SUMMARY " + json.dumps(summary), flush=True)
    return int(failed or summary["tests"] == 0)


if __name__ == "__main__":
    raise SystemExit(main())
