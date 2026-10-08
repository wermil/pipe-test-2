#!/usr/bin/env bash
# Виводить суму цілих чисел, переданих аргументами. Без аргументів — 0.
# Нечислове значення: повідомлення в stderr і код виходу 1.
set -u

total=0
for arg in "$@"; do
  if [[ ! "$arg" =~ ^-?[0-9]+$ ]]; then
    echo "sum.sh: не число: '$arg'" >&2
    exit 1
  fi
  if [[ "$arg" == -* ]]; then
    total=$(( total - 10#${arg#-} ))
  else
    total=$(( total + 10#$arg ))
  fi
done

echo "$total"
