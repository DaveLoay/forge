#!/usr/bin/env bash
# Checks which way of starting the Interrogator actually runs it.
# Each variant asks for one reply in print mode; the Interrogator must open with its banner.
# Usage: bash dev/agent-smoke.sh
set -u
FORGE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)/smoke-project"
"$FORGE/bin/forge-init" "$WORK" >/dev/null
cd "$WORK" || exit 1
BANNER="forge · stage 1/5 · Interrogator"
PROMPT="Start the interview. Reply with your first message only."

run() {
  local label="$1"; shift
  local out
  out="$(claude -p "$PROMPT" --plugin-dir "$FORGE" "$@" 2>&1 | head -c 600)"
  if grep -qF "$BANNER" <<<"$out"; then
    echo "PASS  $label"
  else
    echo "FAIL  $label"
  fi
  echo "      first reply: $(head -n 3 <<<"$out" | tr '\n' ' ' | cut -c1-160)"
}

echo "forge plugin: $FORGE"
echo "test project: $WORK"
echo
run "A  --agent forge:interrogator" --agent forge:interrogator
run "B  --agent interrogator"       --agent interrogator
run "C  settings agent=forge:interrogator" --settings '{"agent":"forge:interrogator"}'
