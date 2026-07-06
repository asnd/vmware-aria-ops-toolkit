#!/usr/bin/env bash
# Generate browsable Robot Framework keyword docs (libdoc HTML) into docs/.
# Output is gitignored; run this locally or in CI to (re)produce the docs.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p docs

RESOURCES="common policy_api ssh_keywords traffic_keywords bbprobe_keywords failure_keywords"
TOTAL=$(( $(echo "$RESOURCES" | wc -w) + 2 ))
i=0

step() { i=$((i + 1)); echo "[$i/$TOTAL] libdoc $1" >&2; }

step "nsxt_robot.NsxtApi"
uv run python -m robot.libdoc src/nsxt_robot/api.py docs/NsxtApi.html

step "nsxt_robot.BbprobeRelease"
uv run python -m robot.libdoc src/nsxt_robot/bbprobe_release.py docs/BbprobeRelease.html

for r in $RESOURCES; do
    step "resources/$r.robot"
    uv run python -m robot.libdoc "src/nsxt_robot/resources/$r.robot" "docs/$r.html"
done

echo "Docs written to docs/*.html" >&2
