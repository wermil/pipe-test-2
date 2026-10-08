#!/usr/bin/env python3
"""Звіт тестового прогону. Без секретів: лише стан перевірок і рішень.
Запуск: python3 .claude/pipeline/report.py [--diag]"""
import json, os, re, subprocess, sys, urllib.request, urllib.error
from collections import Counter

S = os.path.join(os.path.expanduser("~"), ".pipeline")
def load(name):
    try: return json.load(open(os.path.join(S, name)))
    except Exception: return None
def run(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e: return f"помилка: {e.__class__.__name__}"

a = load("attest.json") or {}
ev = []
try:
    ev = [json.loads(l) for l in open(os.path.join(S, "events.log")) if l.strip()]
except Exception:
    pass
ap = load("approved.json")
print("=== PIPELINE REPORT ===")
print(f"attest: {a.get('status', 'немає')} {('— ' + a['reason']) if a.get('reason') else ''}")
print(f"repo: потрібен {a.get('want_repo')} | origin {a.get('have_repo')}")
print(f"env: потрібне {a.get('want_env')} | ORG_ENV_ID {a.get('have_env')} | /opt/org-env/id {a.get('have_env_file')}")
print(f"session id prefix: {a.get('session_prefix') or 'немає'} | url: {a.get('session_url') or 'немає'}")
starts = [e.get('attest') for e in ev if e.get('event') == 'SessionStart']
print(f"SessionStart: {len(starts)} ({', '.join(x or '?' for x in starts)})")
modes = sorted({e.get('mode') for e in ev if e.get('event') == 'PreToolUse' and e.get('mode')})
print(f"permission modes: {', '.join(modes) or 'немає'}")
pt = [e for e in ev if e.get('event') == 'PreToolUse']
c = Counter((e.get('decision'), e.get('phase') or e.get('reason')) for e in pt)
print("gate: " + ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(c.items())) if c else "gate: подій немає")
for e in [e for e in pt if e.get('decision') == 'deny'][:10]:
    print(f"  deny {e['at']} {e['tool']} ({e.get('reason')}) {e.get('cmd', '')}".rstrip())
apc = [e for e in ev if e.get('event') == 'approve_plan']
print(f"approve_plan: {apc[-1]['at'] + ' ' + apc[-1].get('plan_id', '') if apc else 'не викликався або не погоджено'}")
print(f"approved.json: {'так' if ap else 'ні'}")
print(f"plan artifact: {(ap or {}).get('artifact_url') or 'немає'} | sha: {(ap or {}).get('plan_sha') or 'немає'}")
lin = [e for e in pt if str(e.get('reason', '')).startswith('linear')]
lc = [e for e in lin if e.get('reason') == 'linear-comment']
print(f"linear: коментарів {len(lc)} ({', '.join(sorted({e.get('issue', '') for e in lc})) or '—'}), відмов {len([e for e in lin if e.get('decision') == 'deny'])}")
cfg = [e for e in ev if e.get('event') == 'ConfigChange']
print(f"ConfigChange заблоковано: {len(cfg)}")
if "--diag" in sys.argv:
    print("--- diag ---")
    print("python:", sys.version.split()[0], "| node:", run(["node", "--version"]), "| gh:", run(["gh", "--version"]).splitlines()[0] if run(["gh", "--version"]) else "немає")
    print("git branch:", run(["git", "rev-parse", "--abbrev-ref", "HEAD"]))
    repo = a.get("want_repo") or ""
    print("gh api repo:", run(["gh", "api", f"repos/{repo}", "--jq", ".full_name"]) if repo else "немає repo-id")
    try:
        urllib.request.urlopen("https://example.com", timeout=8); code = "200 (мережа відкрита)"
    except urllib.error.HTTPError as e:
        code = f"{e.code} {e.headers.get('x-deny-reason', '')}".strip()
    except Exception as e:
        code = f"помилка: {e.__class__.__name__}"
    print("example.com:", code)
print("=== END ===")
