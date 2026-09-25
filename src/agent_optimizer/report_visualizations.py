"""근거가 있는 분석 데이터만 SVG와 인쇄 가능한 HTML로 표현한다."""
from __future__ import annotations

import html
import math


LABELS = {"passed": "통과", "failed": "미해결", "mixed": "반복 결과 혼합",
          "unknown": "미확인", "timeout": "시간 초과", "infrastructure": "실행 환경 오류",
          "execution": "실행 오류", "run_error": "실험 오류", "scored_failure": "채점 실패",
          "unsupported": "미지원", "interrupted": "중단", "completed": "완료",
          "invalid": "무효", "improved": "최고점 갱신", "equal": "동률",
          "regressed": "최고점 미달", "unchanged": "변화 없음",
          "baseline": "기준", "first": "첫 관측"}
SPLITS = {"train": "학습", "validation": "검증", "test": "테스트"}


def _text(value):
    return html.escape(str(value) if value is not None else "—", quote=True)


def _number(value):
    if type(value) not in (int, float):
        return "—"
    try:
        if not math.isfinite(value):
            return "—"
    except OverflowError:
        return "—"
    if value != 0 and (abs(value) < 0.01 or abs(value) >= 1e9):
        return f"{value:.6g}"
    return f"{value:.3f}"


def _numeric(value):
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _scale(value, minimum, maximum, low, high):
    return low + (value - minimum) / (maximum - minimum or 1) * (high - low)


def _metric(group, name):
    return next((item for item in group.get("comparison", []) if item.get("name") == name), None)


def render_progress(group, objective, index=0):
    specs = objective.get("metrics") or []
    if not specs or not isinstance(specs[0], dict):
        return ""
    metric = specs[0].get("name")
    points = (group.get("visualization") or {}).get("progress") or []
    usable = [(position, point, _numeric((point.get("metrics") or {}).get(metric)),
               _numeric((point.get("best_metrics") or {}).get(metric)))
              for position, point in enumerate(points)]
    valid = [(position, point, score, best) for position, point, score, best in usable
             if score is not None and best is not None and point.get("improvement") != "invalid"]
    if len(valid) < 2:
        return ""
    scores = [number for _, _, score, best in valid for number in (score, best)]
    low, high = min(scores), max(scores)
    padding = (high - low) * .13 or max(abs(high) * .1, .1)
    low, high = low - padding, high + padding
    if (specs[0].get("source") == "passed" and specs[0].get("aggregate", "mean") == "mean"
            and all(0 <= score <= 1 for score in scores)):
        low, high = max(0, low), min(1, high)
    x = lambda position: _scale(position, 0, max(len(points) - 1, 1), 80, 714)
    y = lambda score: _scale(score, low, high, 155, 24)
    base = next((score for _, point, score, _ in valid if point.get("improvement") == "baseline"), None)
    baseline = (f'<line class="baseline-line" x1="80" y1="{y(base):.2f}" x2="714" '
                f'y2="{y(base):.2f}"/>' if base is not None else "")
    path = []
    for position, _, _, best in valid:
        if not path:
            path.append(f"M{x(position):.2f},{y(best):.2f}")
        else:
            path.append(f"H{x(position):.2f} V{y(best):.2f}")
    dots = []
    boundaries = []
    for position, point, score, _ in valid:
        chosen = point.get("selected")
        if position and point.get("stage_id") != points[position - 1].get("stage_id"):
            boundary = (x(position) + x(position - 1)) / 2
            boundaries.append(f'<line class="stage-boundary" x1="{boundary:.2f}" y1="24" '
                              f'x2="{boundary:.2f}" y2="155"/>')
        dots.append(f'<circle class="trial-point{" chosen-point" if chosen else ""}" '
                    f'cx="{x(position):.2f}" cy="{y(score):.2f}" r="{7 if chosen else 5}"/>'
                    f'<text class="axis-label" x="{x(position):.2f}" y="185" text-anchor="middle">'
                    f'{position + 1}</text>')
    rows = []
    for position, point in enumerate(points):
        metrics = point.get("metrics") or {}
        state = LABELS.get(point.get("improvement"), "미확인")
        selected = " · 최종 선택" if point.get("selected") else ""
        rows.append(f'<li class="progress-item"><span class="trail-index">{position + 1:02d}</span>'
                    f'<code title="{_text(point.get("candidate_id"))}">{_text(point.get("candidate_id"))}</code>'
                    f'<span class="trail-score">{_text(point.get("stage_id"))} · '
                    + ' · '.join(f'{_text(spec["name"])} {_number(metrics.get(spec["name"]))}'
                                 for spec in specs if isinstance(spec, dict) and "name" in spec)
                    + '</span>'
                    f'<span class="trail-state">{state}{selected}</span></li>')
    best_at = next((i + 1 for i in range(len(points) - 1, -1, -1)
                    if points[i].get("improvement") == "improved"), None)
    insight = (f'<p class="insight">마지막 최고점 갱신: 후보 평가 {best_at}/{len(points)}. '
               f'이후 {len(points) - best_at}건의 후보 평가에서 갱신 없음.</p>'
               if best_at is not None and len(points) > best_at else "")
    return (f'<section class="visual-section" id="progress-{index}"><div class="section-heading">'
            '<span class="eyebrow">01 / 검증 집계</span><h3>최적화 개선 추이</h3></div>'
            '<p class="subtle">동일 그룹의 후보별 검증 집계만 비교합니다. 점은 후보 점수, 계단선은 '
            '지금까지의 최고점입니다. 최종 선택은 별도로 표시합니다.</p>'
            f'<svg class="chart progress-chart" viewBox="0 0 760 207" role="img" '
            f'aria-labelledby="progress-title-{index} progress-desc-{index}">'
            f'<title id="progress-title-{index}">검증 점수 추이</title>'
            f'<desc id="progress-desc-{index}">{_text(metric)} 후보 점수와 누적 최고점; '
            '아래 목록에 각 후보의 실제 값과 선택 상태가 있습니다.</desc>'
            f'<line class="chart-grid" x1="80" y1="24" x2="714" y2="24"/>'
            f'<line class="chart-grid" x1="80" y1="155" x2="714" y2="155"/>'
            f'<text class="axis-label" x="63" y="28" text-anchor="end">{_number(high)}</text>'
            f'<text class="axis-label" x="63" y="159" text-anchor="end">{_number(low)}</text>'
            + baseline + ''.join(boundaries) + f'<path class="best-curve" d="{" ".join(path)}"/>'
            + ''.join(dots) + '<text class="axis-label" x="714" y="203" text-anchor="end">'
            '후보 평가 순서 →</text></svg>'
            '<div class="legend"><span><i class="legend-dot"></i> 후보 점수</span>'
            '<span><i class="legend-line"></i> 최고점</span>'
            '<span><i class="legend-dash"></i> 기준 점수</span>'
            '<span><i class="legend-dash"></i> 단계 경계</span>'
            '<span><i class="legend-ring"></i> 최종 선택</span></div>'
            + insight + '<ol class="progress-list">' + ''.join(rows) + '</ol></section>')


def render_comparison(group, objective, index=0):
    metrics = group.get("comparison") or []
    if not metrics:
        return ""
    lines = []
    for item in metrics:
        before, after = _numeric(item.get("baseline")), _numeric(item.get("selected"))
        delta = item.get("delta")
        delta_label = (("+" if delta >= 0 else "") + _number(delta)) if delta is not None else "—"
        if item.get("delta_pp") is not None:
            delta_label += f' ({item["delta_pp"]:+.1f} pp)'
        bars = ""
        if before is not None and after is not None and before >= 0 and after >= 0:
            maximum = max(before, after, 0.000001)
            bars = (f'<div class="comparison-bars"><span>기준 후보</span>'
                    f'<div class="bar-track"><i class="bar baseline-bar" style="width:{before / maximum * 100:.2f}%"></i></div>'
                    f'<strong>{_number(before)}</strong><span>최종 선택</span>'
                    f'<div class="bar-track"><i class="bar selected-bar" style="width:{after / maximum * 100:.2f}%"></i></div>'
                    f'<strong>{_number(after)}</strong></div>')
        lines.append(f'<div class="metric-comparison"><div class="metric-heading"><strong>{_text(item["name"])}</strong>'
                     f'<span>{"↑ 높을수록 좋음" if item["direction"] == "maximize" else "↓ 낮을수록 좋음"}'
                     f' · {LABELS.get(item.get("trend"), item.get("trend", "미확인"))}</span>'
                     f'<b>{_text(delta_label)}</b></div>{bars or "<p>비교 막대에 필요한 유효한 비음수 값이 없습니다.</p>"}</div>')
    return (f'<section class="visual-section" id="comparison-{index}"><div class="section-heading">'
            '<span class="eyebrow">02 / 확정된 선택</span><h3>기준 후보와 최종 선택</h3></div>'
            '<p class="subtle">동일 그룹의 기준 후보와 검증에서 최종 선택된 후보입니다. '
            '막대는 각 지표 내에서만 비교합니다.</p>' + ''.join(lines) + '</section>')


def render_landscape(group, objective, index=0):
    specs = objective.get("metrics") or []
    if len(specs) != 2 or not all(isinstance(spec, dict) for spec in specs):
        return ""
    xname, yname = specs[1].get("name"), specs[0].get("name")
    points = []
    for item in (group.get("visualization") or {}).get("progress") or []:
        metrics = item.get("metrics") or {}
        x, y = _numeric(metrics.get(xname)), _numeric(metrics.get(yname))
        if x is not None and y is not None and item.get("improvement") != "invalid":
            points.append((item, x, y))
    if len(points) < 3:
        return ""
    xmin, xmax = min(x for _, x, _ in points), max(x for _, x, _ in points)
    ymin, ymax = min(y for _, _, y in points), max(y for _, _, y in points)
    circles = []
    for item, x, y in points:
        state = " selected" if item.get("selected") else " baseline" if item.get("improvement") == "baseline" else ""
        circles.append(f'<circle class="landscape-point{state}" '
                       f'cx="{_scale(x, xmin, xmax, 65, 708):.2f}" '
                       f'cy="{_scale(y, ymin, ymax, 150, 25):.2f}" r="{7 if state else 5}">'
                       f'<title>{_text(item.get("candidate_id"))}: {_text(xname)} {_number(x)}, '
                       f'{_text(yname)} {_number(y)}</title></circle>')
    return (f'<section class="visual-section" id="landscape-{index}"><div class="section-heading">'
            '<span class="eyebrow">03 / 다중 지표</span><h3>목적 지표 관계</h3></div>'
            '<p class="subtle">후보별 검증 값입니다. 두 지표는 우선순위 순서로 선택하며, '
            '두 축의 교환 관계만 표시합니다.</p>'
            f'<svg class="chart landscape-chart" viewBox="0 0 760 205" role="img" '
            f'aria-label="{_text(xname)}와 {_text(yname)} 후보 관계; 기준은 빈 원, 선택은 강조 원">'
            f'<title>후보별 목적 지표 관계</title><desc>점의 실제 수치는 아래 후보 점수 목록에서 확인합니다.</desc>'
            '<path class="chart-grid" d="M65 25 V150 H708"/>' + ''.join(circles) +
            f'<text class="axis-label" x="68" y="179">{_number(xmin)}</text>'
            f'<text class="axis-label" x="708" y="179" text-anchor="end">{_number(xmax)}</text>'
            f'<text class="axis-label" x="708" y="198" text-anchor="end">{_text(xname)} '
            f'{"↑" if specs[1].get("direction") == "maximize" else "↓"}</text>'
            f'<text class="axis-label" x="57" y="29" text-anchor="end">{_number(ymax)}</text>'
            f'<text class="axis-label" x="57" y="153" text-anchor="end">{_number(ymin)}</text></svg>'
            f'<p class="subtle">세로축: {_text(yname)} '
            f'{"↑" if specs[0].get("direction") == "maximize" else "↓"} · '
            '진한 원: 최종 선택 · 빈 원: 기준 후보</p></section>')


def render_trail(group, index=0):
    candidates = {item["candidate_id"]: item for item in group.get("candidates", [])}
    selected = [item.get("candidate_id") for item in group.get("selected", [])
                if isinstance(item, dict) and item.get("split") == "validation" and item.get("valid") is True]
    if not candidates or not selected:
        return ""
    path = []
    current, seen = selected[0], set()
    while current in candidates and current not in seen and len(path) < 10:
        seen.add(current)
        path.append(current)
        parents = candidates[current].get("parents") or []
        current = parents[0] if parents else None
    if len(path) < 2:
        return ""
    path.reverse()
    scores = {point["candidate_id"]: point for point in
              (group.get("visualization") or {}).get("progress") or []}
    steps = []
    for position, identifier in enumerate(path):
        point = scores.get(identifier) or {}
        state = LABELS.get(point.get("improvement"), "평가 없음")
        steps.append(f'<li class="trail-node"><span class="trail-index">{position + 1:02d}</span>'
                     f'<code title="{_text(identifier)}">{_text(identifier)}</code>'
                     f'<span>{"최종 선택" if identifier == selected[0] else state}</span></li>')
    extras = len(candidates) - len(path)
    return (f'<section class="visual-section" id="trail-{index}"><div class="section-heading">'
            '<span class="eyebrow">04 / 후보 계보</span><h3>선택 후보까지의 경로</h3></div>'
            '<p class="subtle">기록된 부모 관계의 한 경로만 표시합니다. 병합·다른 후보의 '
            '관계는 아래 최적화 과정과 후보 변경 내역에서 확인할 수 있습니다.</p>'
            '<ol class="trail-path">' + ''.join(steps) + '</ol>'
            + (f'<p class="subtle">이 경로 외 기록된 후보 {extras}개</p>' if extras > 0 else '')
            + '</section>')


def render_units(group, objective, index=0):
    units = (group.get("structure") or {}).get("units") or []
    if not units:
        return ""
    scores = {item["candidate_id"]: item for item in
              (group.get("visualization") or {}).get("progress") or []}
    specs = objective.get("metrics") or []
    primary = specs[0].get("name") if specs and isinstance(specs[0], dict) else None

    def render_unit(unit):
        label = unit.get("label") or unit.get("unit_id")
        if (unit.get("unit_type") == "iteration" and isinstance(label, str)
                and label.startswith("Iteration ") and label[10:].isdigit()):
            label = "반복 " + label[10:]
        members = []
        ids = unit.get("candidate_ids") or []
        for identifier in ids[:3]:
            point = scores.get(identifier) or {}
            measured = (point.get("metrics") or {}).get(primary) if primary else None
            state = LABELS.get(point.get("improvement"), "점수 미기록")
            members.append(f'<span><code title="{_text(identifier)}">{_text(identifier)}</code> '
                           f'{_number(measured)} · {state}</span>')
        if len(ids) > 3:
            members.append(f'<span>외 {len(ids) - 3}개 후보</span>')
        return (f'<li class="unit"><span class="eyebrow">{_text(unit.get("stage_id"))} / '
                f'{_text(unit.get("unit_type"))}</span><strong>{_text(label)}</strong>'
                + ('<div class="unit-members">' + ' · '.join(members) + '</div>' if members else
                   '<span class="subtle">연결된 후보 미기록</span>') + '</li>')

    more = ('<details><summary>나머지 탐색 단위 ' + str(len(units) - 8) + '개</summary>'
            '<ol class="unit-flow">' + ''.join(render_unit(unit) for unit in units[8:])
            + '</ol></details>' if len(units) > 8 else '')
    return (f'<section class="visual-section" id="units-{index}"><div class="section-heading">'
            '<span class="eyebrow">04 / 탐색 단위</span><h3>탐색 흐름</h3></div>'
            '<p class="subtle">Optimizer가 명시적으로 기록한 반복·세대·단계의 순서입니다. '
            '후보 점수는 기록된 검증 집계가 있을 때만 표시합니다.</p><ol class="unit-flow">'
            + ''.join(render_unit(unit) for unit in units[:8]) + '</ol>' + more + '</section>')


def render_tasks(group, index=0):
    tasks = (group.get("visualization") or {}).get("task_comparison") or []
    if not tasks:
        return ""
    fixed = sum(row["baseline"] == "failed" and row["selected"] == "passed" for row in tasks)
    lost = sum(row["baseline"] == "passed" and row["selected"] == "failed" for row in tasks)
    cells = ''.join(f'<tr><th scope="row"><code>{_text(item["task_id"])}</code></th>'
                    f'<td><span class="task-state {item["baseline"]}">{LABELS[item["baseline"]]}</span></td>'
                    f'<td><span class="task-state {item["selected"]}">{LABELS[item["selected"]]}</span></td>'
                    f'<td>{"새로 해결" if item["baseline"] == "failed" and item["selected"] == "passed" else "해결 후 미해결" if item["baseline"] == "passed" and item["selected"] == "failed" else "—"}</td></tr>'
                    for item in tasks)
    return (f'<section class="visual-section" id="tasks-{index}"><div class="section-heading">'
            '<span class="eyebrow">05 / 과제별 변화</span><h3>과제별 전후 비교</h3></div>'
            f'<p class="insight">같은 검증 과제 {len(tasks)}개 중 새로 해결 {fixed}개, 해결 후 미해결 {lost}개.</p>'
            '<div class="table-scroll"><table class="task-matrix"><caption>검증 과제 · 기준 후보 → 최종 선택</caption>'
            '<thead><tr><th scope="col">과제</th><th scope="col">기준 후보</th>'
            '<th scope="col">최종 선택</th><th scope="col">변화</th></tr></thead><tbody>'
            + cells + '</tbody></table></div></section>')


def render_timeline(group, index=0):
    rows = (group.get("visualization") or {}).get("trial_timeline") or []
    if not rows:
        return ""
    maximum = max((row["duration_seconds"] for row in rows if row["duration_seconds"] is not None),
                  default=None)
    def render_row(position, row):
        duration = row["duration_seconds"]
        bar = (f'<i class="duration-fill" style="width:{duration / maximum * 100:.2f}%"></i>'
               if duration is not None and maximum and math.isfinite(duration / maximum) else "")
        return (f'<li class="timeline-row"><span class="timeline-id"><code title="{_text(row["trial_id"])}">'
                f'{_text(row["trial_id"])}</code><small>{_text(row["candidate_id"])} · '
                f'{_text(row["task_id"])} · {_text(SPLITS.get(row["split"], row["split"]))} · '
                f'{_text(row["stage_id"])}</small></span>'
                f'<span class="duration-track">{bar}</span>'
                f'<strong class="duration-value">{_number(duration)}초</strong>'
                f'<a class="outcome {_text(row["category"])}" href="#evaluation-{index}-{position}">'
                f'{LABELS.get(row["category"], _text(row["status"]))}</a></li>')
    visible = ''.join(render_row(position, row) for position, row in enumerate(rows[:12]))
    more = ('<details><summary>나머지 평가 ' + str(len(rows) - 12) + '건</summary><ol class="timeline">'
            + ''.join(render_row(position, row) for position, row in enumerate(rows[12:], 12))
            + '</ol></details>' if len(rows) > 12 else '')
    return (f'<section class="visual-section" id="timeline-{index}"><div class="section-heading">'
            '<span class="eyebrow">06 / 실행 진단</span><h3>평가 실행 시간</h3></div>'
            '<p class="subtle">막대는 실제 과제 실행 시간이며 후보 점수와 별개입니다. '
            '미측정 시간은 빈 막대로 표시합니다.</p><ol class="timeline">'
            + visible + '</ol>' + more + '</section>')


def render_outcomes(group, index=0):
    outcomes = (group.get("visualization") or {}).get("outcomes") or {}
    total = sum(outcomes.values())
    if total < 4 or len(outcomes) < 2:
        return ""
    rows = ''.join(f'<li><span>{LABELS.get(name, _text(name))}</span>'
                   f'<span class="bar-track"><i class="bar {"selected-bar" if name == "passed" else "baseline-bar"}" '
                   f'style="width:{count / total * 100:.2f}%"></i></span><strong>{count}</strong></li>'
                   for name, count in sorted(outcomes.items(), key=lambda item: (-item[1], item[0])))
    return (f'<section class="visual-section" id="outcomes-{index}"><div class="section-heading">'
            '<span class="eyebrow">07 / 결과 분포</span><h3>평가 결과 분포</h3></div>'
            '<p class="subtle">과제별 평가 기록의 상태 분류입니다. 후보 단위 개선 건수와 다릅니다.</p>'
            '<ul class="outcome-bars">' + rows + '</ul></section>')
