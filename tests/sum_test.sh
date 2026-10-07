#!/usr/bin/env bash
# Тести для scripts/sum.sh
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUM="$ROOT/scripts/sum.sh"
fail=0

check() {
  local name="$1" want_out="$2" want_code="$3"
  shift 3
  local out code
  out="$(bash "$SUM" "$@" 2>/dev/null)"
  code=$?
  if [[ "$out" == "$want_out" && "$code" == "$want_code" ]]; then
    echo "ok   $name"
  else
    echo "FAIL $name: отримано '$out' (код $code), очікувалось '$want_out' (код $want_code)"
    fail=1
  fi
}

check "2 3 5 = 10" "10" 0 2 3 5
check "порожньо = 0" "0" 0
check "нечислове — код 1" "" 1 2 x
check "від'ємні числа" "-1" 0 2 -3
check "ведучі нулі" "9" 0 08 01

err="$(bash "$SUM" abc 2>&1 >/dev/null)"
if [[ -n "$err" ]]; then
  echo "ok   нечислове — повідомлення в stderr"
else
  echo "FAIL нечислове — немає повідомлення в stderr"
  fail=1
fi

exit "$fail"
