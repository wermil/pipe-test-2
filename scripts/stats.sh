#!/usr/bin/env bash
# Виводить статистику цілих чисел з аргументів: рядки count, min, max, avg
# (avg з двома знаками після коми).
# Без аргументів або з нечисловим значенням: повідомлення в stderr і код виходу 1.
set -u

source "$(dirname "$0")/lib/numbers.sh"

if [[ $# -eq 0 ]]; then
  echo "stats.sh: немає чисел" >&2
  exit 1
fi

count=0
total=0
for arg in "$@"; do
  if ! is_int "$arg"; then
    echo "stats.sh: не число: '$arg'" >&2
    exit 1
  fi
  n=$(to_int "$arg")
  if (( count == 0 || n < min )); then min=$n; fi
  if (( count == 0 || n > max )); then max=$n; fi
  total=$(( total + n ))
  count=$(( count + 1 ))
done

echo "count $count"
echo "min $min"
echo "max $max"
awk -v s="$total" -v c="$count" 'BEGIN { printf "avg %.2f\n", s / c }'
