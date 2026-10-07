#!/usr/bin/env python3
"""MCP-сервер (stdio) з інструментом approve_plan, позначеним requiresUserInteraction.
Тестова емуляція: погодження пишеться у ~/.pipeline/approved.json на машині сесії (техборг TD-1)."""
import json, os, sys, datetime

S = os.path.join(os.path.expanduser("~"), ".pipeline")
KNOWN = {"2024-11-05", "2025-03-26", "2025-06-18"}
TOOLS = [{
    "name": "approve_plan",
    "description": "Погодити план задачі. Виконується лише після кліку розробника Allow. Передай ID задачі й короткий зміст плану.",
    "inputSchema": {"type": "object", "required": ["plan_id", "summary"],
                    "properties": {"plan_id": {"type": "string", "description": "ID задачі, наприклад LIN-1"},
                                   "summary": {"type": "string", "description": "Зміст плану в 1–3 реченнях"}}},
    "_meta": {"anthropic/requiresUserInteraction": True},
}]

def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()

os.makedirs(S, exist_ok=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except ValueError:
        continue
    method, mid = req.get("method"), req.get("id")
    if mid is None:
        continue
    if method == "initialize":
        v = req.get("params", {}).get("protocolVersion")
        reply(mid, {"protocolVersion": v if v in KNOWN else "2025-06-18", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pipeline", "version": "1.0"}})
    elif method == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif method == "tools/call" and req["params"].get("name") == "approve_plan":
        args = req["params"].get("arguments", {})
        rec = {"plan_id": args.get("plan_id", ""), "summary": args.get("summary", ""), "at": now()}
        json.dump(rec, open(os.path.join(S, "approved.json"), "w"), ensure_ascii=False)
        with open(os.path.join(S, "events.log"), "a") as f:
            f.write(json.dumps({"at": rec["at"], "event": "approve_plan", "plan_id": rec["plan_id"]}, ensure_ascii=False) + "\n")
        reply(mid, {"content": [{"type": "text", "text": f"План {rec['plan_id']} погоджено розробником о {rec['at']}. Можна переходити до реалізації."}]})
    elif method == "ping":
        reply(mid, {})
    else:
        reply(mid, error={"code": -32601, "message": "Method not found"})
