"""명시적으로 요청한 로컬 고정 소스/데이터만 준비한다. 다운로드·설치 없음."""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError, SourceSpec
from agent_optimizer.results import write_json
from agent_optimizer.sources import _export_git, _git
from agent_optimizer.workspace import digest, regular_files, safe_path

PIN = 'fead921f18bb57345b5a41ef93ba625be208e99c'
EDITABLE = ('native/guidance.md', 'native/orchestration.py')


def sibling(name):
    spec = importlib.util.spec_from_file_location('_ace_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_source(upstream, destination):
    upstream, destination = Path(upstream), Path(destination)
    if destination.resolve().is_relative_to(upstream.resolve()):
        raise ConfigurationError('native snapshot은 upstream 밖에 준비해야 합니다')
    revision = _git(upstream, ['rev-parse', 'HEAD'], time.monotonic() + 10).decode().strip()
    if revision != PIN:
        raise ConfigurationError('native ACE upstream pin 불일치')
    destination.mkdir(parents=True, exist_ok=False)
    # Export the fixed Git tree, not mutable checkout files, and never fetch.
    _export_git(upstream, PIN, destination, SourceSpec('git', url=str(upstream), revision=PIN,
                include=('skills/ace-rtl/scripts/*', 'skills/ace-rtl/prompts/*')), time.monotonic() + 60)
    source_hash = digest(destination)
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in regular_files(destination)}
    native = destination / 'native'
    native.mkdir()
    for name in ['guidance.md', 'orchestration.py']:
        (native / name).write_bytes((Path(__file__).parent / 'native' / name).read_bytes())
    write_json(native / 'source-lock.json', {'schema_version': 1, 'revision': PIN, 'source_hash': source_hash, 'files': files})
    return {'revision': PIN, 'source_hash': source_hash, 'path': str(destination), 'editable': list(EDITABLE)}


def verify_source(source):
    lock = json.loads(safe_path(source, 'native/source-lock.json').read_text())
    if lock.get('revision') != PIN or lock.get('schema_version') != 1 or not lock.get('files'):
        raise ConfigurationError('native 소스 pin/lock 불일치')
    required = 'skills/ace-rtl/scripts/ace_cvdp_native/cli.py'
    if required not in lock['files']:
        raise ConfigurationError('native entry asset 누락')
    for name, expected in lock['files'].items():
        path = safe_path(source, name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ConfigurationError('native 고정 upstream asset 누락/변경')
    allowed = set(lock['files']) | set(EDITABLE) | {'native/source-lock.json'}
    if {p.relative_to(source).as_posix() for p in regular_files(source)} != allowed:
        raise ConfigurationError('native snapshot에 미허용 asset이 있습니다')
    return lock


def probe_python(python, *, timeout_seconds=10):
    # Keep a venv executable's symlink unresolved so pyvenv.cfg is respected.
    python = Path(python).absolute()
    if not python.is_file():
        return {'ready': False, 'reason': 'native Python interpreter 없음'}
    try:
        result = subprocess.run([str(python), '-c', 'import sys; import yaml; import pydantic_settings; print(sys.version_info[:2])'],
                                capture_output=True, text=True, timeout=timeout_seconds, shell=False,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'})
        valid = result.returncode == 0 and result.stdout.strip() == '(3, 12)'
        return {'ready': valid, 'reason': '' if valid else 'native Python 3.12 또는 필수 yaml/pydantic_settings 의존성 오류'}
    except (OSError, subprocess.TimeoutExpired):
        return {'ready': False, 'reason': 'native interpreter 진단 실패'}


def readiness(source, python, *, timeout_seconds=10):
    deadline = time.monotonic() + timeout_seconds
    checks = []
    try:
        lock = verify_source(Path(source))
        checks.append({'id': 'native_source', 'ready': True, 'revision': lock['revision']})
    except (OSError, ValueError, ConfigurationError):
        checks.append({'id': 'native_source', 'ready': False, 'reason': 'native pin/asset/lock 오류'})
    remaining = deadline - time.monotonic()
    checks.append({'id': 'native_python', **(probe_python(python, timeout_seconds=remaining) if remaining > 0 else
                   {'ready': False, 'reason': 'native 진단 timeout'})})
    return {'ready': all(c['ready'] for c in checks), 'checks': checks, 'live': 'not_run'}


def prepare_dataset(dataset, output, *, cids, splits=None):
    cvdp = sibling('native_cvdp')
    if not cids:
        raise ConfigurationError('사용자가 native CID를 명시적으로 선택해야 합니다')
    rows = cvdp.load_pinned_rows(dataset)
    tasks, excluded = [], []
    for row in rows:
        if not set(row['categories']).intersection(cids):
            continue
        verdict = cvdp.inspect_row(row)
        if not verdict['supported']:
            excluded.append(verdict)
            continue
        public = cvdp.public_row(row)
        split = (splits or {}).get(row['id'], 'validation')
        if split not in {'train', 'validation', 'test'}:
            raise ConfigurationError('native split은 train/validation/test여야 합니다')
        files = dict(public['input']['context'])
        for name in public['output']['context']:
            files.setdefault(name, '')
        files['native-task.json'] = json.dumps({**public, 'split': split}, ensure_ascii=False)
        # Only the trusted dataset/evaluator side retains the private harness.
        private = json.loads(json.dumps(row))
        private['output'] = public['output']
        tasks.append({'id': row['id'], 'split': split, 'family': row['id'],
                      'prompt': public['input']['prompt'], 'files': files,
                      'evaluation': {'row': private, 'targets': list(public['output']['context'])}})
    write_json(Path(output).with_suffix('.excluded.json'), excluded)
    if not tasks:
        raise ConfigurationError('선택 CID에 검토된 native 과제가 없습니다')
    result = {'schema_version': 1, 'synthetic': False, 'source_sha256': cvdp.DATA_SHA256, 'tasks': tasks,
              'native': {'mode': 'native', 'reviewed_cids': sorted(cids), 'live': 'not_run'}}
    write_json(Path(output), result)
    return result


def main():
    parser = argparse.ArgumentParser(description='native ACE 로컬 고정 자산 준비(다운로드 없음)')
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--source-output', type=Path, required=True)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--task-output', type=Path)
    parser.add_argument('--cid', action='append', default=[])
    args = parser.parse_args()
    source = prepare_source(args.upstream, args.source_output)
    if args.dataset:
        if not args.task_output:
            parser.error('--task-output 필요')
        prepare_dataset(args.dataset, args.task_output, cids=args.cid)
    print(json.dumps(source, ensure_ascii=False))


if __name__ == '__main__':
    main()
