"""고정 CVDP row 검토, 공개 입력과 제출물 경계. 평가 자료는 trusted 쪽에만 둔다."""
import hashlib
import json
import re
from pathlib import Path

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path

DATA_SHA256 = 'cbcd81295561ebb16e4d857e096f4d9908d042c33aff3b58abf236e868411857'
REVIEWED_CIDS = {'cid002', 'cid004', 'cid007', 'cid016'}
COMMERCIAL = re.compile(r'\b(xcelium|xrun|irun|vcs|questa|modelsim|vsim|cadence|synopsys)\b|__VERIF_EDA_IMAGE__|LICENSE_NETWORK', re.I)


def load_pinned_rows(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA256:
        raise ConfigurationError('native CVDP 데이터 hash가 고정 버전과 다릅니다')
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ConfigurationError('native CVDP task ID 중복')
    return rows


def validate_targets(targets):
    if not targets or len(targets) != len(set(targets)):
        raise ConfigurationError('선언 target이 없거나 중복입니다')
    for name in targets:
        if not re.fullmatch(r'rtl/[A-Za-z0-9_./-]+\.(sv|v)', name) or any(p in {'', '.', '..'} for p in name.split('/')):
            raise ConfigurationError('검토되지 않은 native RTL target 경로')
        safe_path(Path('/validation'), name)


def inspect_row(row):
    targets = list(row.get('output', {}).get('context', {}))
    harness = row.get('harness', {}).get('files', {})
    text = json.dumps(harness)
    cid = next((c for c in row.get('categories', []) if c.startswith('cid')), None)
    reason = ''
    if cid not in REVIEWED_CIDS:
        reason = 'native binary functional 평가 검토 범주 밖입니다'
    elif COMMERCIAL.search(text):
        reason = '상용 도구 실행 경로가 포함되어 native 검토에서 제외합니다'
    elif '__OSS_PNR_IMAGE__' in text or any(Path(k).name in {'synth.py', 'synth.tcl', 'Dockerfile.synth'} for k in harness):
        reason = 'OSS_PNR_IMAGE/Yosys 합성 Dockerfile·임계값 평가 환경은 준비·검증되지 않았습니다'
    elif cid == 'cid007' and 'src/lint.py' not in harness:
        reason = 'CID007에서 검토한 binary lint-only 서비스가 아닙니다'
    else:
        compose = harness.get('docker-compose.yml', '')
        images = re.findall(r'^\s+image\s*:\s*(\S+)\s*(?:#[^\n]*)?$', compose, re.M)
        dockerfiles = [v for k, v in harness.items() if Path(k).name.startswith('Dockerfile')]
        aliases = [ '\n'.join(line.strip() for line in d.splitlines() if line.strip() and not line.lstrip().startswith('#')) for d in dockerfiles ]
        if not compose or any(i != '__OSS_SIM_IMAGE__' for i in images) or (not images and not dockerfiles):
            reason = '검토된 OSS_SIM_IMAGE binary 서비스가 아닙니다'
        elif dockerfiles and any(d != 'FROM __OSS_SIM_IMAGE__' for d in aliases):
            reason = '추가 Dockerfile 도구/다운로드 환경은 검토되지 않았습니다'
        elif not dockerfiles and re.search(r'^\s+build\s*:', compose, re.M):
            reason = '선언되지 않은 서비스 build입니다'
        else:
            try:
                validate_targets(targets)
                for name in row['input'].get('context', {}):
                    safe_path(Path('/validation'), name)
            except (ConfigurationError, KeyError):
                reason = 'public context 또는 output target 경로가 유효하지 않습니다'
    tools = ['Icarus', 'cocotb', 'pytest']
    if 'src/lint.py' in harness:
        tools.append('Verilator')
    if '__OSS_PNR_IMAGE__' in text:
        tools.append('Yosys')
    return {'id': row.get('id'), 'cid': cid, 'supported': not reason, 'reason': reason,
            'targets': targets, 'target_count': len(targets), 'tools': tools,
            'verification': 'row_review_only'}


def public_row(row):
    validate_targets(list(row['output']['context']))
    return {'id': row['id'], 'categories': row.get('categories', []),
            'input': {'prompt': row['input']['prompt'], 'context': dict(row['input'].get('context', {}))},
            'output': {'response': '', 'context': {p: '' for p in row['output']['context']}}}


def parse_outputs(content, targets):
    validate_targets(targets)
    if not isinstance(content, str) or not content.strip():
        raise ConfigurationError('native 모델의 출력이 비어 있습니다')
    marker = re.compile(r'^// TARGET_FILE: ([^\n\r]+)\r?$', re.M)
    matches = list(marker.finditer(content))
    if matches:
        if content[:matches[0].start()].strip():
            raise ConfigurationError('target section 앞의 임의 출력은 허용하지 않습니다')
        names = [m.group(1) for m in matches]
        if len(names) != len(set(names)) or set(names) != set(targets):
            raise ConfigurationError('선언 target 전체를 정확히 한 번 제출해야 합니다')
        output = {m.group(1): content[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(content)].strip() for i, m in enumerate(matches)}
    elif len(targets) == 1:
        output = {targets[0]: content.strip()}
    else:
        raise ConfigurationError('다중 target의 전체 section이 필요합니다')
    if any(not value or '```' in value for value in output.values()):
        raise ConfigurationError('빈 target 또는 Markdown 출력은 허용하지 않습니다')
    return output


def read_outputs(root, targets):
    validate_targets(targets)
    outputs = {}
    for name in targets:
        path = safe_path(root, name)
        if not path.is_file() or not path.read_text().strip():
            raise ConfigurationError('필수 native target 출력 누락')
        outputs[name] = path.read_text()
    return outputs


def classify_result(record):
    tests = record.get('tests') if isinstance(record, dict) else None
    if not isinstance(tests, list) or not tests or any(not isinstance(t, dict) or type(t.get('result')) is not int for t in tests):
        return 'infrastructure_error', '공식 CVDP 결과가 없거나 스키마가 유효하지 않습니다'
    errors = ' '.join(str(t.get('error_msg', '')) for t in tests).lower()
    if any(t['result'] in {125, 126, 127} for t in tests) or any(s in errors for s in ['command not found', 'no such image', 'cannot connect to the docker', 'failed to execute objective harness']):
        return 'infrastructure_error', '공식 CVDP 환경/도구 오류'
    passed = all(t['result'] == 0 for t in tests)
    return ('passed' if passed else 'failed'), f'공식 CVDP binary: {sum(t["result"] == 0 for t in tests)}/{len(tests)}'
