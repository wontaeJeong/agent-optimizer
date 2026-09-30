"""native 전용 고유 network 정리. 모든 명령이 하나의 deadline을 공유한다."""
import re
import subprocess
import time

from agent_optimizer.results import write_json


def cleanup_network(network, logs, *, deadline):
    started = time.monotonic()
    commands = []
    result = {'network': network, 'status': 'deferred', 'reason': 'budget_exhausted', 'commands': commands}
    def run(argv, label):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        record = {'command': label, 'returncode': None, 'status': 'started'}
        commands.append(record)
        try:
            response = subprocess.run(argv, capture_output=True, text=True, timeout=min(1, remaining), shell=False)
            record.update(returncode=response.returncode, status='completed' if response.returncode == 0 else 'error')
            return response
        except subprocess.TimeoutExpired:
            record['status'] = 'timeout'
        except OSError:
            record['status'] = 'unavailable'
        return None
    try:
        listing = run(['docker', 'ps', '-aq', '--filter', f'network={network}'], 'list_owned_containers')
        if listing is None or listing.returncode:
            result['status'] = 'incomplete' if commands else 'deferred'
            result['reason'] = commands[-1]['status'] if commands else 'budget_exhausted'
            return result
        for container in listing.stdout.split():
            if not re.fullmatch(r'[0-9a-f]{12,64}', container):
                result.update(status='incomplete', reason='invalid_container_id')
                return result
            removed = run(['docker', 'rm', '-f', container], 'remove_owned_container')
            if removed is None or removed.returncode:
                result.update(status='incomplete', reason='container_cleanup_incomplete')
                return result
        removed = run(['docker', 'network', 'rm', network], 'remove_owned_network')
        if removed is not None and (removed.returncode == 0 or any(
                text in removed.stderr.lower() for text in ['no such network', 'network ' + network + ' not found'])):
            result.update(status='completed', reason=None)
        else:
            result.update(status='incomplete', reason='network_cleanup_incomplete')
        return result
    finally:
        result['wall_time_seconds'] = time.monotonic() - started
        logs.mkdir(parents=True, exist_ok=True)
        write_json(logs / 'cleanup.json', result)
