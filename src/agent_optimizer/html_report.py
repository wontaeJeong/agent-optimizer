"""Self-contained, escaped HTML view over persisted run evidence."""
from __future__ import annotations

import html
import json
import math
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from agent_optimizer.contracts import ConfigurationError
from agent_optimizer.workspace import safe_path


STYLE = """
:root{color-scheme:dark;font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
--bg:#0b1220;--panel:#142138;--line:#32445d;--text:#e7f2ff;--muted:#a9bed4;--accent:#6bd8cb;--gold:#ffcf7c}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 12% 0,#1d3552 0,transparent 32rem),var(--bg);color:var(--text)}
a{color:var(--accent)}a:hover{text-decoration:none}header,main,footer{max-width:1200px;margin:auto;padding:1.5rem}
header{padding-top:3.5rem}.eyebrow{color:var(--accent);font-weight:750;letter-spacing:.18em;text-transform:uppercase;font-size:.76rem}
h1{font-size:clamp(2.1rem,5vw,4rem);letter-spacing:-.045em;margin:.3rem 0}.lede{color:var(--muted);max-width:62ch}
nav{display:flex;flex-wrap:wrap;gap:.8rem;margin:2rem 0}nav a,.pill{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:.38rem .85rem;text-decoration:none}
.pill{font-weight:700;color:var(--accent)}.warning{color:var(--gold)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1rem;margin:1.5rem 0}
.card,.panel{border:1px solid var(--line);border-radius:16px;background:linear-gradient(155deg,#1b2e49,var(--panel));box-shadow:0 12px 35px #05091344}
.card{padding:1.25rem}.card strong{display:block;font-size:1.65rem;letter-spacing:-.03em}.card span{color:var(--muted)}
section{margin:2.2rem 0}h2{font-size:1.45rem;margin:0 0 .7rem;letter-spacing:-.025em}.panel{padding:1.25rem;margin:.85rem 0;overflow:auto}
table{width:100%;border-collapse:collapse;text-align:left;min-width:650px}th,td{padding:.75rem .8rem;vertical-align:top;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:.77rem;text-transform:uppercase;letter-spacing:.08em}tr:last-child td{border:0}td{overflow-wrap:anywhere}
.subtle{color:var(--muted);font-size:.87rem}.mono,code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.85rem}
.bar{height:.55rem;min-width:2px;border-radius:6px;background:linear-gradient(90deg,#42a9b8,#83e4b3)}
details{border-top:1px solid var(--line);margin-top:1rem;padding-top:.7rem}summary{cursor:pointer;color:var(--accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:22rem;overflow:auto}
.tag{font-size:.78rem;color:var(--muted)}.bad{color:#ff9ba3}.good{color:#8ee2bd}footer{color:var(--muted);padding-bottom:3rem}
@media(max-width:600px){header,main,footer{padding:1rem}.panel{padding:.8rem}}
"""


def text(value, limit=4000):
    return html.escape(str(value)[:limit], quote=True)


def value(item):
    if item is None:
        return '<span class="subtle">—</span>'
    if type(item) in (int, float) and math.isfinite(item):
        return text(f"{item:.3f}")
    return text(item, 200)


def metrics(items):
    if not isinstance(items, dict) or not items:
        return '<span class="subtle">Not reported</span>'
    return ", ".join(f"<strong>{text(key)}:</strong> {value(number)}"
                     for key, number in items.items())


def rows(entries):
    output = []
    for entry in entries:
        if entry is None:
            continue
        output.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in (
            text(entry.get("agent_id", "")), text(entry.get("harness_id", "")),
            text(entry.get("candidate_id", "")), text(entry.get("split", "")),
            metrics(entry.get("metrics", {})), text(entry.get("trial_count", "—"))
        )) + "</tr>")
    return "".join(output)


def table(header, body):
    return '<div class="panel"><table><thead><tr>' + "".join(
        f"<th>{text(label)}</th>" for label in header) + "</tr></thead><tbody>" + (
        body or f'<tr><td colspan="{len(header)}" class="subtle">Not evaluated</td></tr>') + "</tbody></table></div>"


def _records(root: Path):
    path = root / "events.jsonl"
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                records.append(entry)
        except ValueError:
            continue  # An interrupted trailing event cannot hide earlier evidence.
    return records


def _candidate_link(root: Path, group: dict, candidate_id: str) -> str:
    relative = "/".join([group["agent_id"], group["harness_id"], "candidates", candidate_id,
                         "changes.diff"])
    try:
        candidate = safe_path(root, relative)
    except ConfigurationError:
        return '<span class="subtle">No recorded diff</span>'
    if not candidate.is_file():
        return '<span class="subtle">No recorded diff</span>'
    return f'<a href="{text(quote(relative, safe="/"))}">View changes.diff ↗</a>'


def write_html_report(root: Path, summary: dict) -> Path:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    events = _records(root)
    trials = [event for event in events if event.get("event") == "trial_completed"]
    groups = summary.get("groups", [])
    stages = [stage for group in groups for stage in group.get("stages", [])]
    spent = sum(t.get("metrics", {}).get("task_wall_time_seconds") or 0 for t in trials)
    status = str(summary.get("status", "unknown"))
    synthetic = bool(summary.get("synthetic", False))
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'style-src \'unsafe-inline\'; img-src data:">',
             f'<title>Agent Optimizer · {text(summary.get("run_id", "Run"))}</title>',
             f'<style>{STYLE}</style></head><body><header>',
             '<div class="eyebrow">Agent Optimizer / Run intelligence</div>',
             f'<h1>Experiment {text(summary.get("run_id", ""))}</h1>',
             '<p class="lede">Compare independent optimization stages, investigate slow evaluations, '
             'and trace how the final Agent was selected.</p>',
             f'<span class="pill">{text(status)}</span> ',
             '<span class="pill warning">Synthetic fixture — no model-performance claim</span>'
             if synthetic else '<span class="pill">Real benchmark (verify model evidence separately)</span>',
             '<nav><a href="#scores">Scores</a><a href="#stages">Optimizers</a>'
             '<a href="#slow">Timing</a><a href="#trials">Trials</a>'
             '<a href="#provenance">Provenance</a></nav></header><main>',
             '<div class="cards">',
             f'<div class="card"><strong>{text(len(groups))}</strong><span>Agent × Harness groups</span></div>',
             f'<div class="card"><strong>{text(len(stages))}</strong><span>Optimizer stages</span></div>',
             f'<div class="card"><strong>{text(summary.get("trials_used", 0))}</strong><span>Trials used</span></div>',
             f'<div class="card"><strong>{spent:.1f}s</strong><span>Summed task wall time</span></div>',
             '</div>']
    if summary.get("error"):
        parts.append('<div class="panel bad"><strong>Run stopped: '
                     + text(summary.get("error_type", "error")) + '</strong><p>'
                     + text(summary["error"], 1000) + '</p></div>')

    baseline = [group.get("baseline") for group in groups]
    selected = [row for group in groups for row in group.get("selected", [])]
    tested = [row for group in groups for row in group.get("final_test", [])]
    header = ("Agent", "Harness", "Candidate", "Split", "Metrics", "Trials")
    parts += ['<section id="scores"><h2>Baseline → selected winner → held-out test</h2>',
              '<p class="subtle">Selection is frozen using validation; test never directs the search. '
              'A missing test is not a zero score.</p>',
              '<div class="eyebrow">Baseline</div>', table(header, rows(baseline)),
              '<div class="eyebrow">Validation winner</div>', table(header, rows(selected)),
              '<div class="eyebrow">Held-out test</div>', table(header, rows(tested)), '</section>',
              '<section id="stages"><h2>Optimizer decisions</h2>']
    for group in groups:
        parts += [f'<div class="panel"><span class="eyebrow">{text(group.get("agent_id", ""))} '
                  f'/ {text(group.get("harness_id", ""))}</span>']
        for stage in group.get("stages", []):
            parts += [f'<h3>{text(stage.get("id", ""))} · {text(stage.get("optimizer", ""))}</h3>',
                      f'<p class="subtle">Status: {text(stage.get("status", "unknown"))} · '
                      f'Elapsed: {value(stage.get("stage_wall_time_seconds"))}s</p>',
                      table(header, rows(stage.get("selected", []))),
                      '<details><summary>Evaluated candidates and checkpoint</summary>',
                      table(header, rows(stage.get("evaluated", []))),
                      '<pre>' + text(json.dumps(stage.get("checkpoint", {}), indent=2, ensure_ascii=False),
                                    12000) + '</pre></details>']
        changes = [_candidate_link(root, group, row.get("candidate_id", ""))
                   for row in group.get("selected", [])]
        parts += ['<h3>Candidate changes</h3>', "<p>" + (" · ".join(changes) if changes else
                   '<span class="subtle">No selected candidate</span>') + "</p>",
                  '<h3>Optimizer usage</h3><p class="subtle">Only observed token/cost values are shown; '
                  'missing values are unknown, not zero.</p>',
                  '<pre>' + text(json.dumps(group.get("optimizer_usage", []), indent=2,
                                           ensure_ascii=False), 8000) + '</pre></div>']
    parts.append('</section><section id="slow"><h2>Slowest tasks &amp; datasets</h2>')
    timed = sorted((event for event in trials
                    if type(event.get("metrics", {}).get("task_wall_time_seconds")) in (int, float)),
                   key=lambda row: -row["metrics"]["task_wall_time_seconds"])
    maximum = max((row["metrics"]["task_wall_time_seconds"] for row in timed), default=1) or 1
    timing_rows = []
    dataset_totals = defaultdict(float)
    for row in timed:
        dataset = row.get("dataset") or manifest.get("benchmark", {}).get("id", "unknown")
        seconds = row["metrics"]["task_wall_time_seconds"]
        dataset_totals[str(dataset)] += seconds
        width = min(100, max(1, 100 * seconds / maximum))
        timing_rows.append("<tr>" + "".join(f"<td>{item}</td>" for item in (
            text(dataset), text(row.get("task_id", "")), text(row.get("stage_id", "")),
            text(row.get("split", "")), f'{seconds:.2f}s<div class="bar" style="width:{width:.1f}%"></div>',
            value(row.get("metrics", {}).get("agent_wall_time_seconds"))
        )) + "</tr>")
    parts += [table(("Dataset", "Task", "Stage", "Split", "Task wall time", "Agent time"),
                    "".join(timing_rows[:20])),
              '<div class="panel"><strong>Dataset total task time</strong><p class="subtle">'
              + (" · ".join(f"{text(name)}: {seconds:.1f}s" for name, seconds in
                            sorted(dataset_totals.items(), key=lambda item: -item[1])) or "No timed trials")
              + "</p></div></section>",
              '<section id="trials"><h2>Trial evidence</h2><p class="subtle">'
              'Feedback is shown as untrusted text; see JSON artifacts for full details.</p>']
    trial_rows = []
    for event in trials[:500]:
        trial_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in (
            text(event.get("task_id", "")), text(event.get("candidate_id", "")),
            text(event.get("split", "")), text(event.get("status", "")),
            metrics(event.get("metrics", {})), text(event.get("feedback", ""), 500)
        )) + "</tr>")
    parts += [table(("Task", "Candidate", "Split", "Status", "Observed metrics", "Feedback"),
                    "".join(trial_rows)), '</section>',
              '<section id="provenance"><h2>Reproducibility &amp; provenance</h2>',
              '<div class="panel"><p><strong>Dataset:</strong> '
              f'{text(manifest.get("benchmark", {}).get("id", "Not recorded"))}</p>',
              f'<p><strong>Benchmark SHA-256:</strong> <code>{text(manifest.get("benchmark_sha256", "—"))}</code></p>',
              '<details><summary>Source locks, models and plugin hashes</summary><pre>' + text(
                  json.dumps({"agents": manifest.get("agents", []),
                              "dataset_provenance": manifest.get("benchmark", {}).get("dataset_provenance", {}),
                              "models": manifest.get("resolved_models", {}),
                              "plugin_sha256": manifest.get("plugin_sha256", {}),
                              "extensions_sha256": manifest.get("extensions_sha256")},
                             indent=2, ensure_ascii=False), 16000) + '</pre></details></div></section></main>',
              '<footer>Partial harness usage is never labeled complete. Compare only runs using '
              'equivalent data, model and budget. <a href="summary.json">summary.json</a> · '
              '<a href="events.jsonl">events.jsonl</a> · <a href="report.md">report.md</a></footer>',
              '</body></html>']
    target = root / "report.html"
    temporary = root / "report.html.tmp"
    temporary.write_text("\n".join(parts), encoding="utf-8")
    temporary.replace(target)
    return target


def write_session_index(root: Path, entries: list[dict]) -> Path:
    """Link separate dataset experiments without comparing incompatible scores."""
    cards = []
    for item in entries:
        link = '<span class="subtle">No report produced</span>'
        if item.get("report"):
            try:
                target = safe_path(root, item["report"])
            except ConfigurationError:
                target = None
            if target is not None and target.is_file():
                link = (f'<a href="{text(quote(item["report"], safe="/"))}">'
                        'Open dataset report ↗</a>')
        cards.append('<div class="card"><span class="eyebrow">Dataset</span>'
                     f'<strong>{text(item.get("dataset", ""), 200)}</strong>'
                     f'<span>Status: {text(item.get("status", "unknown"))}</span><p>{link}</p>'
                     + (f'<p class="bad">{text(item["error"], 500)}</p>' if item.get("error") else '')
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
    temporary = root / "index.html.tmp"
    temporary.write_text(document, encoding="utf-8")
    target = root / "index.html"
    temporary.replace(target)
    return target
