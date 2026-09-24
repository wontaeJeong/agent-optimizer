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
footer{border-top:1px solid var(--border);color:var(--muted);font-size:.85rem;padding-bottom:3rem}
@media(max-width:768px){header,main,footer{padding:1.1rem}header{padding-top:1.5rem}
.meta,.cards{grid-template-columns:repeat(auto-fit,minmax(min(100%,165px),1fr))}
.panel{padding:.8rem}section{margin:2rem 0}th,td{padding:.5rem}}
"""
