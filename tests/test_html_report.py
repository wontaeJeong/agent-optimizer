"""Offline reports must be useful after success or failure and escape untrusted feedback."""
import contextlib
import io
import json
import os
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from agent_optimizer.cli import main
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import Evaluation, UnavailableError
from agent_optimizer.registry import Registry
from agent_optimizer.runner import run_experiment
from agent_optimizer.html_report import write_html_report, write_session_index
from support import test_project


class HTMLReportTests(unittest.TestCase):
    def setUp(self):
        temporary, self.root = test_project()
        self.addCleanup(temporary.cleanup)
        self.spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        self.spec["_agents"] = self.spec["_agents"][:1]

    def test_run_html_localizes_navigation_status_and_explains_selection(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ko">', page)
        self.assertIn('<span class="pill">완료</span>', page)
        self.assertIn('href="#held-out-test">최종 테스트</a>', page)
        self.assertIn('<span><abbr class="help"', page)
        self.assertIn('title="과제별로 실제 종료되어 기록된 평가 건수입니다."', page)
        self.assertRegex(page, r'<abbr[^>]+title="[^"]+"[^>]+tabindex="0"[^>]*>검증</abbr>')
        self.assertIn('.help:focus-visible::after', page)
        self.assertIn('검증에서 선택된 후보', page)
        self.assertIn('fixture-validation', page)
        self.assertIn('summary.json', page)

    def test_english_run_remembers_report_language_and_one_time_override(self):
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["report_language"], "en")
        self.assertEqual(json.loads((run / "summary.json").read_text())["report_language"], "en")
        page = (run / "report.html").read_text()
        self.assertIn('<html lang="en">', page[:100])
        navigation = page.split('<nav ', 1)[1].split('</nav>', 1)[0]
        self.assertIn('aria-label="Report sections"', navigation)
        self.assertIn('href="#scores">Comparison</a>', navigation)
        self.assertNotIn('리포트 목차', navigation)
        self.assertIn("# Experiment report", (run / "report.md").read_text())
        with patch.dict(os.environ, {"AGENT_OPT_LANG": "ko"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["report", str(run), "--html"]), 0)
        self.assertIn('<html lang="ko">', (run / "report.html").read_text()[:100])
        with patch.dict(os.environ, {"AGENT_OPT_LANG": ""}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["report", str(run), "--html"]), 0)
        self.assertIn('<html lang="en">', (run / "report.html").read_text()[:100])
        self.assertEqual(json.loads((run / "summary.json").read_text())["report_language"], "en")

    def test_english_report_has_no_korean_interface_labels(self):
        class Labels(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ignored = 0
                self.korean = []

            def handle_starttag(self, tag, attrs):
                if tag in {"style", "pre", "code"}:
                    self.ignored += 1
                elif not self.ignored:
                    self.korean.extend(value for key, value in attrs
                                       if key in {"title", "aria-label"} and re.search("[가-힣]", value or ""))

            def handle_endtag(self, tag):
                if tag in {"style", "pre", "code"}:
                    self.ignored -= 1

            def handle_data(self, data):
                if not self.ignored and re.search("[가-힣]", data):
                    self.korean.append(data.strip())

        with patch.dict(os.environ, {"AGENT_OPT_LANG": "en"}):
            run, _ = run_experiment(self.spec, Registry(), self.root / "runs")
        labels = Labels()
        labels.feed((run / "report.html").read_text())
        self.assertFalse(labels.korean, f"한국어 UI 문구 {len(labels.korean)}개: {labels.korean[:12]}")
        summary_line = (run / "report.html").read_text().split('<section class="group"', 1)[1].split('</p>', 1)[0]
        self.assertNotIn("—</span> trials", summary_line)

    def test_session_html_localizes_status_and_explains_dataset_separation(self):
        root = self.root / "session"
        root.mkdir()
        run = root / "dataset-1"
        run.mkdir()
        (run / "report.html").write_text("report", encoding="utf-8")
        page = write_session_index(root, [
            {"dataset": "<private>", "status": "completed", "report": "dataset-1/report.html"},
            {"dataset": "other", "status": "error", "error": "<bad>"},
        ]).read_text(encoding="utf-8")
        self.assertIn('<html lang="ko">', page)
        self.assertIn('데이터셋별 독립 평가', page)
        self.assertIn('상태: 완료', page)
        self.assertIn('상태: 오류', page)
        self.assertIn('title="서로 다른 채점기의 점수를 직접 비교하거나 순위를 매기지 않습니다."', page)
        self.assertIn('&lt;private&gt;', page)
        self.assertIn('&lt;bad&gt;', page)
        self.assertIn('href="dataset-1/report.html"', page)
        self.assertNotIn('<private>', page)

    def test_english_session_index_keeps_links_and_untrusted_dataset_escaped(self):
        root = self.root / "english-session"
        root.mkdir()
        (root / "run").mkdir()
        (root / "run/report.html").write_text("fixture")
        page = write_session_index(root, [{"dataset": "<private>", "status": "completed",
                                           "report": "run/report.html"}], language="en").read_text()
        self.assertIn('<html lang="en">', page[:100])
        self.assertIn("Independent evaluations", page)
        self.assertIn('href="run/report.html"', page)
        self.assertIn("&lt;private&gt;", page)
        self.assertNotIn("<private>", page)

    def test_builtin_iteration_label_is_localized_but_raw_event_is_preserved(self):
        run = self.root / "iteration"
        run.mkdir()
        (run / "events.jsonl").write_text(json.dumps({
            "event": "optimizer_iteration_started", "agent_id": "solo", "harness_id": "fixture",
            "stage_id": "search", "iteration": 3, "candidate_id": "c1",
        }) + "\n", encoding="utf-8")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "selected": [], "final_test": [], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        journey = page.split('<section id="journey">', 1)[1].split('</section>', 1)[0]
        self.assertIn('id="units-0"', page)
        self.assertIn('<strong>반복 3</strong>', journey)
        self.assertNotIn('<strong>Iteration 3</strong>', journey)
        self.assertIn('&quot;iteration&quot;: 3', journey)

    def test_completed_report_shows_splits_timeline_usage_and_candidate_links(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        self.assertEqual(summary["status"], "completed")
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["benchmark"]["dataset_provenance"] = {"image_id": "sha256:checked",
                                                       "revision": "verified-source"}
        manifest_path.write_text(json.dumps(manifest))
        write_html_report(run, summary)
        page = (run / "report.html").read_text(encoding="utf-8")
        for detail in ("Agent Optimizer", "기준 후보", "검증", "최종 테스트",
                       "fixture-validation", "Optimizer 사용량", "후보 변경 내역"):
            with self.subTest(detail=detail):
                self.assertIn(detail, page)
        self.assertIn("changes.diff", page)
        self.assertIn("sha256:checked", page)
        self.assertNotIn("extensions_sha256", page)
        self.assertNotIn('src="https://', page)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--html"]), 0)
        self.assertEqual(Path(json.loads(output.getvalue())["html"]), run / "report.html")

    def test_real_run_shows_visual_progress_comparison_and_trial_trail_offline(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        run, _ = run_experiment(spec, Registry(), self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn('id="progress-0"', page)
        self.assertIn('class="best-curve"', page)
        self.assertIn('class="trial-point"', page)
        self.assertIn('id="comparison-0"', page)
        self.assertIn('id="timeline-0"', page)
        self.assertIn('id="tasks-0"', page)
        self.assertIn('<title id="progress-title-0">검증 점수 추이</title>', page)
        progress = page.split('id="progress-0"', 1)[1].split('</section>', 1)[0]
        self.assertIn('>1.000</text>', progress)
        self.assertIn('>0.000</text>', progress)
        journey = page.split('<section id="journey">', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('<ol class="lineage">', journey.split('<details', 1)[0])
        self.assertIn('href="#evaluation-0-', page)
        self.assertIn('기준 후보', page)
        self.assertIn('최종 선택', page)
        self.assertIn('첫 후보 평가 이후 1건에서 최고점 갱신 없음', page)
        self.assertIn('실패 상세 2건', page)
        self.assertLess(page.index('id="progress-0"'), page.index('<dl class="meta">'))
        self.assertLess(page.index('id="progress-0"'), page.index('<div class="cards"'))
        self.assertNotIn('<script', page)
        self.assertNotIn('https://cdn', page)

    def test_two_objectives_show_tradeoff_without_claiming_pareto(self):
        run = self.root / "two-objectives"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "mode": "lexicographic", "metrics": [
                {"name": "solve_rate", "direction": "maximize", "source": "passed"},
                {"name": "seconds", "direction": "minimize"}]}}}), encoding="utf-8")
        common = {"agent_id": "agent", "harness_id": "harness", "split": "validation", "valid": True}
        (run / "events.jsonl").write_text("\n".join(json.dumps({
            "event": "candidate_evaluated", **common, "candidate_id": candidate,
            "stage_id": stage, "metrics": {"solve_rate": score, "seconds": seconds}})
            for candidate, stage, score, seconds in (("base", "baseline", 0.3, 12),
                                                      ("long-" + "X" * 240, "search", 0.8, 9),
                                                      ("best", "search", 0.9, 11))) + "\n", encoding="utf-8")
        def row(candidate, score, seconds):
            return {**common, "candidate_id": candidate,
                    "metrics": {"solve_rate": score, "seconds": seconds}}
        summary = {"status": "completed", "groups": [{"agent_id": "agent", "harness_id": "harness",
                   "baseline": row("base", 0.3, 12), "selected": [row("best", 0.9, 11)],
                   "stages": [], "final_test": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn('id="landscape-0"', page)
        self.assertIn('목적 지표 관계', page)
        self.assertIn('우선순위', page)
        self.assertIn('class="landscape-point', page)
        progress = page.split('id="progress-0"', 1)[1].split('</section>', 1)[0]
        self.assertIn('seconds 9.000', progress)
        self.assertIn('search', progress)
        self.assertNotIn('Pareto', page)
        self.assertIn('long-' + 'X' * 240, page)
        english = write_html_report(run, summary, language="en").read_text(encoding="utf-8")
        self.assertIn('id="landscape-0"', english)
        self.assertIn('Objective trade-off', english)
        self.assertNotRegex(english.split('<main>', 1)[1].split('</main>', 1)[0], '[가-힣]')

    def test_empty_and_one_trial_do_not_draw_invented_curve(self):
        run = self.root / "single"
        run.mkdir()
        summary = {"status": "partial", "groups": [{"agent_id": "solo", "harness_id": "fixture",
                   "baseline": None, "selected": [], "final_test": [], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertNotIn('class="best-curve"', page)
        self.assertNotIn('id="landscape-0"', page)
        (run / "events.jsonl").write_text(json.dumps({"event": "trial_completed", "trial_id": "only",
            "agent_id": "solo", "harness_id": "fixture", "candidate_id": "C", "task_id": "t",
            "split": "train", "status": "timeout", "metrics": {"task_wall_time_seconds": 4.0}}) + "\n")
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn('id="timeline-0"', page)
        self.assertIn('4.000', page)
        self.assertNotIn('class="best-curve"', page)

    def test_duplicate_trial_details_link_to_distinct_evidence_rows(self):
        run = self.root / "duplicate-trials"
        run.mkdir()
        common = {"event": "trial_completed", "agent_id": "solo", "harness_id": "fixture",
                  "candidate_id": "base", "task_id": "same", "split": "train", "status": "passed",
                  "metrics": {"passed": 1, "task_wall_time_seconds": 1.0}}
        (run / "events.jsonl").write_text("\n".join(json.dumps({**common, "trial_id": name})
            for name in ("same", "same")) + "\n")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": None, "selected": [], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        timeline = page.split('id="timeline-0"', 1)[1].split('</section>', 1)[0]
        self.assertIn('href="#evaluation-0-0"', timeline)
        self.assertIn('href="#evaluation-0-1"', timeline)

    def test_invalid_huge_aggregate_does_not_break_valid_progress(self):
        run = self.root / "huge-aggregate"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "metrics": [{"name": "score", "direction": "maximize"}]}}}))
        common = {"event": "candidate_evaluated", "agent_id": "solo", "harness_id": "fixture",
                  "split": "validation", "valid": True, "stage_id": "search"}
        (run / "events.jsonl").write_text("\n".join(json.dumps({**common,
            "candidate_id": name, "metrics": {"score": score}})
            for name, score in (("base", 0), ("best", 1), ("overflow", 10 ** 400))) + "\n")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": None, "selected": [], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn('class="best-curve"', page)
        self.assertIn('overflow', page)

    def test_unknown_legacy_objective_direction_is_not_shown_as_minimize(self):
        run = self.root / "unknown-direction"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "metrics": [{"name": "custom", "direction": "sideways"}]}}}))
        page = write_html_report(run, {"groups": []}).read_text(encoding="utf-8")
        glance = page.split('class="quick-config"', 1)[1].split('</div></div>', 1)[0]
        self.assertIn('custom', glance)
        self.assertNotIn('↓ custom', glance)

    def test_unrepresentable_chart_range_omits_curve_without_nonfinite_svg_coordinates(self):
        run = self.root / "extreme-scores"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "metrics": [{"name": "score", "direction": "maximize"}]}}}))
        (run / "events.jsonl").write_text("\n".join(json.dumps({
            "event": "candidate_evaluated", "agent_id": "solo", "harness_id": "fixture",
            "candidate_id": candidate, "split": "validation", "stage_id": "search",
            "valid": True, "metrics": {"score": score}}) for candidate, score in (
                ("minimum", -1e308), ("maximum", 1e308))) + "\n")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": None, "selected": [], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertNotIn('class="best-curve"', page)
        self.assertIn('minimum', page)
        self.assertIn('maximum', page)

    def test_many_candidates_keep_selected_visible_and_fold_the_remaining_trail(self):
        run = self.root / "many-candidates"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "metrics": [{"name": "score", "direction": "maximize"}]}}}))
        common = {"agent_id": "solo", "harness_id": "fixture", "split": "validation", "valid": True}
        (run / "events.jsonl").write_text("\n".join(json.dumps({
            "event": "candidate_evaluated", **common, "candidate_id": f"c{number:03d}",
            "stage_id": "search", "metrics": {"score": number / 10}})
            for number in range(15)) + "\n")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": {**common, "candidate_id": "c000", "metrics": {"score": 0}},
                              "selected": [{**common, "candidate_id": "c008", "metrics": {"score": 0.8}}],
                              "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        progress = page.split('id="progress-0"', 1)[1].split('</section>', 1)[0]
        self.assertIn('나머지 후보 평가', progress)
        self.assertIn('c008</code>', progress.split('<details', 1)[0])
        self.assertEqual(progress.count('class="trial-point'), 15)

    def test_untrusted_feedback_is_escaped_in_incomplete_report(self):
        class FailingEvaluator:
            def __init__(self, config=None):
                pass

            def evaluate(self, task, output_dir, timeout_seconds):
                return Evaluation("failed", {"passed": 0.0}, '<script>alert(1)</script>')

        registry = Registry()
        registry.factories["evaluators"]["text_fixture"] = FailingEvaluator
        self.spec["plugins"]["evaluators"] = {}
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        run, summary = run_experiment(self.spec, registry, self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("평가 기록 없음", page)

    def test_run_failure_still_writes_inspectable_html(self):
        class FailingOptimizer:
            def optimize(self, context, seeds, config):
                raise UnavailableError("model failed")

        registry = Registry()
        registry.factories["optimizers"]["file_variants"] = FailingOptimizer
        with self.assertRaisesRegex(UnavailableError, "model failed"):
            run_experiment(self.spec, registry, self.root / "runs")
        run = next((self.root / "runs").glob("*/summary.json")).parent
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("model failed", page)
        self.assertIn("error", page)

    def test_report_html_rebuilds_legacy_derived_artifacts_without_changing_source_or_csv(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        source = (run / "summary.json").read_bytes()
        csv_path = run / "export.csv"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--csv", str(csv_path)]), 0)
        exported = csv_path.read_bytes()
        (run / "report.json").unlink(missing_ok=True)
        (run / "report.md").write_text("old")
        (run / "report.html").write_text("old")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["report", str(run), "--html"]), 0)

        self.assertEqual(json.loads(output.getvalue()),
                         {"html": str(run / "report.html"), "status": summary["status"]})
        self.assertEqual((run / "summary.json").read_bytes(), source)
        self.assertEqual(csv_path.read_bytes(), exported)
        model = json.loads((run / "report.json").read_text())
        self.assertEqual(model["groups"][0]["selected"], summary["groups"][0]["selected"])
        self.assertNotEqual((run / "report.md").read_text(), "old")
        self.assertNotEqual((run / "report.html").read_text(), "old")

    def test_two_group_run_writes_matching_selected_and_completed_counts(self):
        spec = load_experiment(self.root / "examples/minimal/experiment.toml")
        run, summary = run_experiment(spec, Registry(), self.root / "runs")
        model = json.loads((run / "report.json").read_text())
        markdown = (run / "report.md").read_text()
        html = (run / "report.html").read_text()
        self.assertEqual(len(model["groups"]), 2)
        self.assertEqual([g["selected"] for g in model["groups"]],
                         [g["selected"] for g in summary["groups"]])
        for group in model["groups"]:
            self.assertGreater(group["counts"]["completed_evaluations"], 0)
            for content in (markdown, html):
                self.assertIn(group["agent_id"], content)
            self.assertIn(f'{group["counts"]["completed_evaluations"]} 완료', markdown)
            self.assertIn(f'완료 {group["counts"]["completed_evaluations"]}건', html)
            self.assertIn(group["comparison_trend"], markdown)
            self.assertIn({"improved": "개선", "unchanged": "변화 없음"}[group["comparison_trend"]], html)

        self.assertIn("multi-agent-demo", html)
        self.assertIn("examples/minimal/tasks.json", html)
        self.assertIn("높을수록 좋음", html)
        self.assertIn("max_trials", html)
        self.assertIn("합성 예제", html)
        self.assertIn('scope="col"', html)
        self.assertIn("<caption", html)
        self.assertNotIn('src="https://', html)
        self.assertIn('완료된 평가 7건', html)
        self.assertEqual(model["counts"]["completed_evaluations"], 7)
        self.assertEqual(model["identity"]["run_wall_time_seconds"],
                         summary["run_wall_time_seconds"])
        self.assertIn('실측 실행 시간', html)
        self.assertEqual(len(re.findall(r'<tr[^>]+id="evaluation-', html)), 7)
        self.assertIn('href="rtl-solo/fixture/candidates/c0002/changes.diff"', html)
        self.assertIn('href="rtl-team/fixture/candidates/c0001/changes.diff"', html)
        self.assertIn('href="rtl-solo/fixture/candidates/c0002/bundle/"', html)
        self.assertIn('href="rtl-team/fixture/candidates/c0001/bundle/"', html)
        self.assertIn('집계 · 1 건의 평가</span>', html)
        self.assertNotIn('집계 · 1.000 건의 평가</span>', html)
        self.assertIn("+1.000", html)  # solo 0 -> 1; team 1 -> 1
        self.assertIn("+0.000", html)
        self.assertIn('id="held-out-test"', html)
        self.assertIn("변경 사항 미리보기", html)

    def test_long_untrusted_feedback_keeps_full_text_in_details(self):
        class FailingEvaluator:
            def __init__(self, config=None):
                pass

            def evaluate(self, task, output_dir, timeout_seconds):
                return Evaluation("failed", {"passed": 0.0}, "A" * 5001 + "<script>tail</script>")

        registry = Registry()
        registry.factories["evaluators"]["text_fixture"] = FailingEvaluator
        self.spec["plugins"]["evaluators"] = {}
        self.spec.update(stages=[], final_stages=["baseline"], final_test=False)
        run, _ = run_experiment(self.spec, registry, self.root / "runs")
        page = (run / "report.html").read_text(encoding="utf-8")
        self.assertIn("A" * 5001 + "&lt;script&gt;tail&lt;/script&gt;", page)
        self.assertNotIn("<script>tail</script>", page)
        self.assertIn("<details", page)

    def test_explicit_infrastructure_failure_and_unknown_optimizer_have_evaluation_fallback(self):
        run = self.root / "recorded"
        run.mkdir()
        summary = {"run_id": "recorded", "status": "partial", "trials_used": 2, "groups": [
            {"agent_id": "solo", "harness_id": "fixture-harness", "baseline": None,
             "selected": [], "final_test": [], "stages": [{"id": "opaque", "optimizer": "unknown-plugin",
                                                   "checkpoint": {"internal": [1, 2]}}]}]}
        (run / "events.jsonl").write_text(json.dumps({
            "event": "trial_completed", "trial_id": "infra-1", "agent_id": "solo",
            "harness_id": "fixture-harness", "candidate_id": "c0001", "task_id": "unit-1",
            "split": "train", "status": "infrastructure_error", "feedback": "timeout text only",
            "execution": {"status": "infrastructure_error", "detail": "worker unavailable"},
        }) + "\n", encoding="utf-8")
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn("unknown-plugin", page)
        self.assertIn("기록된 탐색 구조가 없습니다", page)
        self.assertIn('id="evaluations"', page)
        self.assertIn("infra-1", page)
        self.assertIn("실행 환경 오류", page)
        self.assertIn("worker unavailable", page)
        self.assertNotIn("category: timeout", page)
        self.assertIn('scope="row"', page)

    def test_unknown_optimizer_without_evaluations_keeps_group_event_order_and_raw_evidence(self):
        run = self.root / "event-only"
        run.mkdir()
        summary = {"status": "partial", "groups": [
            {"agent_id": "solo", "harness_id": "fixture", "baseline": None,
             "selected": [], "final_test": [], "stages": [
                 {"id": "opaque", "optimizer": "custom-unknown", "checkpoint": {}}]}]}
        events = [
            {"event": "optimizer_probe_started", "agent_id": "solo", "harness_id": "fixture",
             "stage_id": "opaque", "phase": "probe", "timestamp": "2026-09-25T00:00:02Z",
             "private_note": "<script>secret-trace</script>"},
            {"event": "optimizer_probe_completed", "agent_id": "other", "harness_id": "fixture",
             "stage_id": "opaque", "detail": "other-group-only"},
            {"event": "optimizer_probe_completed", "agent_id": "solo", "harness_id": "fixture",
             "stage_id": "opaque", "status": "interrupted", "timestamp": "2026-09-25T00:00:03Z",
             "detail": "raw outcome"},
        ]
        (run / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

        page = write_html_report(run, summary).read_text(encoding="utf-8")
        journey = page.split('<section id="journey">', 1)[1].split('</section>', 1)[0]
        self.assertIn('optimizer_probe_started', journey)
        self.assertIn('optimizer_probe_completed', journey)
        self.assertLess(journey.index('optimizer_probe_started'),
                        journey.index('optimizer_probe_completed'))
        self.assertIn('2026-09-25T00:00:02Z', journey)
        self.assertIn('opaque', journey)
        self.assertIn('interrupted', journey)
        self.assertIn('<details', journey)
        self.assertIn('&lt;script&gt;secret-trace&lt;/script&gt;', journey)
        self.assertNotIn('<script>secret-trace</script>', page)
        self.assertNotIn('secret-trace', journey.split('<details', 1)[0])
        self.assertNotIn('other-group-only', page)
        self.assertIn('평가 기록 없음', page)

    def test_long_unbroken_experiment_name_is_wrappable_without_truncation(self):
        run = self.root / "long-name"
        run.mkdir()
        name = "X" * 2048
        (run / "manifest.json").write_text(json.dumps({"experiment": {"name": name}}),
                                            encoding="utf-8")

        page = write_html_report(run, {"status": "completed", "groups": []}).read_text(encoding="utf-8")
        self.assertIn(f'<h1>{name}</h1>', page)
        self.assertRegex(page, r'h1\{[^}]*overflow-wrap:anywhere')

    def test_selected_candidate_long_changed_path_uses_wrappable_code(self):
        run, summary = run_experiment(self.spec, Registry(), self.root / "runs")
        model = json.loads((run / "report.json").read_text())
        long_path = "configs/" + "nested" * 350
        selected_id = model["groups"][0]["selected"][0]["candidate_id"]
        candidate = next(item for item in model["groups"][0]["candidates"]
                         if item["candidate_id"] == selected_id)
        candidate["changed_files"] = [long_path]

        page = write_html_report(run, summary, model).read_text(encoding="utf-8")
        self.assertIn(f'변경 파일: <code>{long_path}</code>', page)
        self.assertRegex(page, r'code,pre\{[^}]*overflow-wrap:anywhere')

    def test_untrusted_candidate_paths_are_not_links_and_large_durations_are_not_summed(self):
        run = self.root / "unsafe"
        run.mkdir()
        (run / "outside.diff").write_text("secret")
        summary = {"run_id": "unsafe", "status": "completed", "groups": [
            {"agent_id": "solo", "harness_id": "fixture-harness", "baseline": None,
             "selected": [{"candidate_id": "../../outside", "split": "validation"}],
             "final_test": [], "stages": []}]}
        (run / "events.jsonl").write_text("\n".join(json.dumps({
            "event": "trial_completed", "trial_id": f"large-{number}", "agent_id": "solo",
            "harness_id": "fixture-harness", "candidate_id": "../../outside", "status": "passed",
            "metrics": {"task_wall_time_seconds": 10 ** 400},
        }) for number in range(2)) + "\n", encoding="utf-8")
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertNotIn('href="../', page)
        self.assertNotIn("과제 시간 합계", page)
        self.assertNotIn("infs", page)
        self.assertIn("완료 2건", page)

    def test_invalid_or_nonvalidation_selection_is_recorded_without_winner_claim(self):
        run = self.root / "invalid-selection"
        run.mkdir()
        rows = [
            {"candidate_id": "bad-test", "agent_id": "solo", "harness_id": "fixture",
             "split": "test", "valid": True, "metrics": {"score": 1}},
            {"candidate_id": "bad-validation", "agent_id": "solo", "harness_id": "fixture",
             "split": "validation", "valid": False, "metrics": {"score": None}},
            {"candidate_id": "other-group", "agent_id": "other", "harness_id": "fixture",
             "split": "validation", "valid": True, "metrics": {"score": 2}},
            {"candidate_id": "partial", "agent_id": "solo", "harness_id": "fixture",
             "split": "validation", "valid": True, "partial": True, "metrics": {"score": 3}},
        ]
        summary = {"status": "partial", "groups": [{"agent_id": "solo", "harness_id": "fixture",
                                                 "baseline": None, "selected": rows,
                                                 "final_test": [], "stages": []}]}

        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn("bad-test", page)
        self.assertIn("bad-validation", page)
        self.assertIn("other-group", page)
        self.assertIn("partial", page)
        self.assertIn("기록된 선택", page)
        self.assertNotIn("검증에서 선택된 후보:", page)
        self.assertNotIn("검증에서 선택 ·", page)

    def test_partial_selection_with_parent_is_not_a_visual_winner(self):
        run = self.root / "partial-parent"
        for identifier, parents in (("base", []), ("partial", ["base"])):
            folder = run / "solo" / "fixture" / "candidates" / identifier
            folder.mkdir(parents=True)
            (folder / "candidate.json").write_text(json.dumps({"id": identifier, "parents": parents}))
        row = {"candidate_id": "partial", "agent_id": "solo", "harness_id": "fixture",
               "split": "validation", "valid": True, "partial": True, "metrics": {"score": 1}}
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": None, "selected": [row], "stages": []}]}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertNotIn('id="trail-0"', page)

    def test_small_minimize_delta_keeps_sign_and_distinguishable_scores(self):
        run = self.root / "small-score"
        run.mkdir()
        (run / "manifest.json").write_text(json.dumps({"experiment": {"objective": {
            "metrics": [{"name": "latency", "direction": "minimize"}]}}}), encoding="utf-8")
        def row(candidate, score):
            return {"candidate_id": candidate, "agent_id": "solo", "harness_id": "fixture",
                    "split": "validation", "valid": True, "metrics": {"latency": score}}
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": row("base", 0.0004),
                              "selected": [row("chosen", 0.0003)], "final_test": [], "stages": []}]}

        page = write_html_report(run, summary).read_text(encoding="utf-8")
        comparison = page.split('<section class="group"', 1)[1].split('</section>', 1)[0]
        self.assertIn("0.0004", comparison)
        self.assertIn("0.0003", comparison)
        self.assertIn("-0.0001", comparison)
        self.assertNotIn("-0.000</td>", comparison)

    def test_unselected_candidates_offer_escaped_changes_and_evaluation_anchors(self):
        run = self.root / "candidate-evidence"
        run.mkdir()
        root = run / "solo" / "fixture" / "candidates"
        for identifier in ("chosen", "rejected", "unevaluated"):
            directory = root / identifier
            directory.mkdir(parents=True)
            (directory / "candidate.json").write_text(json.dumps({
                "id": identifier, "parents": ["chosen"], "producer": "search",
                "changed_files": ["danger<file>.txt"]}), encoding="utf-8")
            (directory / "changes.diff").write_text("+<script>bad</script>", encoding="utf-8")
        (run / "events.jsonl").write_text(json.dumps({
            "event": "trial_completed", "agent_id": "solo", "harness_id": "fixture",
            "trial_id": "rejected-trial", "candidate_id": "rejected", "stage_id": "search",
            "split": "train", "status": "failed"}) + "\n", encoding="utf-8")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture",
                              "baseline": None, "selected": [{"candidate_id": "chosen",
                              "agent_id": "solo", "harness_id": "fixture", "split": "validation",
                              "valid": True}], "final_test": [], "stages": []}]}

        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn('<details><summary>기록된 후보 · rejected</summary>', page)
        self.assertIn('href="solo/fixture/candidates/rejected/changes.diff"', page)
        self.assertIn('href="#evaluation-0-0"', page)
        self.assertIn('id="evaluation-0-0"', page)
        self.assertIn("unevaluated", page)
        self.assertIn("평가 기록 없음", page)
        self.assertIn("danger&lt;file&gt;.txt", page)
        self.assertIn("+&lt;script&gt;bad&lt;/script&gt;", page)
        self.assertNotIn("+<script>bad</script>", page)

    def test_structured_journey_keeps_additional_optimizer_events_as_raw_evidence(self):
        run = self.root / "structured-events"
        run.mkdir()
        events = [
            {"event": "report_unit", "agent_id": "solo", "harness_id": "fixture",
             "stage_id": "search", "unit_id": "g0", "unit_type": "generation",
             "candidate_ids": ["A"]},
            {"event": "optimizer_probe_completed", "agent_id": "solo", "harness_id": "fixture",
             "stage_id": "search", "detail": "<unsafe>opaque</unsafe>"},
        ]
        (run / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n", encoding="utf-8")
        summary = {"groups": [{"agent_id": "solo", "harness_id": "fixture", "selected": [],
                              "final_test": [], "stages": []}]}

        page = write_html_report(run, summary).read_text(encoding="utf-8")
        journey = page.split('<section id="journey">', 1)[1].split('</section>', 1)[0]
        self.assertIn('id="units-0"', page)
        self.assertIn("g0", journey)
        self.assertIn("optimizer_probe_completed", journey)
        self.assertIn("&lt;unsafe&gt;opaque&lt;/unsafe&gt;", journey)
        self.assertIn("이벤트 원본", journey)
        self.assertNotIn("<unsafe>", page)

    def test_compact_budget_and_measured_wall_time_leave_full_config_in_details(self):
        run = self.root / "budget"
        run.mkdir()
        budget = {"max_trials": 40, "max_wall_time_seconds": 120,
                  "trial_timeout_seconds": 10, "extra_limit": "kept"}
        (run / "manifest.json").write_text(json.dumps({"experiment": {
            "budget": budget}}), encoding="utf-8")
        summary = {"status": "completed", "run_wall_time_seconds": 2.125, "groups": []}
        page = write_html_report(run, summary).read_text(encoding="utf-8")
        self.assertIn("40회 · 120초 총 실행 제한 · 10초/평가", page)
        self.assertIn("실측 실행 시간", page)
        self.assertIn("2.125", page)
        self.assertIn('&quot;extra_limit&quot;', page)
        self.assertNotIn('{&quot;max_trials&quot;: 40', page)
        page = write_html_report(run, {"status": "completed", "groups": []}).read_text(encoding="utf-8")
        self.assertNotIn("실측 실행 시간", page)

    def test_large_legacy_budget_integer_does_not_prevent_report_generation(self):
        run = self.root / "large-budget"
        run.mkdir()
        huge = 10 ** 400
        (run / "manifest.json").write_text(json.dumps({"experiment": {
            "budget": {"max_trials": huge}}}), encoding="utf-8")
        page = write_html_report(run, {"groups": []}).read_text(encoding="utf-8")
        self.assertIn(f'{huge}회', page)
        self.assertIn('실험 설정 원본', page)


if __name__ == "__main__":
    unittest.main()
