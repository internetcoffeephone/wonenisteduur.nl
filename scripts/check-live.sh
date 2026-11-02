#!/usr/bin/env bash
# Check that the live site serves pages with the expected content, e.g. after a push to main.
#
#   scripts/check-live.sh PATH PATTERN [PATH PATTERN ...]
#   scripts/check-live.sh /amsterdam/methode/ 'id=den-haag' /amsterdam/data/x.csv '^buurtcode,'
#
# Exits 0 when every PATH returns HTTP 200 and its body matches PATTERN (grep -E), 1 otherwise.
# A query string bypasses the GitHub Pages cache. To wait for a deploy:
#   ~/src/agent-skills/bin/poll --budget 240 -- scripts/check-live.sh ...
set -u
base=${SITE:-https://wonenisteduur.nl}
if (( $# == 0 || $# % 2 )); then
  echo "usage: $0 PATH PATTERN [PATH PATTERN ...]" >&2
  exit 2
fi
ok=0
while (( $# )); do
  path=$1 pattern=$2
  shift 2
  body=$(curl -sS --max-time 20 -w '\n%{http_code}' "$base$path?check=$(date +%s)") || body=$'\n000'
  code=${body##*$'\n'}
  if [[ $code != 200 ]]; then
    echo "$path: HTTP $code"
    ok=1
  elif ! grep -qE -- "$pattern" <<<"${body%$'\n'*}"; then
    echo "$path: no match for $pattern"
    ok=1
  else
    echo "$path: ok"
  fi
done
exit $ok
