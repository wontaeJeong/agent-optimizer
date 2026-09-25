"""Inline CSS shared by the standalone run report and dataset index."""

STYLE = """
:root{color-scheme:light;--bg:#f8f9fa;--surface:#fff;--text:#20252d;--muted:#56606d;
--border:#dce1e6;--accent:#155d70;--good:#176145;--bad:#ad3545;--warn:#745317;
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#10141a;--surface:#171d24;
--text:#e9edf2;--muted:#afb8c4;--border:#37424e;--accent:#85c9d6;--good:#8ee0b6;
--bad:#ffa7ae;--warn:#e8c785}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text)}
header,main,footer{max-width:1360px;margin:auto;padding:1.5rem 2rem}header{padding-top:2.4rem}
h1{font-size:clamp(1.9rem,3vw,2.8rem);line-height:1.2;letter-spacing:-.035em;margin:.35rem 0;overflow-wrap:anywhere}
h2{font-size:1.45rem;letter-spacing:-.025em;margin:0 0 .7rem}h3{font-size:1.07rem;margin:1.2rem 0 .45rem}
p{margin:.5rem 0}.eyebrow{font-size:.73rem;letter-spacing:.12em;text-transform:uppercase;
font-weight:750;color:var(--accent)}.lede,.subtle,.tag{color:var(--muted)}.subtle,.tag{font-size:.88rem}
.mono,code,pre,.number{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
code,pre{font-size:.85rem;overflow-wrap:anywhere;word-break:break-word}pre{white-space:pre-wrap;margin:.6rem 0;max-height:28rem;overflow:auto}
a{color:var(--accent);text-underline-offset:.18em}a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px;border-radius:2px}
abbr.help{position:relative;text-decoration:underline dotted;text-underline-offset:.2em;cursor:help}
.help:focus-visible::after{content:attr(title);position:absolute;top:calc(100% + .4rem);left:0;
z-index:10;width:min(18rem,75vw);padding:.5rem .7rem;border:1px solid var(--border);
border-radius:4px;background:var(--surface);color:var(--text);font:normal .85rem/1.5 system-ui,sans-serif;
text-align:left;text-transform:none;letter-spacing:normal;white-space:normal;box-shadow:0 3px 12px #0003}
nav{display:flex;flex-wrap:wrap;gap:.35rem 1.1rem;margin:1.5rem 0 0;font-size:.9rem}
.pill{display:inline-block;border:1px solid var(--border);border-radius:4px;padding:.18rem .6rem;
margin:.5rem .4rem 0 0;font-weight:650;font-size:.85rem}
.warning{color:var(--warn)}.bad{color:var(--bad)}.good{color:var(--good)}
.meta,.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:.7rem 1.4rem}
.meta{padding:1rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:1.25rem 0 0}
.meta div{min-width:0}.meta dt{color:var(--muted);font-size:.76rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.meta dd{margin:.22rem 0 0;overflow-wrap:anywhere}.cards{margin:1rem 0 2rem}
.card,.panel{border:1px solid var(--border);border-radius:7px;background:var(--surface)}
.best{border-left:3px solid var(--good)}.best>strong{color:var(--good)}
.card{padding:.85rem 1rem}.card strong{display:block;font-size:1.5rem;line-height:1.35}.card span{color:var(--muted);font-size:.84rem}
.panel{padding:1rem;margin:.85rem 0}.panel>:first-child{margin-top:0}
section{margin:2.6rem 0}section.group{border-top:2px solid var(--border);padding-top:1.2rem}
.group-heading{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1rem}.group-heading h2{margin:0}
.table-scroll{max-width:100%;overflow-x:auto;border:1px solid var(--border);border-radius:6px;margin:.75rem 0 1.2rem}
table{width:100%;border-collapse:collapse;text-align:left;font-size:.9rem}
caption{text-align:left;font-weight:700;padding:.7rem .8rem;color:var(--text);background:var(--surface)}
th,td{padding:.55rem .75rem;border-top:1px solid var(--border);vertical-align:top;overflow-wrap:anywhere}
thead th{color:var(--muted);font-size:.77rem;letter-spacing:.05em;background:var(--surface)}
tbody tr:hover{background:color-mix(in srgb,var(--accent) 5%,transparent)}
th[scope=row]{font-weight:600}.number{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.table-scroll td:not(.number){min-width:7rem}.table-scroll td.evidence{min-width:16rem;max-width:35rem}
.row-failed{border-left:3px solid var(--bad)}
details{border-top:1px solid var(--border);margin:.75rem 0 0;padding:.55rem 0 0}
summary{cursor:pointer;color:var(--accent);font-weight:600}details[open] summary{margin-bottom:.6rem}
.feedback{max-width:34rem}.feedback pre{overflow-wrap:anywhere}.measure{font-variant-numeric:tabular-nums}
.lineage{padding-left:1.5rem}.lineage li{margin:.4rem 0;overflow-wrap:anywhere}
.quick-config{display:grid;grid-template-columns:1fr 1.2fr 1fr;gap:.6rem 2rem;
border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:.85rem 0;margin:1.15rem 0 0}
.quick-config>div{min-width:0;overflow-wrap:anywhere}.quick-config .eyebrow{display:block;font-size:.65rem}
.quick-config strong{display:block;font-weight:600;font-size:.9rem;margin-top:.15rem}
.quick-config ol{display:flex;flex-wrap:wrap;list-style:none;padding:0;margin:.15rem 0 0;
gap:.15rem .85rem;font-size:.9rem;font-weight:600}
.summary-section{margin:1.6rem 0 1rem}.summary-section h2{font-size:1.9rem;margin:.25rem 0}
.headlines{border-top:1px solid var(--border);border-bottom:1px solid var(--border);
display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));margin:1rem 0 0}
.headline-group{min-width:0;padding:1.1rem 1.3rem 1.1rem 0;display:grid;align-content:start;gap:.15rem;
border-right:1px solid var(--border);overflow-wrap:anywhere}
.headline-group:last-child{border-right:0}.headline-group strong{font-size:clamp(1.7rem,3vw,2.5rem);
line-height:1.18;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.headline-group strong small{font-size:.43em;letter-spacing:0;color:var(--muted)}
.headline-group>a{font-size:.83rem;margin-top:.5rem}
.summary-facts{color:var(--muted);font-size:.83rem;margin:.65rem 0 0;
font-variant-numeric:tabular-nums}
section.group{margin:1.3rem 0 3rem;padding-top:.9rem}
.group-heading .pill{margin:0}
.cards{grid-template-columns:repeat(auto-fit,minmax(min(100%,145px),1fr));gap:0;
border-bottom:1px solid var(--border);margin:.5rem 0 2rem}
.cards .card{border:0;border-radius:0;background:transparent;padding:.4rem .7rem .8rem 0}
.cards .card strong{font-size:1.17rem}
.visual-section{margin:1.8rem 0 2rem;padding-top:1.1rem;border-top:1px solid var(--border)}
.visual-section h3{font-size:1.25rem;margin:.1rem 0 .4rem;letter-spacing:-.025em}
.section-heading .eyebrow{font-size:.67rem}.chart{display:block;width:100%;height:auto;max-height:270px;
margin:.9rem 0 0;overflow:visible}
.chart-grid{fill:none;stroke:var(--border);stroke-width:1}.baseline-line{stroke:var(--muted);
stroke-width:1.3;stroke-dasharray:6 5}.best-curve{fill:none;stroke:var(--accent);
stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.stage-boundary{stroke:var(--border);stroke-width:1.5;stroke-dasharray:2 4}
.trial-point{fill:var(--surface);stroke:var(--accent);stroke-width:2.5}
.chosen-point{fill:var(--accent);stroke:var(--text);stroke-width:2.5}
.axis-label{fill:var(--muted);font:12px ui-monospace,SFMono-Regular,Consolas,monospace}
.legend{display:flex;gap:.5rem 1.4rem;flex-wrap:wrap;color:var(--muted);font-size:.8rem}
.legend span{display:inline-flex;align-items:center;gap:.4rem}.legend i{display:inline-block;width:15px;
height:10px;border-bottom:2px solid var(--accent)}.legend .legend-dot{width:9px;height:9px;
border:2px solid var(--accent);border-radius:50%}.legend .legend-dash{border-bottom:2px dashed var(--muted)}
.legend .legend-ring{width:11px;height:11px;border-radius:50%;border:3px solid var(--accent)}
.insight{border-left:2px solid var(--accent);padding:.45rem .8rem;margin:1rem 0;
background:color-mix(in srgb,var(--accent) 6%,var(--surface));font-weight:600}
.progress-list{padding:0;margin:.6rem 0;list-style:none;display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:0 1rem}
.progress-item{display:flex;align-items:baseline;gap:.4rem;padding:.4rem 0;border-bottom:1px solid var(--border);
min-width:0;flex-wrap:wrap;font-size:.86rem}.progress-item code,.trail-node code{min-width:0;overflow-wrap:anywhere}
.trail-index{font:700 .78rem ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted)}
.trail-score{margin-left:auto;font-variant-numeric:tabular-nums}.trail-state{font-size:.8rem;color:var(--muted)}
.metric-comparison{margin:1rem 0 1.4rem;max-width:850px}
.metric-heading{display:flex;align-items:baseline;flex-wrap:wrap;gap:.15rem 1.2rem;border-bottom:1px solid var(--border);
padding-bottom:.35rem}.metric-heading>strong{font-size:1.05rem}.metric-heading>span{color:var(--muted);font-size:.85rem}
.metric-heading>b{margin-left:auto;font-variant-numeric:tabular-nums}
.comparison-bars{display:grid;grid-template-columns:6.5rem minmax(0,1fr) 6rem;
align-items:center;gap:.3rem .65rem;font-size:.8rem;padding:.5rem 0}
.comparison-bars strong{text-align:right;font-variant-numeric:tabular-nums}
.bar-track{display:block;width:100%;height:.65rem;background:var(--border);overflow:hidden}
.bar{display:block;height:100%;background:var(--muted)}.selected-bar{background:var(--accent)}
.landscape-point{fill:var(--surface);stroke:var(--accent);stroke-width:2.5}
.landscape-point.baseline{stroke:var(--muted)}.landscape-point.selected{fill:var(--accent);stroke:var(--text)}
.unit-flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,215px),1fr));
gap:.5rem;list-style:none;padding:0;margin:.85rem 0}
.unit{position:relative;min-width:0;padding:.65rem .8rem;border-left:2px solid var(--accent);
background:var(--surface);overflow-wrap:anywhere}
.unit strong{display:block;font-size:.95rem}.unit-members{color:var(--muted);font-size:.79rem}
.unit-members code{color:var(--text)}
.trail-path{display:flex;flex-wrap:wrap;list-style:none;padding:0;gap:.6rem;margin:.8rem 0}
.trail-node{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;min-width:0;padding:.5rem .7rem;
border-left:2px solid var(--accent);background:var(--surface)}
.trail-node:not(:last-child)::after{content:'→';color:var(--muted);margin-left:.5rem}
.trail-node>span:last-child{color:var(--muted);font-size:.8rem}
.task-matrix td{min-width:0!important}.task-state{display:inline-block;padding:.1rem .55rem;
border:1px solid var(--border);font-size:.83rem;white-space:nowrap}
.task-state.passed{color:var(--good);border-color:var(--good)}
.task-state.failed{color:var(--bad);border-color:var(--bad)}
.timeline{list-style:none;padding:0;margin:.7rem 0}.timeline-row{display:grid;
grid-template-columns:minmax(10rem,1.7fr) minmax(3rem,1fr) 5rem minmax(5rem,.55fr);
align-items:center;gap:.45rem .8rem;min-width:0;padding:.4rem 0;border-bottom:1px solid var(--border)}
.timeline-id{min-width:0}.timeline-id code{display:block;overflow-wrap:anywhere}
.timeline-id small{display:block;color:var(--muted);overflow-wrap:anywhere}
.duration-track{display:block;width:100%;height:.8rem;background:var(--border)}
.duration-fill{display:block;height:100%;background:var(--accent)}
.duration-value{font-size:.82rem;text-align:right;font-variant-numeric:tabular-nums}
.outcome{text-align:right;font-size:.82rem;overflow-wrap:anywhere}.outcome.passed{color:var(--good)}
.outcome.timeout,.outcome.infrastructure,.outcome.execution,.outcome.scored_failure{color:var(--bad)}
.outcome-bars{padding:0;list-style:none;max-width:700px}.outcome-bars li{display:grid;
grid-template-columns:minmax(8rem,1.5fr) minmax(4rem,3fr) 2rem;gap:1rem;align-items:center;
margin:.45rem 0;font-variant-numeric:tabular-nums}
.failure-summary{display:flex;flex-wrap:wrap;gap:.5rem 1.4rem;padding:0;list-style:none}
.failure-summary li{border-left:2px solid var(--bad);padding:0 .65rem;font-size:.86rem}
footer{border-top:1px solid var(--border);color:var(--muted);font-size:.85rem;padding-bottom:3rem}
@media(max-width:768px){header,main,footer{padding:1.1rem}header{padding-top:1.5rem}
.meta,.cards{grid-template-columns:repeat(auto-fit,minmax(min(100%,165px),1fr))}
.panel{padding:.8rem}section{margin:2rem 0}th,td{padding:.5rem}
.chart{min-height:130px}.timeline-row{grid-template-columns:minmax(7rem,2fr) minmax(3rem,1fr) 4rem;
gap:.3rem}.timeline-row .outcome{grid-column:1/-1;text-align:left}.headlines{grid-template-columns:1fr}
.headline-group{border-right:0;border-bottom:1px solid var(--border)}}
@media(max-width:650px){.quick-config{grid-template-columns:1fr 1fr}.quick-config>div:last-child{grid-column:1/-1}}
@media print{ :root{color-scheme:light;--bg:#fff;--surface:#fff;--text:#151a20;
--muted:#47515e;--border:#aab2ba;--accent:#155d70;--good:#12573d;--bad:#922536}
body{background:#fff}nav,footer,#evaluations{display:none}details:not([open]){display:none}
.visual-section,.metric-comparison{break-inside:avoid}.chart{max-height:240px}
.bar,.duration-fill,.task-state,.insight{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
"""
