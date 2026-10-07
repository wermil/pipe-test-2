#!/usr/bin/env bash
# SessionStart: перевіряє, що сесія в правильному репозиторії й оточенні.
# Тестова емуляція backend: результат пишеться у ~/.pipeline/attest.json, gate.py його читає.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cat > /dev/null                                   # вхід hook не потрібен
S="$HOME/.pipeline"; mkdir -p "$S"
P="$CLAUDE_PROJECT_DIR/.claude"
want_env=$(tr -d '[:space:]' 2>/dev/null < "$P/allowed-env")
want_repo=$(tr -d '[:space:]' 2>/dev/null < "$P/repo-id")
have_env="${ORG_ENV_ID:-}"
have_env_file=$(tr -d '[:space:]' 2>/dev/null < /opt/org-env/id)
remote=$(git -C "$CLAUDE_PROJECT_DIR" remote get-url origin 2>/dev/null)
have_repo=$(printf '%s' "$remote" | sed -E 's#\.git$##; s#/+$##' | awk -F'[/:]' '{ if (NF>=2) print $(NF-1)"/"$NF }')

reason=""
if   [ -z "$want_env" ];                 then reason="у репозиторії немає .claude/allowed-env"
elif [ -z "$want_repo" ];                then reason="у репозиторії немає .claude/repo-id"
elif [ "$have_env" != "$want_env" ];     then reason="оточення не те: потрібне '$want_env', змінна ORG_ENV_ID='$have_env'"
elif [ "$have_env_file" != "$want_env" ]; then reason="оточення не те: потрібне '$want_env', файл /opt/org-env/id='$have_env_file'"
elif [ "${have_repo,,}" != "${want_repo,,}" ]; then reason="репозиторій не той: потрібен '$want_repo', origin='$have_repo'"
fi
status=ok; [ -n "$reason" ] && status=fail

STATUS="$status" REASON="$reason" WANT_ENV="$want_env" HAVE_ENV="$have_env" HAVE_ENV_FILE="$have_env_file" \
WANT_REPO="$want_repo" HAVE_REPO="$have_repo" SOURCE_DIR="$S" python3 - <<'PY'
import json, os, datetime
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
st = {"status": os.environ["STATUS"], "reason": os.environ["REASON"], "at": now,
      "want_env": os.environ["WANT_ENV"], "have_env": os.environ["HAVE_ENV"], "have_env_file": os.environ["HAVE_ENV_FILE"],
      "want_repo": os.environ["WANT_REPO"], "have_repo": os.environ["HAVE_REPO"],
      "session_prefix": sid[:4], "session_url": ("https://claude.ai/code/" + sid.replace("cse_", "session_", 1)) if sid else ""}
d = os.environ["SOURCE_DIR"]
json.dump(st, open(os.path.join(d, "attest.json"), "w"), ensure_ascii=False)
with open(os.path.join(d, "events.log"), "a") as f:
    f.write(json.dumps({"at": now, "event": "SessionStart", "attest": st["status"], "reason": st["reason"]}, ensure_ascii=False) + "\n")
PY

if [ "$status" = ok ]; then
  echo "PIPELINE: перевірку на старті пройдено. Репозиторій $have_repo, оточення $have_env. До погодження плану дозволено лише читання."
else
  echo "PIPELINE: ПЕРЕВІРКУ НЕ ПРОЙДЕНО: $reason. Усі інструменти заблоковано. Коротко повідом причину і зупинись."
fi
exit 0
