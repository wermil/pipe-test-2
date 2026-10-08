#!/usr/bin/env python3
"""Генерує сторінку плану задачі для публікації артефактом (mobile first, світла й темна теми).

Запуск: python3 .claude/pipeline/plan_artifact.py /tmp/pipeline-plan/<ID>.json
Вхід і вихід — лише в /tmp/pipeline-plan. Результат: /tmp/pipeline-plan/<ID>.html і sha плану.

Формат JSON:
{
  "task_id": "SBX-26", "title": "…", "repo": "owner/name", "summary": "1–3 речення",
  "flows": [{"name": "Виконання", "nodes": [
      {"label": "Користувач", "kind": "external"},
      {"label": "scripts/greet.sh", "kind": "modified", "note": "…", "edge": "підпис стрілки до наступного вузла"}, …]}],
  "steps":   [{"title": "…", "detail": "…"}],
  "files":   [{"path": "scripts/lib/daypart.sh", "change": "new|modified|deleted", "why": "…"}],
  "tests":   [{"name": "tests/greet_test.sh", "checks": ["…"]}],
  "risks":   [{"text": "…", "mitigation": "…"}],
  "out_of_scope": ["…"]
}
kind вузла: new | modified | existing | external. Поля branch і session_url заповнюються самі, якщо їх немає.
"""
import datetime, hashlib, html, json, os, re, subprocess, sys

PLAN_DIR = "/tmp/pipeline-plan"
KINDS = {"new": "новий", "modified": "змінюється", "existing": "без змін", "external": "зовнішнє"}
CHANGES = {"new": "новий", "modified": "змінюється", "deleted": "видаляється"}
LIMITS = {"flows": 4, "nodes": 10, "steps": 15, "files": 30, "tests": 10, "checks": 12, "risks": 10, "out_of_scope": 10}


def fail(msg):
    print("PLAN ARTIFACT: помилка: " + msg, file=sys.stderr)
    sys.exit(1)


def inside_plan_dir(path):
    if os.path.islink(PLAN_DIR):
        return False
    real = os.path.realpath(path)
    return real.startswith(os.path.realpath(PLAN_DIR) + os.sep)


def txt(value, limit=600):
    value = "" if value is None else str(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def esc(value, limit=600):
    return html.escape(txt(value, limit), quote=True)


def code_or_text(value, limit=200):
    """Шляхи й команди — моноширинним шрифтом."""
    t = txt(value, limit)
    if re.search(r"[/._]", t) and " " not in t:
        return f'<code>{html.escape(t)}</code>'
    return html.escape(t)


def session_url():
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if re.fullmatch(r"(cse|session)_[A-Za-z0-9]+", sid):
        return "https://claude.ai/code/session_" + sid.split("_", 1)[1]
    return ""


def git_branch():
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def validate(p):
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}-\d{1,6}", txt(p.get("task_id"), 20)):
        fail("task_id має бути на зразок SBX-26")
    for key in ("title", "summary"):
        if not txt(p.get(key)):
            fail(f"порожнє поле {key}")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", txt(p.get("repo"), 120)):
        fail("repo має бути owner/name")
    flows = p.get("flows") or []
    if not isinstance(flows, list) or not flows:
        fail("потрібна хоча б одна лінія схеми у flows")
    for f in flows[:LIMITS["flows"]]:
        nodes = f.get("nodes") or []
        if len(nodes) < 2:
            fail(f"лінія «{txt(f.get('name'), 60)}» має мати щонайменше 2 вузли")
        for n in nodes:
            if n.get("kind", "existing") not in KINDS:
                fail(f"невідомий kind «{txt(n.get('kind'), 20)}»")
    if not p.get("steps"):
        fail("потрібен хоча б один крок у steps")
    if not p.get("files"):
        fail("потрібен хоча б один файл у files")
    for f in p.get("files", []):
        if f.get("change", "modified") not in CHANGES:
            fail(f"невідомий change «{txt(f.get('change'), 20)}»")
    url = txt(p.get("session_url"), 200)
    if url and not re.fullmatch(r"https://claude\.ai/code/session_[A-Za-z0-9]+", url):
        fail("session_url має бути https://claude.ai/code/session_…")


ARROW = ('<svg class="arrow" viewBox="0 0 12 30" aria-hidden="true" focusable="false">'
         '<line x1="6" y1="1" x2="6" y2="26" stroke="currentColor" stroke-width="1.6"/>'
         '<path d="M1.5 21.5 L6 28 L10.5 21.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>')


def render_flow(flow):
    nodes = (flow.get("nodes") or [])[:LIMITS["nodes"]]
    parts = []
    for i, n in enumerate(nodes):
        kind = n.get("kind", "existing")
        note = f'<p class="node-note">{esc(n.get("note"), 240)}</p>' if txt(n.get("note")) else ""
        parts.append(
            f'<li class="node k-{kind}"><span class="chip c-{kind}">{KINDS[kind]}</span>'
            f'<span class="node-label">{code_or_text(n.get("label"), 120)}</span>{note}</li>')
        if i < len(nodes) - 1:
            edge = txt(n.get("edge"), 120)
            label = f'<span class="edge-label">{html.escape(edge)}</span>' if edge else ""
            parts.append(f'<li class="edge" aria-hidden="{"false" if edge else "true"}">{ARROW}{label}</li>')
    names = " → ".join(txt(n.get("label"), 60) for n in nodes)
    return (f'<figure class="lane"><figcaption class="lane-name">{esc(flow.get("name") or "Потік", 80)}</figcaption>'
            f'<ol class="flow" role="list" aria-label="{html.escape(names, quote=True)}">{"".join(parts)}</ol></figure>')


def render(p, sha, generated):
    tid, title, repo = esc(p["task_id"], 20), esc(p["title"], 160), esc(p["repo"], 120)
    branch = esc(p.get("branch") or "—", 120)
    surl = txt(p.get("session_url"), 200)
    session_cell = f'<a href="{html.escape(surl, quote=True)}">Відкрити сесію</a>' if surl else "—"
    approve_btn = (f'<a class="btn" href="{html.escape(surl, quote=True)}">Відкрити сесію для погодження</a>' if surl else "")

    flows = "".join(render_flow(f) for f in p["flows"][:LIMITS["flows"]])
    steps = "".join(
        f'<li class="step"><span class="step-n">{i}</span><div class="step-body"><p class="step-title">{esc(s.get("title"), 160)}</p>'
        + (f'<p class="step-detail">{esc(s.get("detail"), 500)}</p>' if txt(s.get("detail")) else "") + "</div></li>"
        for i, s in enumerate(p["steps"][:LIMITS["steps"]], 1))
    files = "".join(
        f'<li class="file"><span class="chip c-{ "new" if f.get("change") == "new" else ("deleted" if f.get("change") == "deleted" else "modified") }">'
        f'{CHANGES.get(f.get("change", "modified"), "змінюється")}</span><code class="path">{esc(f.get("path"), 200)}</code>'
        + (f'<p class="file-why">{esc(f.get("why"), 300)}</p>' if txt(f.get("why")) else "") + "</li>"
        for f in p["files"][:LIMITS["files"]])
    tests = "".join(
        f'<li class="test"><code class="path">{esc(t.get("name"), 200)}</code><ul class="checks">'
        + "".join(f"<li>{esc(c, 200)}</li>" for c in (t.get("checks") or [])[:LIMITS["checks"]]) + "</ul></li>"
        for t in (p.get("tests") or [])[:LIMITS["tests"]])
    risks = "".join(
        f'<li class="risk"><p class="risk-text">{esc(r.get("text"), 300)}</p>'
        + (f'<p class="risk-fix"><span class="label">Як знижуємо</span> {esc(r.get("mitigation"), 300)}</p>' if txt(r.get("mitigation")) else "")
        + "</li>" for r in (p.get("risks") or [])[:LIMITS["risks"]])
    oos = "".join(f"<li>{esc(x, 200)}</li>" for x in (p.get("out_of_scope") or [])[:LIMITS["out_of_scope"]])

    def section(sid, heading, body, extra=""):
        return f'<section class="block" id="{sid}" aria-labelledby="h-{sid}"><h2 id="h-{sid}">{heading}</h2>{extra}{body}</section>'

    legend = ('<ul class="legend" role="list">' + "".join(f'<li><span class="chip c-{k}">{v}</span></li>' for k, v in KINDS.items()) + "</ul>")
    left = section("scheme", "Схема впровадження", f'<div class="lanes">{flows}</div>', legend)
    left += section("steps", "Кроки", f'<ol class="steps" role="list">{steps}</ol>')
    right = section("files", "Файли", f'<ul class="files" role="list">{files}</ul>')
    if tests:
        right += section("tests", "Тести", f'<ul class="tests" role="list">{tests}</ul>')
    if risks:
        right += section("risks", "Ризики", f'<ul class="risks" role="list">{risks}</ul>')
    if oos:
        right += section("oos", "Поза межами задачі", f'<ul class="oos">{oos}</ul>')

    return f"""<title>{tid} {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Unbounded:wght@500;600&display=swap">
<style>
/* Layout: mobile first — одна колонка; від 760px лінії схеми поруч; від 1100px дві колонки: схема й кроки | файли, тести, ризики */
:root {{
  --paper: #f3f5f1; --sheet: #ffffff; --ink: #17201c; --muted: #56645e; --line: #d3dcd6;
  --accent: #0b6a55; --accent-ink: #ffffff; --accent-wash: #dfefe8;
  --new: #0b6a55; --new-wash: #dfefe8; --mod: #8f5300; --mod-wash: #f6ead5;
  --keep: #56645e; --keep-wash: #e9edea; --ext: #36569a; --ext-wash: #e3e9f6;
  --risk: #9e2f27; --risk-wash: #f7e4e1;
  --display: "Unbounded", "IBM Plex Sans", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --r: 10px;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --paper: #0f1512; --sheet: #161e1a; --ink: #e2eae6; --muted: #9baba4; --line: #2a3631;
  --accent: #4fc4a3; --accent-ink: #08201a; --accent-wash: #12302a;
  --new: #4fc4a3; --new-wash: #12302a; --mod: #e2a64c; --mod-wash: #33250f;
  --keep: #9baba4; --keep-wash: #1f2925; --ext: #91aaea; --ext-wash: #1a2442;
  --risk: #ee8b80; --risk-wash: #3a1b17; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --paper: #0f1512; --sheet: #161e1a; --ink: #e2eae6; --muted: #9baba4; --line: #2a3631;
  --accent: #4fc4a3; --accent-ink: #08201a; --accent-wash: #12302a;
  --new: #4fc4a3; --new-wash: #12302a; --mod: #e2a64c; --mod-wash: #33250f;
  --keep: #9baba4; --keep-wash: #1f2925; --ext: #91aaea; --ext-wash: #1a2442;
  --risk: #ee8b80; --risk-wash: #3a1b17; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--paper); color: var(--ink); font: 400 16px/1.55 var(--body); }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-inline: 16px; padding-block: 20px 40px; display: grid; gap: 20px; }}
a {{ color: var(--accent); text-underline-offset: 3px; }}
a:focus-visible, .btn:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 2px; }}
code {{ font-family: var(--mono); font-size: 0.9em; overflow-wrap: anywhere; }}
h1, h2 {{ text-wrap: balance; margin: 0; }}
p {{ margin: 0; }}
.head {{ display: grid; gap: 12px; }}
.eyebrow {{ font: 500 13px/1.3 var(--mono); color: var(--muted); letter-spacing: 0.02em; overflow-wrap: anywhere; }}
h1 {{ font: 600 clamp(1.45rem, 5.4vw, 2.2rem)/1.2 var(--display); letter-spacing: -0.01em; }}
.summary {{ font-size: 1.05rem; max-width: 65ch; }}
.status {{ justify-self: start; display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border-radius: 999px;
  background: var(--mod-wash); color: var(--mod); font: 600 13px/1.4 var(--body); }}
.status::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }}
.meta {{ display: grid; grid-template-columns: max-content 1fr; gap: 6px 14px; margin: 0; font-size: 14px; }}
.meta dt {{ color: var(--muted); }}
.meta dd {{ margin: 0; min-width: 0; overflow-wrap: anywhere; }}
.approve {{ display: grid; gap: 12px; padding: 14px 16px; border-radius: var(--r); background: var(--accent-wash); }}
.approve p {{ max-width: 65ch; }}
.btn {{ justify-self: start; display: inline-block; padding: 10px 16px; border-radius: 8px; background: var(--accent); color: var(--accent-ink);
  font-weight: 600; text-decoration: none; }}
.cols {{ display: grid; gap: 20px; }}
.col {{ display: grid; gap: 20px; align-content: start; min-width: 0; }}
.block {{ background: var(--sheet); border: 1px solid var(--line); border-radius: var(--r); padding: 16px; display: grid; gap: 14px; min-width: 0; }}
h2 {{ font: 600 1.05rem/1.3 var(--display); }}
.legend, .flow, .steps, .files, .tests, .risks {{ list-style: none; margin: 0; padding: 0; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.chip {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font: 600 12px/1.6 var(--body); letter-spacing: 0.02em; white-space: nowrap; }}
.c-new {{ background: var(--new-wash); color: var(--new); }}
.c-modified {{ background: var(--mod-wash); color: var(--mod); }}
.c-existing {{ background: var(--keep-wash); color: var(--keep); }}
.c-external {{ background: var(--ext-wash); color: var(--ext); }}
.c-deleted {{ background: var(--risk-wash); color: var(--risk); }}
.lanes {{ display: grid; gap: 18px; align-items: start; }}
.lane {{ margin: 0; display: grid; gap: 10px; min-width: 0; align-content: start; }}
.lane-name {{ font: 500 12px/1.3 var(--mono); text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
.flow {{ display: grid; justify-items: stretch; }}
.node {{ display: grid; gap: 4px; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--line); background: var(--paper); min-width: 0; }}
.node .chip {{ justify-self: start; }}
.k-new {{ border-color: var(--new); }}
.k-modified {{ border-color: var(--mod); }}
.k-external {{ border-style: dashed; }}
.node-label {{ font-weight: 600; overflow-wrap: anywhere; }}
.node-note {{ font-size: 14px; color: var(--muted); }}
.edge {{ display: grid; grid-template-columns: 24px 1fr; align-items: center; min-height: 34px; padding-left: 12px; color: var(--muted); }}
.arrow {{ width: 12px; height: 30px; display: block; }}
.edge-label {{ font: 400 13px/1.35 var(--mono); overflow-wrap: anywhere; }}
.steps {{ display: grid; gap: 12px; counter-reset: none; }}
.step {{ display: grid; grid-template-columns: 30px 1fr; gap: 10px; align-items: start; }}
.step-n {{ display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid var(--accent);
  color: var(--accent); font: 500 13px/1 var(--mono); font-variant-numeric: tabular-nums; }}
.step-body {{ display: grid; gap: 2px; min-width: 0; }}
.step-title {{ font-weight: 600; }}
.step-detail {{ color: var(--muted); font-size: 15px; }}
.files, .tests, .risks {{ display: grid; gap: 12px; }}
.file {{ display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; align-items: baseline; }}
.file .path {{ min-width: 0; }}
.file-why {{ grid-column: 2; color: var(--muted); font-size: 14px; }}
.test {{ display: grid; gap: 6px; }}
.checks {{ margin: 0; padding-left: 20px; display: grid; gap: 3px; font-size: 15px; }}
.risk {{ display: grid; gap: 4px; padding-left: 12px; border-left: 3px solid var(--risk); }}
.risk-fix {{ color: var(--muted); font-size: 15px; }}
.label {{ font: 600 12px/1.4 var(--body); text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink); margin-right: 4px; }}
.oos {{ margin: 0; padding-left: 20px; display: grid; gap: 4px; color: var(--muted); }}
.foot {{ color: var(--muted); font-size: 13px; display: grid; gap: 4px; }}
@media (min-width: 760px) {{
  .wrap {{ padding-inline: 28px; padding-block: 32px 56px; gap: 24px; }}
  .lanes {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 22px; }}
  .meta {{ grid-template-columns: max-content 1fr max-content 1fr; }}
  .approve {{ grid-template-columns: 1fr auto; align-items: center; }}
  .block {{ padding: 20px 22px; }}
}}
@media (min-width: 1100px) {{
  .cols {{ grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); align-items: start; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto; }} }}
</style>
<div class="wrap">
  <header class="head">
    <p class="eyebrow">{tid} · {repo}</p>
    <h1>{title}</h1>
    <p class="summary">{esc(p["summary"], 700)}</p>
    <p class="status">Очікує погодження</p>
    <dl class="meta">
      <dt>Гілка</dt><dd><code>{branch}</code></dd>
      <dt>Сесія</dt><dd>{session_cell}</dd>
      <dt>Складено</dt><dd>{generated}</dd>
      <dt>Версія плану</dt><dd><code>sha256 {sha}</code></dd>
    </dl>
  </header>
  <div class="approve">
    <p>План погоджує розробник у сесії: кнопка <b>Allow once</b> на картці <code>approve_plan</code>. Ця сторінка лише показує план.</p>
    {approve_btn}
  </div>
  <div class="cols">
    <div class="col">{left}</div>
    <div class="col">{right}</div>
  </div>
  <footer class="foot">
    <p>Сторінку згенерувала сесія Claude Code з файлу плану. Зміни в коді почнуться лише після погодження.</p>
  </footer>
</div>
"""


def main():
    if len(sys.argv) != 2:
        fail("використання: python3 .claude/pipeline/plan_artifact.py /tmp/pipeline-plan/<ID>.json")
    src = sys.argv[1]
    if not src.endswith(".json") or not inside_plan_dir(src):
        fail(f"вхідний файл має бути .json у {PLAN_DIR}")
    try:
        with open(src, encoding="utf-8") as fh:
            plan = json.load(fh)
    except Exception as e:
        fail(f"не вдалося прочитати JSON: {e}")
    if not isinstance(plan, dict):
        fail("JSON має бути об'єктом")
    plan.setdefault("session_url", session_url())
    plan.setdefault("branch", git_branch())
    validate(plan)
    canon = json.dumps({k: v for k, v in plan.items() if k not in ("session_url", "branch")}, ensure_ascii=False, sort_keys=True)
    sha = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    out = os.path.join(PLAN_DIR, txt(plan["task_id"], 20) + ".html")
    if not inside_plan_dir(out):
        fail("вихідний шлях поза каталогом плану")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(plan, sha, generated))
    print(f"PLAN ARTIFACT: OK {out} sha={sha}")


if __name__ == "__main__":
    main()
