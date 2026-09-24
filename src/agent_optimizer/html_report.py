"""Self-contained, escaped HTML view over the canonical report model."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from urllib.parse import quote

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.report_style import STYLE
from agent_optimizer.workspace import safe_path


def text(item, limit=None):
    value = str(item) if item is not None else "—"
    return html.escape(value if limit is None else value[:limit], quote=True)


def value(item):
    if item is None:
        return '<span class="subtle">—</span>'
    if type(item) in (int, float):
        try:
            if math.isfinite(item):
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
                     f'{text(label)}</th>' for index, label in enumerate(headers))
    return (f'<div class="table-scroll"><table><caption>{text(caption)}</caption>'
            f'<thead><tr>{titles}</tr></thead><tbody>'
            + (''.join(body) or f'<tr><td colspan="{len(headers)}" class="subtle">Not evaluated</td></tr>')
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
        return '<span class="subtle">Not reported</span>'
    return ', '.join(f'<strong>{text(key)}:</strong> {value(number)}'
                     for key, number in items.items())


def _aggregate_rows(rows, group_label=None):
    rendered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = ([text(group_label)] if group_label is not None else []) + [
            text(row.get('candidate_id')), text(row.get('split')),
            _metrics(row.get('metrics')), _count(row.get('trial_count'))]
        rendered.append(_cells(cells, numeric=(4,) if group_label is not None else (3,)))
    return rendered


def _metadata(report):
    configuration = report.get('configuration') or {}
    provenance = report.get('provenance') or {}
    benchmark = provenance.get('benchmark') or {}
    objective = report.get('objective') or {}
    measures = objective.get('metrics') or []
    objective_label = ', '.join(f'{metric.get("name", "—")} ({metric.get("direction", "—")})'
                                for metric in measures if isinstance(metric, dict)) or 'Not recorded'
    stages = configuration.get('stages') or []
    fields = (
        ('Benchmark ID', benchmark.get('id')), ('Benchmark path', configuration.get('benchmark')),
        ('Objective', objective_label), ('Selection', f'{objective.get("mode", "—")} · keep={objective.get("keep", "—")}'),
        ('Budget', configuration.get('budget') or {}),
        ('Optimizers', ', '.join(str(item.get('optimizer', '—')) for item in stages if isinstance(item, dict)) or 'Not recorded'),
        ('Agent × Harness', ', '.join(group['key'] for group in report['groups']) or 'Not recorded'),
        ('Run ID', report['identity'].get('run_id')),
    )
    return '<dl class="meta">' + ''.join(
        f'<div><dt>{text(label)}</dt><dd class="{"mono" if label == "Run ID" else ""}">'
        f'{text(json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item)}</dd></div>'
        for label, item in fields) + '</dl>'


def _comparison(group, number):
    selected = group.get('selected') or []
    chosen = ', '.join(str(item.get('candidate_id')) for item in selected if isinstance(item, dict)) or 'Not selected'
    baseline = group.get('baseline') or {}
    counts = group['counts']
    heading = (f'<section class="group" id="group-{number}"><div class="group-heading">'
               f'<h2>{text(group["agent_id"])} / {text(group["harness_id"])}</h2>'
               f'<span class="pill {"good" if group["comparison_trend"] == "improved" else ""}">'
               f'{text(group["comparison_trend"])}</span></div>'
               f'<p class="subtle">{_count(counts.get("completed_evaluations"))} completed · '
               f'{_count(counts.get("passed_evaluations"))} passed · '
               f'{_count(counts.get("failed_evaluations"))} failed · '
               f'{_count(counts.get("trials_used"))} trials used (budget)</p>'
               f'<p>Baseline: <code>{text(baseline.get("candidate_id"))}</code> → '
               f'{"Validation winner" if selected else "Selected validation"}: '
               f'<code>{text(chosen)}</code></p>')
    rows = []
    for metric in group['comparison']:
        difference = _signed(metric.get('delta'))
        if metric.get('delta_pp') is not None:
            difference += f' <span class="tag">({_signed(metric["delta_pp"])} pp)</span>'
        rows.append(_cells((text(metric.get('name')), text(metric.get('direction')),
                            value(metric.get('baseline')), value(metric.get('selected')),
                            difference, text(metric.get('trend'))), numeric=(2, 3, 4)))
    return heading + _table('Validation · baseline → selected',
                            ('Metric', 'Direction', 'Baseline', 'Selected', 'Delta', 'Trend'),
                            rows, numeric=(2, 3, 4)) + '</section>'


def _test_results(report):
    rows = []
    for group in report['groups']:
        rows.extend(_aggregate_rows(group.get('final_test') or [], group['key']))
    return ('<section id="held-out-test"><h2>Held-out test</h2>'
            '<p class="subtle">Test is recorded after validation selection; it does not direct search. '
            'Scores are shown separately for every Agent × Harness group.</p>'
            + _table('Final test · recorded aggregates',
                     ('Group', 'Candidate', 'Split', 'Metrics', 'Trials'), rows, numeric=(4,)) + '</section>')


def _recorded_events(report, group):
    events = [event for event in report.get('events', [])
              if isinstance(event, dict) and isinstance(event.get('event'), str)
              and event.get('event') != 'trial_completed'
              and event.get('agent_id') == group['agent_id']
              and event.get('harness_id') == group['harness_id']]
    if not events:
        return '<p class="subtle">No recorded structure; consult the evaluation table below.</p>'
    parts = ['<p class="subtle">No recorded structure; recorded group events in log order. '
             'Open raw evidence for additional fields.</p><ol class="lineage">']
    for event in events:
        context = ' · '.join(f'{name}: {text(event[name], 120)}' for name in (
            'timestamp', 'stage_id', 'phase', 'status', 'candidate_id', 'task_id')
            if event.get(name) is not None)
        parts.append(f'<li><strong>{text(event["event"], 120)}</strong>'
                     + (f' <span class="tag">{context}</span>' if context else '')
                     + _details('Raw event', _json(event)) + '</li>')
    return ''.join(parts) + '</ol>'


def _journey(report):
    sections = ['<section id="journey"><h2>Optimization journey</h2>']
    for group in report['groups']:
        structure = group.get('structure') or {}
        units = structure.get('units') or []
        edges = structure.get('edges') or []
        sections.append(f'<h3>{text(group["key"])} · {text(structure.get("kind") or "recorded evidence")}</h3>')
        if units:
            sections.append('<ol class="lineage">')
            for unit in units:
                sections.append(f'<li><strong>{text(unit.get("label") or unit.get("unit_id"))}</strong> '
                                f'<span class="tag">{text(unit.get("unit_type"))} · '
                                f'stage {text(unit.get("stage_id"))}</span> · '
                                f'parent unit {text(unit.get("parent_unit_id"))} · '
                                f'candidates {text(", ".join(unit.get("candidate_ids") or []) or "—")} · '
                                f'evaluation refs {text(", ".join(unit.get("evaluation_refs") or []) or "—")}</li>')
            sections.append('</ol>')
        else:
            sections.append(_recorded_events(report, group))
        if edges:
            sections.append('<p class="tag">Recorded candidate parent relationships</p><ul class="lineage">')
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
    return _details('Full feedback · ' + message[:90], '<pre class="feedback">' + text(message) + '</pre>')


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
        link = _link(root, reference, label)
        if link:
            links.append(link)
    return ' · '.join(links) or value(None)


def _evaluations(root, report):
    sections = ['<section id="evaluations"><h2>Evaluation evidence</h2>'
                '<p class="subtle">Each row is one recorded trial. Per-task metrics are not overall scores.</p>']
    for index, group in enumerate(report['groups']):
        rows = []
        for position, entry in enumerate(group['evaluations']):
            failure = entry.get('failure') or {}
            label = text(entry.get('status'))
            if failure:
                label += f' · <span class="bad">{text(failure.get("category"))}</span>'
            refs = _evidence_links(root, entry)
            rows.append(_cells((text(entry.get('trial_id')), text(entry.get('candidate_id')),
                                text(entry.get('task_id')), text(entry.get('split')),
                                text(entry.get('stage_id')), text(entry.get('repeat')),
                                label, _metrics(entry.get('metrics')),
                                _feedback(entry.get('feedback')) + (f'<p>{refs}</p>' if refs != value(None) else '')),
                               row_class='row-failed' if failure else '',
                               row_id=f'evaluation-{index}-{position}'))
        sections.append(_table(f'{group["key"]} · recorded evaluations',
                               ('Trial', 'Candidate', 'Task', 'Split', 'Stage', 'Repeat',
                                'Status / cause', 'Observed metrics', 'Feedback / logs'), rows))
    if not report['groups']:
        sections.append(_table('Recorded evaluations', ('Trial', 'Candidate', 'Task', 'Split',
                                                        'Status / cause'), []))
    return ''.join(sections) + '</section>'


def _candidates(root, report):
    sections = ['<section id="candidates"><h2>Candidate changes</h2>']
    for index, group in enumerate(report['groups']):
        selected = group.get('selected') or []
        sections.append(f'<h3>{text(group["key"])} · selected validation</h3>')
        if not selected:
            sections.append('<p class="subtle">No selected candidate</p>')
        for row in selected:
            if not isinstance(row, dict):
                continue
            identifier = row.get('candidate_id')
            candidate = next((item for item in group['candidates'] if item['candidate_id'] == identifier), None)
            sections.append(f'<div class="panel best"><strong>BEST · {text(identifier)}</strong> '
                            f'<span class="tag">{text(row.get("split"))} aggregate · '
                            f'{_count(row.get("trial_count"))} trials</span><p>{_metrics(row.get("metrics"))}</p>')
            if candidate:
                sections.append(f'<p>Parents: {text(", ".join(candidate.get("parents") or []) or "—")} · '
                                f'Producer: {text(candidate.get("producer"))} · '
                                f'Changed files: <code>{text(", ".join(map(str, candidate.get("changed_files") or [])) or "—")}</code></p>')
                diff = _link(root, candidate.get('diff_path'), 'changes.diff')
                bundle = _link(root, candidate.get('snapshot_path'), 'Snapshot bundle', directory=True)
                sections.append('<p>' + ' · '.join(item for item in (diff, bundle) if item) + '</p>')
                if candidate.get('diff_preview'):
                    sections.append(_details('Diff preview', '<pre>' + text(candidate['diff_preview']) + '</pre>'))
            else:
                sections.append('<p class="subtle">No recorded candidate files</p>')
            history = [(position, entry) for position, entry in enumerate(group['evaluations'])
                       if entry.get('candidate_id') == identifier]
            sections.append('<p>Evaluation history: ' + (', '.join(
                f'<a href="#evaluation-{index}-{position}">{text(entry.get("trial_id"))} '
                f'({text(entry.get("split"))})</a>'
                for position, entry in history) or 'Not evaluated') + '</p></div>')
        sections.append('<p class="tag">Other recorded candidates: ' +
                        text(', '.join(item['candidate_id'] for item in group['candidates']
                                       if item['candidate_id'] not in [row.get('candidate_id') for row in selected
                                                                       if isinstance(row, dict)]) or '—') + '</p>')
    return ''.join(sections) + '</section>'


def _failures(report):
    sections = ['<section id="failures"><h2>Failure evidence</h2>']
    identity = report['identity']
    if identity.get('failure'):
        failure = identity['failure']
        sections.append('<div class="panel bad"><strong>Run stopped: ' + text(failure.get('category')) +
                        ' · ' + text(identity.get('error_type')) + '</strong>' +
                        _details('Full run error', '<pre>' + text(identity.get('error')) + '</pre>') + '</div>')
    for index, group in enumerate(report['groups']):
        for failure in group['failures']:
            evaluation = next(((position, item) for position, item in enumerate(group['evaluations'])
                               if item.get('id') == failure.get('evaluation_ref')), None)
            trial = (f'<a href="#evaluation-{index}-{evaluation[0]}">'
                     f'{text(evaluation[1].get("trial_id"))}</a>') if evaluation else text(failure.get('evaluation_ref'))
            sections.append('<div class="panel"><strong class="bad">' + text(failure.get('category')) +
                            '</strong> · ' + text(group['key']) + ' · ' + trial +
                            (_details('Full failure message', '<pre>' + text(failure['message']) + '</pre>')
                             if failure.get('message') else '') + '</div>')
    if len(sections) == 1:
        sections.append('<p class="subtle">No classified failures recorded.</p>')
    return ''.join(sections) + '</section>'


def _stages(report):
    sections = ['<section id="stages"><h2>Stages, checkpoints &amp; usage</h2>']
    for group in report['groups']:
        sections.append(f'<h3>{text(group["key"])}</h3>')
        for stage in group.get('stages') or []:
            sections.append(f'<div class="panel"><strong>{text(stage.get("id"))} · '
                            f'{text(stage.get("optimizer"))}</strong><p class="subtle">'
                            f'Status: {text(stage.get("status"))} · '
                            f'Observed stage wall time: {value(stage.get("stage_wall_time_seconds"))} s</p>')
            sections.append(_table('Stage-selected validation aggregates',
                                   ('Candidate', 'Split', 'Metrics', 'Trials'),
                                   _aggregate_rows(stage.get('selected') or []), numeric=(3,)))
            sections.append(_details('Stage evaluated aggregates and raw checkpoint',
                                     _table('Stage-evaluated aggregates',
                                            ('Candidate', 'Split', 'Metrics', 'Trials'),
                                            _aggregate_rows(stage.get('evaluated') or []), numeric=(3,))
                                     + _json(stage.get('checkpoint') or {})))
            sections.append('</div>')
        sections.append('<p class="subtle">Optimizer usage is observed per stage. Harness-reported '
                        'Agent usage is only complete where all expected valid trials have values; '
                        'missing values are unknown.</p>')
        sections.append(_details('Optimizer usage', _json(group.get('optimizer_usage') or [])))
        sections.append(_details('Agent usage (harness reported)', _json(group.get('agent_usage') or [])))
    return ''.join(sections) + '</section>'


def _provenance(report):
    manifest = report.get('provenance') or {}
    benchmark = manifest.get('benchmark') or {}
    content = {'agents': manifest.get('agents', []),
               'dataset_provenance': benchmark.get('dataset_provenance', {}),
               'models': manifest.get('resolved_models', {}),
               'plugin_sha256': manifest.get('plugin_sha256', {})}
    return ('<section id="provenance"><h2>Reproducibility &amp; provenance</h2>'
            '<p>Benchmark SHA-256: <code>' + text(manifest.get('benchmark_sha256')) + '</code></p>'
            + _details('Experiment configuration', _json(report.get('configuration') or {}))
            + _details('Source locks, models and plugin hashes', _json(content)) + '</section>')


def _render_report(root: Path, report: dict) -> str:
    identity = report['identity']
    counts = report['counts']
    title = (report.get('configuration') or {}).get('name') or identity.get('run_id') or 'Experiment'
    synthetic = ('<span class="pill warning">Synthetic fixture — no model-performance claim</span>'
                 if identity.get('synthetic') else
                 '<span class="pill">Benchmark evidence (verify model evidence separately)</span>')
    cards = ''.join(f'<div class="card"><strong>{_count(counts.get(key))}</strong><span>{label}</span></div>'
                    for key, label in (('groups', 'Agent × Harness groups'),
                                       ('completed_evaluations', 'Completed evaluations'),
                                       ('passed_evaluations', 'Passed evaluations'),
                                       ('failed_evaluations', 'Failed evaluations'),
                                       ('trials_used', 'Trials used (budget)')))
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'style-src \'unsafe-inline\'; img-src data:">',
             f'<title>Agent Optimizer · {text(title)}</title><style>{STYLE}</style></head><body>',
             '<header><div class="eyebrow">Agent Optimizer / Experiment analysis</div>',
             f'<h1>{text(title)}</h1><span class="pill">{text(identity.get("status"))}</span>{synthetic}',
             _metadata(report),
             '<nav aria-label="Report sections"><a href="#scores">Comparison</a>'
             '<a href="#held-out-test">Held-out test</a><a href="#journey">Journey</a>'
             '<a href="#evaluations">Evaluations</a><a href="#candidates">Candidates</a>'
             '<a href="#failures">Failures</a><a href="#stages">Stages &amp; usage</a>'
             '<a href="#provenance">Reproduce</a></nav></header><main>',
             '<div class="cards">' + cards + '</div>',
             '<section id="scores"><h2>Baseline → selected validation</h2>'
             '<p class="subtle">Within-group validation aggregates only; direction and difference '
             'come from the canonical report. Missing scores are not zero.</p></section>']
    parts.extend(_comparison(group, index) for index, group in enumerate(report['groups']))
    parts.extend((_test_results(report), _journey(report), _evaluations(root, report),
                  _candidates(root, report), _failures(report), _stages(report), _provenance(report)))
    parts.extend(('</main><footer>Partial harness usage is never labeled complete. Compare only '
                  'runs using equivalent data, model and budget. '
                  '<a href="summary.json">summary.json</a> · <a href="events.jsonl">events.jsonl</a> · '
                  '<a href="report.md">report.md</a></footer></body></html>',))
    return '\n'.join(parts)


def write_html_report(root: Path, summary: dict, report: dict | None = None) -> Path:
    if report is None:
        from agent_optimizer.report_model import build_report
        report = build_report(root, summary)
    temporary = root / 'report.html.tmp'
    temporary.write_text(_render_report(root, report), encoding='utf-8')
    target = root / 'report.html'
    temporary.replace(target)
    return target


def write_session_index(root: Path, entries: list[dict]) -> Path:
    """Link separate dataset experiments without comparing incompatible scores."""
    cards = []
    for item in entries:
        link = '<span class="subtle">No report produced</span>'
        if item.get('report'):
            link = _link(root, item['report'], 'Open dataset report ↗') or link
        cards.append('<div class="card"><span class="eyebrow">Dataset</span>'
                     f'<strong>{text(item.get("dataset", ""), 200)}</strong>'
                     f'<span>Status: {text(item.get("status", "unknown"))}</span><p>{link}</p>'
                     + (f'<p class="bad">{text(item["error"], 500)}</p>' if item.get('error') else '')
                     + '</div>')
    document = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" '
                'content="default-src \'none\'; style-src \'unsafe-inline\'">'
                f'<title>Agent Optimizer · Dataset session</title><style>{STYLE}</style></head>'
                '<body><header><div class="eyebrow">Agent Optimizer / Dataset session</div>'
                '<h1>Independent evaluations</h1><p class="lede">Each dataset uses its own '
                'scorer. Do not rank scores from different evaluators as directly comparable.</p>'
                '</header><main><div class="cards">' + ''.join(cards) + '</div></main>'
                '<footer><a href="summary.json">Session summary.json</a></footer></body></html>')
    temporary = root / 'index.html.tmp'
    temporary.write_text(document, encoding='utf-8')
    target = root / 'index.html'
    temporary.replace(target)
    return target
