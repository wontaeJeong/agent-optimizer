"""Self-contained, escaped HTML view over the canonical report model."""
from __future__ import annotations

import html
import json
import math
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import quote

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.locale import current_language, human
from agent_optimizer.report_style import STYLE
from agent_optimizer.workspace import safe_path


HELP = {
    'Agent × 하네스 그룹': '하나의 Agent와 실행 하네스를 짝지어 독립적으로 평가한 단위입니다.',
    'Agent × 하네스': 'Agent와 실행 하네스를 짝지어 평가한 조합입니다.',
    '완료된 평가': '과제별로 실제 종료되어 기록된 평가 건수입니다.',
    '기준 후보': '최적화하기 전의 Agent를 동일 조건에서 평가한 결과입니다.',
    '검증': '후보를 선택할 때 사용하는 데이터입니다. 최종 테스트와 분리됩니다.',
    '최종 테스트': '검증으로 후보를 고른 뒤에만 확인하는 별도 데이터입니다. 탐색에 사용하지 않습니다.',
    '후보': '원본 Agent의 스냅샷을 바탕으로 만든 변경 버전입니다.',
    '선택 후보': '검증 결과에 따라 선택된 변경 버전입니다.',
    '평가 횟수': '한 후보를 한 과제에 실행해 평가한 건수입니다.',
    '예산 사용 횟수': '예약되어 사용된 평가 예산입니다. 완료된 평가 건수와 다를 수 있습니다.',
    '예산': '실험에서 허용한 평가 횟수와 실행 시간의 상한입니다.',
    '점수 차이': '선택 후보 점수에서 기준 후보 점수를 뺀 값입니다.',
    'pp': '퍼센트포인트: 두 비율의 차이를 백분율 단위로 나타낸 값입니다.',
    '단계': '각 Optimizer가 기준 후보에서 시작해 독립적으로 탐색하는 구간입니다.',
    '체크포인트': 'Optimizer가 단계 실행 중 기록한 원본 상태입니다.',
    '사용량': '기록된 실행 비용과 토큰입니다. 값이 없으면 전체 사용량을 알 수 없습니다.',
    '하네스': 'Agent 실행과 결과 수집을 연결하는 구성 요소입니다.',
    '합성 예제': '연결 확인용 예제이며 실제 모델 성능을 입증하지 않습니다.',
    '독립 평가': '서로 다른 채점기의 점수를 직접 비교하거나 순위를 매기지 않습니다.',
}

SPLITS = {'train': '학습', 'validation': '검증', 'test': '테스트'}
STATES = {'completed': '완료', 'passed': '통과', 'failed': '실패', 'partial': '부분 완료',
          'error': '오류', 'interrupted': '중단', 'timeout': '시간 초과',
          'unsupported': '미지원', 'infrastructure_error': '실행 환경 오류',
          'process_error': '프로세스 오류', 'source_error': '소스 오류',
          'budget_exhausted': '예산 소진', 'unknown': '알 수 없음',
          'improved': '개선', 'regressed': '악화', 'unchanged': '변화 없음'}
FAILURES = {'infrastructure': '실행 환경 오류', 'timeout': '시간 초과',
            'unsupported': '미지원', 'interrupted': '중단', 'execution': '실행 오류',
            'run_error': '실험 오류', 'scored_failure': '채점 실패'}
DIRECTIONS = {'maximize': '높을수록 좋음', 'minimize': '낮을수록 좋음'}
MODES = {'lexicographic': '우선순위 순서', 'mean': '평균', 'sum': '합계'}
STRUCTURES = {'lineage': '후보 계보', 'iteration': '반복', 'generation': '세대',
              'phase': '단계', 'mixed': '혼합'}
EVENTS = {'candidate_created': '후보 생성', 'trial_started': '평가 시작',
          'trial_completed': '평가 완료', 'agent_started': 'Agent 시작',
          'agent_completed': 'Agent 완료', 'evaluation_started': '채점 시작',
          'evaluation_completed': '채점 완료', 'stage_started': '단계 시작',
          'stage_completed': '단계 완료', 'optimizer_iteration_started': '반복 시작',
          'optimizer_iteration_completed': '반복 완료',
          'optimizer_merge_completed': '후보 병합 완료', 'report_unit': '탐색 단위 기록'}
CONTEXT_LABELS = {'timestamp': '시각', 'stage_id': '단계', 'phase': '작업',
                  'status': '상태', 'candidate_id': '후보', 'task_id': '과제'}
PHASES = {'workspace': '작업 공간', 'agent': 'Agent', 'evaluation': '채점'}

_language = ContextVar('report_language', default='ko')


def _s(label):
    return human(label, lang=_language.get())


def text(item, limit=None):
    value = str(item) if item is not None else "—"
    return html.escape(value if limit is None else value[:limit], quote=True)


def _term(label):
    explanation = HELP.get(label)
    if explanation is None:
        return text(_s(label))
    return (f'<abbr class="help" title="{text(_s(explanation))}" tabindex="0" '
            f'aria-label="{text(_s(label))}: {text(_s(explanation))}">{text(_s(label))}</abbr>')


def _display(item, translations):
    return (text(translations.get(item, item) if _language.get() == 'ko' else item)
            if isinstance(item, str) else text(item))


def _split(item):
    return _term('검증') if item == 'validation' else _display(item, SPLITS)


def value(item):
    if item is None:
        return '<span class="subtle">—</span>'
    if type(item) in (int, float):
        try:
            if math.isfinite(item):
                if item != 0 and (abs(item) < 0.01 or abs(item) >= 1e9):
                    return text(f"{item:.6g}")
                return text(f"{item:.3f}")
        except OverflowError:
            pass
    return text(item, 200)


def _count(item):
    return text(item) if item is not None else value(None)


def _signed(item):
    if item is None:
        return value(None)
    return ("+" if item >= 0 else "") + value(item)


def _json(item):
    return '<pre>' + text(json.dumps(item, indent=2, ensure_ascii=False, default=str)) + '</pre>'


def _details(label, content):
    return f'<details><summary>{text(label)}</summary>{content}</details>'


def _link(root: Path, reference, label, directory=False):
    """Link only recorded files/directories that resolve inside the run, without symlinks."""
    if not isinstance(reference, str) or not reference:
        return None
    try:
        relative = Path(reference)
        if relative.is_absolute():
            relative = relative.relative_to(root.resolve())
        location = relative.as_posix()
        target = safe_path(root, location)
    except (ConfigurationError, ValueError):
        return None
    if not (target.is_dir() if directory else target.is_file()):
        return None
    href = quote(location, safe="/") + ("/" if directory else "")
    return f'<a href="{text(href)}">{text(label)}</a>'


def _table(caption, headers, body, numeric=()):
    titles = ''.join(f'<th scope="col" class="{"number" if index in numeric else ""}">'
                     f'{_term(label)}</th>' for index, label in enumerate(headers))
    return (f'<div class="table-scroll"><table><caption>{text(_s(caption))}</caption>'
            f'<thead><tr>{titles}</tr></thead><tbody>'
            + (''.join(body) or f'<tr><td colspan="{len(headers)}" class="subtle">{text(_s("평가 기록 없음"))}</td></tr>')
            + '</tbody></table></div>')


def _cells(items, numeric=(), row_header=0, row_class="", row_id=""):
    cells = []
    for index, item in enumerate(items):
        kind = 'th' if index == row_header else 'td'
        scope = ' scope="row"' if kind == 'th' else ''
        cells.append(f'<{kind}{scope} class="{"number" if index in numeric else ""}">{item}</{kind}>')
    identifier = f' id="{text(row_id)}"' if row_id else ''
    return f'<tr class="{row_class}"{identifier}>' + ''.join(cells) + '</tr>'


def _metrics(items):
    if not isinstance(items, dict) or not items:
        return f'<span class="subtle">{text(_s("기록 없음"))}</span>'
    return ', '.join(f'<strong>{text(key)}:</strong> {value(number)}'
                     for key, number in items.items())


def _aggregate_rows(rows, group_label=None):
    rendered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = ([text(group_label)] if group_label is not None else []) + [
            text(row.get('candidate_id')), _split(row.get('split')),
            _metrics(row.get('metrics')), _count(row.get('trial_count'))]
        rendered.append(_cells(cells, numeric=(4,) if group_label is not None else (3,)))
    return rendered


def _budget_label(budget):
    if not isinstance(budget, dict):
        return '—'
    parts = []
    for key, suffix in (('max_trials', '회'), ('max_wall_time_seconds', '초 총 실행 제한'),
                        ('trial_timeout_seconds', '초/평가')):
        item = budget.get(key)
        if type(item) is int:
            parts.append(f'{item}{_s(suffix)}')
        elif type(item) is float and math.isfinite(item):
            parts.append(f'{item:g}{_s(suffix)}')
    return ' · '.join(parts) or '—'


def _valid_selection(row, group):
    return (isinstance(row, dict) and row.get('split') == 'validation'
            and row.get('valid') is True and not row.get('partial', False)
            and row.get('agent_id') == group['agent_id']
            and row.get('harness_id') == group['harness_id'])


def _metadata(report):
    configuration = report.get('configuration') or {}
    provenance = report.get('provenance') or {}
    benchmark = provenance.get('benchmark') or {}
    objective = report.get('objective') or {}
    measures = objective.get('metrics') or []
    objective_label = ', '.join(f'{metric.get("name", "—")} '
                                f'({_s(DIRECTIONS.get(metric.get("direction"), metric.get("direction", "—")))})'
                                for metric in measures if isinstance(metric, dict)) or _s('기록 없음')
    stages = configuration.get('stages') or []
    fields = (
        ('벤치마크 ID', benchmark.get('id')), ('벤치마크 경로', configuration.get('benchmark')),
        ('목적 지표', objective_label),
         ('선택 방식', f'{_s(MODES.get(objective.get("mode"), objective.get("mode", "—")))} · '
                    f'{_s("유지 후보 수=")}{objective.get("keep", "—")}'),
        ('예산', _budget_label(configuration.get('budget'))),
         ('Optimizer', ', '.join(str(item.get('optimizer', '—')) for item in stages if isinstance(item, dict)) or _s('기록 없음')),
         ('Agent × 하네스', ', '.join(group['key'] for group in report['groups']) or _s('기록 없음')),
        ('실행 ID', report['identity'].get('run_id')),
    )
    if 'run_wall_time_seconds' in report['identity']:
        fields += (('실측 실행 시간', f'{report["identity"]["run_wall_time_seconds"]:.3f}{_s("초")}'),)
    return '<dl class="meta">' + ''.join(
        f'<div><dt>{_term(label)}</dt><dd class="{"mono" if label == "실행 ID" else ""}">'
        f'{text(json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item)}</dd></div>'
        for label, item in fields) + '</dl>'


def _comparison(group, number):
    selected = group.get('selected') or []
    winners = [item for item in selected if _valid_selection(item, group)]
    other = [item for item in selected if isinstance(item, dict) and not _valid_selection(item, group)]
    selection = []
    if winners:
        selection.append(text(_s('검증에서 선택된 후보: ')) + '<code>' + text(', '.join(
            str(item.get('candidate_id')) for item in winners)) + '</code>')
    if other:
        selection.append(text(_s('기록된 선택 (유효한 검증 결과 아님): ')) + '<code>' + text(', '.join(
            str(item.get('candidate_id')) for item in other)) + '</code>')
    if not selection:
        selection.append(text(_s('검증 선택 결과: ')) + '<code>' + text(_s('선택된 후보 없음')) + '</code>')
    baseline = group.get('baseline') or {}
    counts = group['counts']
    heading = (f'<section class="group" id="group-{number}"><div class="group-heading">'
               f'<h2>{text(group["agent_id"])} / {text(group["harness_id"])}</h2>'
               f'<span class="pill {"good" if group["comparison_trend"] == "improved" else ""}">'
               f'{_display(group["comparison_trend"], STATES)}</span></div>'
               f'<p class="subtle">{text(_s("완료"))} {_count(counts.get("completed_evaluations"))}{text(_s("건 · "))}'
               f'{text(_s("통과"))} {_count(counts.get("passed_evaluations"))}{text(_s("건 · "))}'
               f'{text(_s("실패"))} {_count(counts.get("failed_evaluations"))}{text(_s("건 · "))}'
               f'{_term("예산 사용 횟수")} {_count(counts.get("trials_used"))}{text(_s("회")) if _language.get() == "ko" else ""}</p>'
               f'<p>{_term("기준 후보")}: <code>{text(baseline.get("candidate_id"))}</code> → '
               f'{" · ".join(selection)}</p>')
    rows = []
    for metric in group['comparison']:
        difference = _signed(metric.get('delta'))
        if metric.get('delta_pp') is not None:
            difference += f' <span class="tag">({_signed(metric["delta_pp"])} {_term("pp")})</span>'
        rows.append(_cells((text(metric.get('name')), _display(metric.get('direction'), DIRECTIONS),
                            value(metric.get('baseline')), value(metric.get('selected')),
                            difference, _display(metric.get('trend'), STATES)), numeric=(2, 3, 4)))
    return heading + _table('검증 · 기준 후보 → 선택 후보',
                            ('지표', '방향', '기준 후보', '선택 후보', '점수 차이', '변화'),
                            rows, numeric=(2, 3, 4)) + '</section>'


def _test_results(report):
    rows = []
    for group in report['groups']:
        rows.extend(_aggregate_rows(group.get('final_test') or [], group['key']))
    return ('<section id="held-out-test"><h2>' + _term('최종 테스트') + '</h2>'
            f'<p class="subtle">{text(_s("검증으로 후보를 확정한 뒤 기록한 테스트입니다. 탐색에는 사용하지 않으며 Agent × 하네스 그룹별 점수를 따로 보여줍니다."))}</p>'
            + _table('최종 테스트 · 기록된 집계',
                     ('그룹', '후보', '데이터 구분', '지표', '평가 횟수'), rows, numeric=(4,)) + '</section>')


def _recorded_events(report, group, structured=False):
    events = [event for event in report.get('events', [])
              if isinstance(event, dict) and isinstance(event.get('event'), str)
              and event.get('event') != 'trial_completed'
              and event.get('agent_id') == group['agent_id']
              and event.get('harness_id') == group['harness_id']]
    if not events:
        return f'<p class="subtle">{text(_s("기록된 탐색 구조가 없습니다. 아래 평가 표를 확인하세요."))}</p>'
    description = ('기록된 그룹 이벤트를 로그 순서로 보여줍니다. 나머지 필드는 원본 기록에서 확인하세요.'
                   if structured else '기록된 탐색 구조가 없어 그룹 이벤트를 로그 순서로 보여줍니다. '
                   '나머지 필드는 원본 기록에서 확인하세요.')
    parts = [f'<p class="subtle">{text(_s(description))}</p><ol class="lineage">']
    for event in events:
        context_parts = []
        for name in ('timestamp', 'stage_id', 'phase', 'status', 'candidate_id', 'task_id'):
            if event.get(name) is None:
                continue
            displayed = (_display(event[name], STATES if name == 'status' else PHASES)
                         if name in ('status', 'phase') else text(event[name], 120))
            context_parts.append(f'{text(_s(CONTEXT_LABELS[name]))}: {displayed}')
        context = ' · '.join(context_parts)
        parts.append(f'<li><strong>{_display(event["event"], EVENTS)}</strong>'
                     + (f' <span class="tag">{context}</span>' if context else '')
                     + _details(_s('이벤트 원본'), _json(event)) + '</li>')
    return ''.join(parts) + '</ol>'


def _journey(report):
    sections = [f'<section id="journey"><h2>{text(_s("최적화 과정"))}</h2>']
    for group in report['groups']:
        structure = group.get('structure') or {}
        units = structure.get('units') or []
        edges = structure.get('edges') or []
        sections.append(f'<h3>{text(group["key"])} · {_display(structure.get("kind"), STRUCTURES) if structure.get("kind") else text(_s("기록된 근거"))}</h3>')
        if units:
            sections.append('<ol class="lineage">')
            for unit in units:
                label = unit.get('label') or unit.get('unit_id')
                if (unit.get('unit_type') == 'iteration' and isinstance(label, str)
                        and label.startswith('Iteration ') and label[10:].isdigit()
                        and isinstance(unit.get('unit_id'), str)
                        and unit['unit_id'].endswith('/iteration-' + label[10:])):
                    label = ('반복 ' if _language.get() == 'ko' else 'Iteration ') + label[10:]
                sections.append(f'<li><strong>{text(label)}</strong> '
                                f'<span class="tag">{_display(unit.get("unit_type"), STRUCTURES)} · '
                                f'{_term("단계")} {text(unit.get("stage_id"))}</span> · '
                                f'{text(_s("상위 단위"))} {text(unit.get("parent_unit_id"))} · '
                                f'{text(_s("후보"))} {text(", ".join(unit.get("candidate_ids") or []) or "—")} · '
                                f'{text(_s("평가 참조"))} {text(", ".join(unit.get("evaluation_refs") or []) or "—")}</li>')
            sections.append('</ol>')
            sections.append(_details(_s('그룹 이벤트 기록 · 원본 근거'),
                                     _recorded_events(report, group, structured=True)))
        else:
            sections.append(_recorded_events(report, group))
        if edges:
            sections.append(f'<p class="tag">{text(_s("기록된 후보 부모 관계"))}</p><ul class="lineage">')
            for edge in edges:
                sections.append(f'<li><code>{text(edge.get("candidate_id"))}</code> ← '
                                f'{text(", ".join(edge.get("parents") or []))}</li>')
            sections.append('</ul>')
    return ''.join(sections) + '</section>'


def _feedback(message):
    if not isinstance(message, str) or not message:
        return value(None)
    if len(message) <= 160:
        return text(message)
    return _details(_s('피드백 전체 · ') + message[:90], '<pre class="feedback">' + text(message) + '</pre>')


def _evidence_links(root, evaluation):
    references = []
    execution = evaluation.get('execution') or {}
    if isinstance(execution, dict):
        references.extend((key, execution.get(key)) for key in ('stdout_path', 'stderr_path'))
    artifacts = evaluation.get('artifacts') or {}
    if isinstance(artifacts, dict):
        references.extend(artifacts.items())
    links = []
    for label, reference in references:
        link = _link(root, reference, _s({'stdout_path': '표준 출력 로그',
                                          'stderr_path': '표준 오류 로그'}.get(label, label)))
        if link:
            links.append(link)
    return ' · '.join(links) or value(None)


def _evaluations(root, report):
    sections = [f'<section id="evaluations"><h2>{text(_s("평가 근거"))}</h2>'
                f'<p class="subtle">{text(_s("한 행은 한 과제의 평가 기록입니다. 과제별 지표는 전체 점수가 아닙니다."))}</p>']
    for index, group in enumerate(report['groups']):
        rows = []
        for position, entry in enumerate(group['evaluations']):
            failure = entry.get('failure') or {}
            label = _display(entry.get('status'), STATES)
            if failure:
                label += f' · <span class="bad">{_display(failure.get("category"), FAILURES)}</span>'
            refs = _evidence_links(root, entry)
            rows.append(_cells((text(entry.get('trial_id')), text(entry.get('candidate_id')),
                                text(entry.get('task_id')), _split(entry.get('split')),
                                text(entry.get('stage_id')), text(entry.get('repeat')),
                                label, _metrics(entry.get('metrics')),
                                _feedback(entry.get('feedback')) + (f'<p>{refs}</p>' if refs != value(None) else '')),
                               row_class='row-failed' if failure else '',
                               row_id=f'evaluation-{index}-{position}'))
        sections.append(_table(f'{group["key"]} · {_s("기록된 평가")}',
                               ('평가 ID', '후보', '과제', '데이터 구분', '단계', '반복',
                                '상태 / 원인', '관측 지표', '피드백 / 로그'), rows))
    if not report['groups']:
        sections.append(_table('기록된 평가', ('평가 ID', '후보', '과제', '데이터 구분',
                                           '상태 / 원인'), []))
    return ''.join(sections) + '</section>'


def _candidates(root, report):
    sections = [f'<section id="candidates"><h2>{text(_s("후보 변경 내역"))}</h2>']
    for index, group in enumerate(report['groups']):
        selected = group.get('selected') or []
        sections.append(f'<h3>{text(group["key"])} · {text(_s("기록된 선택과 후보"))}</h3>')
        if not selected:
            sections.append(f'<p class="subtle">{text(_s("선택된 후보 없음"))}</p>')
        selected_ids = set()

        def evidence(identifier, candidate, collapsible=False):
            if candidate:
                sections.append(f'<p>{text(_s("부모 후보"))}: {text(", ".join(candidate.get("parents") or []) or "—")} · '
                                f'{text(_s("생성 주체"))}: {text(candidate.get("producer"))} · '
                                f'{text(_s("변경 파일"))}: <code>{text(", ".join(map(str, candidate.get("changed_files") or [])) or "—")}</code></p>')
                diff = _link(root, candidate.get('diff_path'), 'changes.diff')
                bundle = _link(root, candidate.get('snapshot_path'), _s('스냅샷 묶음'), directory=True)
                sections.append('<p>' + ' · '.join(item for item in (diff, bundle) if item) + '</p>')
                if candidate.get('diff_preview'):
                    sections.append(_details(_s('변경 사항 미리보기'), '<pre>' + text(candidate['diff_preview']) + '</pre>'))
            else:
                sections.append(f'<p class="subtle">{text(_s("기록된 후보 파일 없음"))}</p>')
            history = [(position, entry) for position, entry in enumerate(group['evaluations'])
                       if entry.get('candidate_id') == identifier]
            sections.append(f'<p>{text(_s("평가 이력"))}: ' + (', '.join(
                f'<a href="#evaluation-{index}-{position}">{text(entry.get("trial_id"))} '
                f'({_split(entry.get("split"))})</a>'
                for position, entry in history) or text(_s('평가 기록 없음'))) +
                            ('</p></details></div>' if collapsible else '</p></div>'))

        for row in selected:
            if not isinstance(row, dict):
                continue
            identifier = row.get('candidate_id')
            if isinstance(identifier, str):
                selected_ids.add(identifier)
            candidate = next((item for item in group['candidates'] if item['candidate_id'] == identifier), None)
            valid = _valid_selection(row, group)
            sections.append(f'<div class="panel {"best" if valid else ""}"><strong>'
                            f'{text(_s("검증에서 선택" if valid else "기록된 선택 · 유효한 검증 결과 아님"))} · '
                            f'{text(identifier)}</strong> '
                            f'<span class="tag">{_split(row.get("split"))} {text(_s("집계"))} · '
                            f'{_count(row.get("trial_count"))} '
                            f'{text(_s("건의 평가"))}</span>'
                            f'<p>{_metrics(row.get("metrics"))}</p>')
            evidence(identifier, candidate)
        for candidate in group['candidates']:
            if candidate['candidate_id'] in selected_ids:
                continue
            identifier = candidate['candidate_id']
            sections.append(f'<div class="panel"><details><summary>{text(_s("기록된 후보"))} · '
                            f'{text(identifier)}</summary>')
            evidence(identifier, candidate, collapsible=True)
    return ''.join(sections) + '</section>'


def _failures(report):
    sections = [f'<section id="failures"><h2>{text(_s("실패 근거"))}</h2>']
    identity = report['identity']
    if identity.get('failure'):
        failure = identity['failure']
        sections.append(f'<div class="panel bad"><strong>{text(_s("실행 중단"))}: ' + _display(failure.get('category'), FAILURES) +
                         ' · ' + text(identity.get('error_type')) + '</strong>' +
                         _details(_s('실행 오류 원문'), '<pre>' + text(identity.get('error')) + '</pre>') + '</div>')
    for index, group in enumerate(report['groups']):
        for failure in group['failures']:
            evaluation = next(((position, item) for position, item in enumerate(group['evaluations'])
                               if item.get('id') == failure.get('evaluation_ref')), None)
            trial = (f'<a href="#evaluation-{index}-{evaluation[0]}">'
                     f'{text(evaluation[1].get("trial_id"))}</a>') if evaluation else text(failure.get('evaluation_ref'))
            sections.append('<div class="panel"><strong class="bad">' + _display(failure.get('category'), FAILURES) +
                            '</strong> · ' + text(group['key']) + ' · ' + trial +
                             (_details(_s('실패 메시지 원문'), '<pre>' + text(failure['message']) + '</pre>')
                             if failure.get('message') else '') + '</div>')
    if len(sections) == 1:
        sections.append(f'<p class="subtle">{text(_s("분류된 실패 기록 없음"))}</p>')
    return ''.join(sections) + '</section>'


def _stages(report):
    sections = ['<section id="stages"><h2>' + _term('단계') + ' · ' + _term('체크포인트')
                + ' · ' + _term('사용량') + '</h2>']
    for group in report['groups']:
        sections.append(f'<h3>{text(group["key"])}</h3>')
        for stage in group.get('stages') or []:
            sections.append(f'<div class="panel"><strong>{text(stage.get("id"))} · '
                            f'{text(stage.get("optimizer"))}</strong><p class="subtle">'
                             f'{text(_s("상태"))}: {_display(stage.get("status"), STATES)} · '
                             f'{text(_s("실측 단계 실행 시간"))}: {value(stage.get("stage_wall_time_seconds"))}{text(_s("초"))}</p>')
            sections.append(_table('단계별 검증 선택 집계',
                                   ('후보', '데이터 구분', '지표', '평가 횟수'),
                                   _aggregate_rows(stage.get('selected') or []), numeric=(3,)))
            sections.append(_details(_s('단계 평가 집계 및 체크포인트 원본'),
                                    _table('단계별 평가 집계',
                                            ('후보', '데이터 구분', '지표', '평가 횟수'),
                                            _aggregate_rows(stage.get('evaluated') or []), numeric=(3,))
                                    + _json(stage.get('checkpoint') or {})))
            sections.append('</div>')
        sections.append(f'<p class="subtle">{text(_s("Optimizer 사용량은 단계별 관측값입니다. 하네스가 보고한 Agent 사용량은 예상된 모든 유효 평가의 값이 있을 때만 전체값이며, 빠진 값은 미수집입니다."))}</p>')
        sections.append(_details(_s('Optimizer 사용량'), _json(group.get('optimizer_usage') or [])))
        sections.append(_details(_s('Agent 사용량 (하네스 보고)'), _json(group.get('agent_usage') or [])))
    return ''.join(sections) + '</section>'


def _provenance(report):
    manifest = report.get('provenance') or {}
    benchmark = manifest.get('benchmark') or {}
    content = {'agents': manifest.get('agents', []),
               'dataset_provenance': benchmark.get('dataset_provenance', {}),
               'models': manifest.get('resolved_models', {}),
               'plugin_sha256': manifest.get('plugin_sha256', {})}
    return (f'<section id="provenance"><h2>{text(_s("재현 정보와 출처"))}</h2>'
            f'<p>{text(_s("벤치마크 SHA-256"))}: <code>' + text(manifest.get('benchmark_sha256')) + '</code></p>'
            + _details(_s('실험 설정 원본'), _json(report.get('configuration') or {}))
            + _details(_s('소스 고정 버전 · 모델 · 플러그인 해시 원본'), _json(content)) + '</section>')


def _render_report(root: Path, report: dict) -> str:
    identity = report['identity']
    counts = report['counts']
    title = (report.get('configuration') or {}).get('name') or identity.get('run_id') or _s('실험')
    synthetic = ('<span class="pill warning">' + _term('합성 예제') + ' · ' + text(_s('실제 모델 성능 근거 아님')) + '</span>'
                  if identity.get('synthetic') else
                  f'<span class="pill">{text(_s("벤치마크 기록 · 모델 근거는 별도 확인 필요"))}</span>')
    cards = ''.join(f'<div class="card"><strong>{_count(counts.get(key))}</strong><span>{_term(label)}</span></div>'
                    for key, label in (('groups', 'Agent × 하네스 그룹'),
                                       ('completed_evaluations', '완료된 평가'),
                                       ('passed_evaluations', '통과한 평가'),
                                       ('failed_evaluations', '실패한 평가'),
                                       ('trials_used', '예산 사용 횟수')))
    parts = [f'<!doctype html><html lang="{_language.get()}"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'style-src \'unsafe-inline\'; img-src data:">',
             f'<title>Agent Optimizer · {text(title)}</title><style>{STYLE}</style></head><body>',
              f'<header><div class="eyebrow">Agent Optimizer / {text(_s("실험 분석"))}</div>',
              f'<h1>{text(title)}</h1><span class="pill">{_display(identity.get("status"), STATES)}</span>{synthetic}',
              _metadata(report),
              f'<nav aria-label="{text(_s("리포트 목차"))}"><a href="#scores">{text(_s("점수 비교"))}</a>'
              f'<a href="#held-out-test">{text(_s("최종 테스트"))}</a><a href="#journey">{text(_s("최적화 과정"))}</a>'
              f'<a href="#evaluations">{text(_s("평가 근거"))}</a><a href="#candidates">{text(_s("후보 변경"))}</a>'
              f'<a href="#failures">{text(_s("실패 근거"))}</a><a href="#stages">{text(_s("단계와 사용량"))}</a>'
              f'<a href="#provenance">{text(_s("재현 정보"))}</a></nav></header><main>',
              '<div class="cards">' + cards + '</div>',
              '<section id="scores"><h2>' + _term('기준 후보') + ' → ' + text(_s('선택된 ')) + _term('검증') + text(_s(' 결과')) + '</h2>'
              f'<p class="subtle">{text(_s("같은 그룹의 검증 집계만 비교합니다. 지표 방향과 차이는 기록된 리포트를 따르며 없는 점수는 0으로 취급하지 않습니다."))}</p></section>']
    parts.extend(_comparison(group, index) for index, group in enumerate(report['groups']))
    parts.extend((_test_results(report), _journey(report), _evaluations(root, report),
                  _candidates(root, report), _failures(report), _stages(report), _provenance(report)))
    parts.extend(('</main><footer>' + text(_s('일부만 기록된 하네스 사용량을 전체 사용량으로 표시하지 않습니다. 데이터·모델·예산이 같은 실험끼리 비교하세요. ')) +
                  '<a href="summary.json">summary.json</a> · <a href="events.jsonl">events.jsonl</a> · '
                  '<a href="report.md">report.md</a></footer></body></html>',))
    return '\n'.join(parts)


def write_html_report(root: Path, summary: dict, report: dict | None = None,
                      *, language: str | None = None) -> Path:
    if report is None:
        from agent_optimizer.report_model import build_report
        report = build_report(root, summary)
    token = _language.set(language or summary.get('report_language') or current_language())
    try:
        document = _render_report(root, report)
    finally:
        _language.reset(token)
    temporary = root / 'report.html.tmp'
    temporary.write_text(document, encoding='utf-8')
    target = root / 'report.html'
    temporary.replace(target)
    return target


def write_session_index(root: Path, entries: list[dict], *, language: str | None = None) -> Path:
    """Link separate dataset experiments without comparing incompatible scores."""
    token = _language.set(language or current_language())
    try:
        document = _render_session_index(root, entries)
    finally:
        _language.reset(token)
    temporary = root / 'index.html.tmp'
    temporary.write_text(document, encoding='utf-8')
    target = root / 'index.html'
    temporary.replace(target)
    return target


def _render_session_index(root, entries):
    cards = []
    for item in entries:
        link = f'<span class="subtle">{text(_s("생성된 리포트 없음"))}</span>'
        if item.get('report'):
            link = _link(root, item['report'], _s('데이터셋 리포트 열기 ↗')) or link
        cards.append(f'<div class="card"><span class="eyebrow">{text(_s("데이터셋"))}</span>'
                     f'<strong>{text(item.get("dataset", ""), 200)}</strong>'
                     f'<span>{text(_s("상태"))}: {_display(item.get("status", "unknown"), STATES)}</span><p>{link}</p>'
                     + (f'<p class="bad">{text(item["error"], 500)}</p>' if item.get('error') else '')
                     + '</div>')
    document = (f'<!doctype html><html lang="{_language.get()}"><head><meta charset="utf-8">'
                 '<meta name="viewport" content="width=device-width,initial-scale=1">'
                 '<meta http-equiv="Content-Security-Policy" '
                 'content="default-src \'none\'; style-src \'unsafe-inline\'">'
                 f'<title>Agent Optimizer · {text(_s("데이터셋 세션"))}</title><style>{STYLE}</style></head>'
                 f'<body><header><div class="eyebrow">Agent Optimizer / {text(_s("데이터셋 세션"))}</div>'
                 f'<h1>{text(_s("데이터셋별 독립 평가"))}</h1><p class="lede">{text(_s("각 데이터셋은 자체 채점기를 사용합니다. "))}'
                 + _term('독립 평가') + ' ' + text(_s('결과를 함께 순위화하지 마세요.')) + '</p>'
                 '</header><main><div class="cards">' + ''.join(cards) + '</div></main>'
                 f'<footer><a href="summary.json">{text(_s("세션 summary.json"))}</a></footer></body></html>')
    return document
