#!/usr/bin/env bash
# Тести для scripts/stats.sh
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATS="$ROOT/scripts/stats.sh"
fail=0

check() {
  local name="$1" want_out="$2" want_code="$3"
  shift 3
  local out code
  out="$(bash "$STATS" "$@" 2>/dev/null)"
  code=$?
  if [[ "$out" == "$want_out" && "$code" == "$want_code" ]]; then
    echo "ok   $name"
  else
    echo "FAIL $name: отримано '$out' (код $code), очікувалось '$want_out' (код $want_code)"
    fail=1
  fi
}

check_err() {
  local name="$1"
  shift
  local err code
  err="$(bash "$STATS" "$@" 2>&1 >/dev/null)"
  code=$?
  if [[ -n "$err" && "$code" == 1 ]]; then
    echo "ok   $name"
  else
    echo "FAIL $name: stderr '$err', код $code"
    fail=1
  fi
}

check "3 1 2" $'count 3\nmin 1\nmax 3\navg 2.00' 0 3 1 2
check "від'ємні числа" $'count 3\nmin -5\nmax -1\navg -3.00' 0 -5 -1 -3
check "мішані знаки" $'count 4\nmin -4\nmax 10\navg 1.75' 0 -4 10 -2 3
check "дробове avg" $'count 2\nmin 1\nmax 2\navg 1.50' 0 1 2
check "одне число" $'count 1\nmin 7\nmax 7\navg 7.00' 0 7
check "ведучі нулі" $'count 2\nmin 1\nmax 8\navg 4.50' 0 08 01
check "порожньо — код 1" "" 1
check "нечислове — код 1" "" 1 2 x
check "дробове значення — код 1" "" 1 1.5

check_err "порожньо — повідомлення в stderr"
check_err "нечислове — повідомлення в stderr" 2 abc

exit "$fail"
