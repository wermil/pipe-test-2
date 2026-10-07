#!/usr/bin/env python3
"""PreToolUse: блокувальник перед кожною дією (тестова емуляція backend у VM).
Без пройденої перевірки на старті — блок усього. До погодження плану — лише інструменти зі списку дозволених
(читання, read-only Bash, approve_plan, сповіщення). Після approve_plan — дозволено все.
Помилка скрипта блокує дію (обгортка в settings.json)."""
import json, os, re, sys, datetime

S = os.path.join(os.path.expanduser("~"), ".pipeline")
PLAN_TOOLS = {"Read", "Glob", "Grep", "LS", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
              "ToolSearch", "PushNotification", "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
              "mcp__pipeline__approve_plan"}
GITHUB_READ = re.compile(r"^mcp__[^_]*github[^_]*__(get|list|search)_")
READ_CMD = re.compile(
    r"^(cd\s+\S+|ls|cat|head|tail|grep|rg|find|wc|tree|pwd|echo|which|file|stat|du|sort|uniq|cut|tr|basename|dirname|"
    r"check-tools|python3 \.claude/pipeline/report\.py|"
    r"git (status|log|diff|show|ls-files|rev-parse|blame|grep)|git branch|git remote)(\s|$)")

def log(entry):
    entry["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(S, exist_ok=True)
    with open(os.path.join(S, "events.log"), "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def read_only(cmd):
    cmd = re.sub(r"\s*2>(/dev/null|&1)", "", cmd)
    if re.search(r"[>`]|\$\(|<\(|--output", cmd):
        return False
    for seg in re.split(r"\|\||&&|\||;|\n", cmd):
        seg = seg.strip()
        if not seg:
            continue
        if not READ_CMD.match(seg):
            return False
        if seg.startswith("git branch") and not re.fullmatch(r"git branch(\s+(-a|-r|-v|-vv|--list|--show-current))*", seg):
            return False
        if seg.startswith("git remote") and not re.fullmatch(r"git remote(\s+-v|\s+get-url\s+\S+)?", seg):
            return False
        if seg.startswith("find") and re.search(r"\s-(exec|execdir|delete|fprint|fprint0|fprintf|fls|ok|okdir)\b", seg):
            return False
        if re.match(r"(sort|tree)\s", seg) and re.search(r"\s-o", seg):
            return False
        if re.match(r"uniq\s", seg) and len([a for a in seg.split()[1:] if not a.startswith("-")]) > 1:
            return False
    return True

def plan_allowed(tool, inp):
    if tool in PLAN_TOOLS or GITHUB_READ.match(tool):
        return True
    return tool == "Bash" and read_only(str(inp.get("command", "")))

def main():
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return 0
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    base = {"event": "PreToolUse", "tool": tool, "mode": data.get("permission_mode")}
    try:
        attest = json.load(open(os.path.join(S, "attest.json")))
    except Exception:
        attest = {}
    if attest.get("status") != "ok":
        log({**base, "decision": "deny", "reason": "attest"})
        print("PIPELINE: перевірку на старті не пройдено (" + attest.get("reason", "немає результату") + "). Усі інструменти заблоковано.", file=sys.stderr)
        return 2
    if os.path.exists(os.path.join(S, "approved.json")):
        log({**base, "decision": "allow", "phase": "exec"})
        return 0
    if not plan_allowed(tool, inp):
        log({**base, "decision": "deny", "reason": "not-approved", "cmd": str(inp.get("command", ""))[:80] if tool == "Bash" else ""})
        print("PIPELINE: план ще не погоджено. До погодження дозволено лише читання; погодження — через approve_plan.", file=sys.stderr)
        return 2
    log({**base, "decision": "allow", "phase": "plan"})
    return 0

if __name__ == "__main__":
    sys.exit(main())
