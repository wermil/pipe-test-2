#!/usr/bin/env python3
"""PreToolUse: блокувальник перед кожною дією (тестова емуляція backend у VM).
Без пройденої перевірки на старті — блок усього. До погодження плану — лише інструменти зі списку дозволених
(читання, read-only Bash, approve_plan, сповіщення, артефакт плану: запис лише .json/.html у /tmp/pipeline-plan,
генератор plan_artifact.py і публікація Artifact). Після approve_plan — дозволено все, крім Linear.
Linear у будь-якій фазі: читання задачі й статусів і новий коментар save_comment лише до однієї задачі сесії
(після погодження — лише до погодженої). Після погодження ще save_issue для погодженої задачі, лише поле state
зі значенням In Progress або Done. Решта інструментів Linear заборонена.
Помилка скрипта блокує дію (обгортка в settings.json)."""
import json, os, re, sys, datetime

S = os.path.join(os.path.expanduser("~"), ".pipeline")
PLAN_TOOLS = {"Read", "Glob", "Grep", "LS", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
              "ToolSearch", "PushNotification", "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
              "Artifact", "mcp__pipeline__approve_plan"}
PLAN_DIR = "/tmp/pipeline-plan"
PLAN_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
LINEAR_READ = {"get_issue", "list_comments", "list_issue_statuses", "get_issue_status"}
LINEAR_STATES = {"In Progress", "Done"}
TASK_ID = re.compile(r"[A-Z][A-Z0-9]{0,9}-\d{1,6}")
GITHUB_READ = re.compile(r"^mcp__[^_]*github[^_]*__(get|list|search)_")
READ_CMD = re.compile(
    r"^(cd\s+\S+|ls|cat|head|tail|grep|rg|find|wc|tree|pwd|echo|which|file|stat|du|sort|uniq|cut|tr|basename|dirname|"
    r"check-tools|python3 \.claude/pipeline/report\.py|python3 \.claude/pipeline/plan_artifact\.py|"
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

def plan_file_ok(inp):
    path = str(inp.get("file_path", ""))
    if not path or os.path.islink(PLAN_DIR) or not path.endswith((".json", ".html")):
        return False
    return os.path.realpath(path).startswith(os.path.realpath(PLAN_DIR) + os.sep)

def plan_allowed(tool, inp):
    if tool in PLAN_TOOLS or GITHUB_READ.match(tool):
        return True
    if tool in PLAN_WRITE_TOOLS:
        return plan_file_ok(inp)
    return tool == "Bash" and read_only(str(inp.get("command", "")))

def mcp_parts(tool):
    if not tool.startswith("mcp__") or "__" not in tool[5:]:
        return "", ""
    server, name = tool[5:].rsplit("__", 1)
    return server.lower(), name

def linear_check(name, inp, approved):
    """Повертає (дозволено, причина)."""
    if name in LINEAR_READ:
        return True, "linear-read"
    if name == "save_issue":
        if approved is None:
            return False, "linear-status-before-approval"
        if set(inp) != {"id", "state"} or str(inp.get("id")) != approved.get("plan_id") or inp.get("state") not in LINEAR_STATES:
            return False, "linear-status-target"
        return True, "linear-status"
    if name != "save_comment":
        return False, "linear-write"
    iid = str(inp.get("issueId", ""))
    other = ("id", "parentId", "projectId", "initiativeId", "documentId", "milestoneId", "statusUpdateId")
    if any(inp.get(k) for k in other) or not TASK_ID.fullmatch(iid) or len(str(inp.get("body", ""))) > 20000:
        return False, "linear-target"
    if approved is not None and approved.get("plan_id") != iid:
        return False, "linear-not-approved-issue"
    bound_path = os.path.join(S, "linear_issue")
    try:
        bound = open(bound_path).read().strip()
    except Exception:
        bound = ""
    if bound and bound != iid:
        return False, "linear-other-issue"
    if not bound:
        os.makedirs(S, exist_ok=True)
        with open(bound_path, "w") as f:
            f.write(iid)
    return True, "linear-comment"

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
    approved = None
    if os.path.exists(os.path.join(S, "approved.json")):
        try:
            approved = json.load(open(os.path.join(S, "approved.json")))
        except Exception:
            approved = {}
    server, name = mcp_parts(tool)
    if "linear" in server:
        ok, why = linear_check(name, inp, approved)
        log({**base, "decision": "allow" if ok else "deny", "reason": why, "issue": str(inp.get("issueId", ""))[:20]})
        if not ok:
            print("PIPELINE: у Linear дозволено лише читати й коментувати задачу цієї сесії (" + why + ").", file=sys.stderr)
            return 2
        return 0
    if approved is not None:
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
