#!/usr/bin/env bash
# Виводить суму цілих чисел, переданих аргументами. Без аргументів — 0.
# Нечислове значення: повідомлення в stderr і код виходу 1.
set -u

source "$(dirname "$0")/lib/numbers.sh"

total=0
for arg in "$@"; do
  if ! is_int "$arg"; then
    echo "sum.sh: не число: '$arg'" >&2
    exit 1
  fi
  total=$(( total + $(to_int "$arg") ))
done

echo "$total"
