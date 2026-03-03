#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/skills"
DEST_ROOT="${CODEX_HOME:-$HOME/.codex}"
DEST_DIR="$DEST_ROOT/skills"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "[skills] project skills directory not found: $SRC_DIR"
  exit 1
fi

mkdir -p "$DEST_DIR"

installed=()
for skill_path in "$SRC_DIR"/*; do
  [[ -d "$skill_path" ]] || continue
  skill_name="$(basename "$skill_path")"
  if [[ ! -f "$skill_path/SKILL.md" ]]; then
    continue
  fi
  ln -sfn "$skill_path" "$DEST_DIR/$skill_name"
  installed+=("$skill_name")
done

echo "[skills] linked project skills to $DEST_DIR"
if [[ ${#installed[@]} -gt 0 ]]; then
  echo "[skills] installed: ${installed[*]}"
else
  echo "[skills] no skills found to install"
fi

