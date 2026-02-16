#!/usr/bin/env bash
# Manage databricks-agent-skills in any project's .claude/skills/ directory via symlinks.
# Skills in .claude/skills/ are auto-triggered by Claude when relevant to the conversation.
#
# Usage:
#   manage-skills.sh list                    # List available skills
#   manage-skills.sh add [skill...] [--to DIR]   # Add skills to a project
#   manage-skills.sh remove [skill...] [--from DIR]  # Remove skills from a project
#   manage-skills.sh status [--in DIR]       # Show which skills are installed in a project
#
# If no skills are specified for add/remove, an interactive picker is shown.
# If no target directory is given, defaults to the current working directory.

set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "$0")/../commands" && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  list                          List all available skills
  add [skill...] [--to DIR]     Symlink skills into a project's .claude/skills/
  remove [skill...] [--from DIR] Remove skill symlinks from a project
  status [--in DIR]             Show which skills are installed in a project

Options:
  --to, --from, --in DIR        Target project directory (default: \$PWD)
  --all                         Apply to all skills

Examples:
  $(basename "$0") list
  $(basename "$0") add multi-agent-architecture --to ~/my-project
  $(basename "$0") add --all
  $(basename "$0") remove excalidraw-diagram
  $(basename "$0") status
EOF
  exit 1
}

available_skills() {
  for f in "$SKILLS_DIR"/*.md; do
    basename "$f" .md
  done
}

cmd_list() {
  echo "Available skills:"
  for skill in $(available_skills); do
    desc=$(grep -m1 '^description:' "$SKILLS_DIR/${skill}.md" 2>/dev/null | sed 's/^description: *//' || echo "")
    printf "  %-30s %s\n" "$skill" "$desc"
  done
}

cmd_status() {
  local target="$1"
  local cmd_dir="$target/.claude/skills"

  echo "Project: $target"
  echo ""

  if [ ! -d "$cmd_dir" ]; then
    echo "  No .claude/skills/ directory found."
    return
  fi

  local found=0
  for skill in $(available_skills); do
    if [ -L "$cmd_dir/${skill}.md" ]; then
      echo "  [installed] $skill"
      found=1
    elif [ -f "$cmd_dir/${skill}.md" ]; then
      echo "  [copied]    $skill  (not symlinked)"
      found=1
    fi
  done

  if [ "$found" -eq 0 ]; then
    echo "  No skills installed."
  fi
}

pick_skills() {
  local action="$1"
  local target="$2"
  local cmd_dir="$target/.claude/skills"
  local skills=()
  local i=1

  echo "Available skills:"
  for skill in $(available_skills); do
    if [ "$action" = "add" ]; then
      if [ -L "$cmd_dir/${skill}.md" ] 2>/dev/null; then
        printf "  %d) %-30s [already installed]\n" "$i" "$skill"
      else
        printf "  %d) %s\n" "$i" "$skill"
      fi
    else
      if [ -L "$cmd_dir/${skill}.md" ] 2>/dev/null || [ -f "$cmd_dir/${skill}.md" ] 2>/dev/null; then
        printf "  %d) %s\n" "$i" "$skill"
      else
        printf "  %d) %-30s [not installed]\n" "$i" "$skill"
      fi
    fi
    skills+=("$skill")
    ((i++))
  done

  echo ""
  read -rp "Enter skill numbers (comma-separated, or 'all'): " selection

  if [ "$selection" = "all" ]; then
    echo "${skills[*]}"
    return
  fi

  local selected=()
  IFS=',' read -ra nums <<< "$selection"
  for num in "${nums[@]}"; do
    num=$(echo "$num" | tr -d ' ')
    if [ "$num" -ge 1 ] 2>/dev/null && [ "$num" -le "${#skills[@]}" ] 2>/dev/null; then
      selected+=("${skills[$((num-1))]}")
    fi
  done
  echo "${selected[*]}"
}

cmd_add() {
  local target="$1"
  shift
  local skills=("$@")
  local cmd_dir="$target/.claude/skills"

  mkdir -p "$cmd_dir"

  for skill in "${skills[@]}"; do
    local src="$SKILLS_DIR/${skill}.md"
    local dest="$cmd_dir/${skill}.md"

    if [ ! -f "$src" ]; then
      echo "  [skip] $skill — not found in commands/"
      continue
    fi

    if [ -L "$dest" ]; then
      echo "  [skip] $skill — already installed"
      continue
    fi

    ln -sf "$src" "$dest"
    echo "  [added] $skill"
  done
}

cmd_remove() {
  local target="$1"
  shift
  local skills=("$@")
  local cmd_dir="$target/.claude/skills"

  for skill in "${skills[@]}"; do
    local dest="$cmd_dir/${skill}.md"

    if [ -L "$dest" ] || [ -f "$dest" ]; then
      rm -f "$dest"
      echo "  [removed] $skill"
    else
      echo "  [skip] $skill — not installed"
    fi
  done
}

# --- Main ---

[ $# -lt 1 ] && usage

COMMAND="$1"
shift

TARGET_DIR="$PWD"
USE_ALL=false
SKILLS=()

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --to|--from|--in)
      TARGET_DIR="$2"
      shift 2
      ;;
    --all)
      USE_ALL=true
      shift
      ;;
    -*)
      echo "Unknown option: $1"
      usage
      ;;
    *)
      SKILLS+=("$1")
      shift
      ;;
  esac
done

case "$COMMAND" in
  list)
    cmd_list
    ;;
  status)
    cmd_status "$TARGET_DIR"
    ;;
  add)
    if $USE_ALL; then
      while IFS= read -r s; do SKILLS+=("$s"); done <<< "$(available_skills)"
    elif [ ${#SKILLS[@]} -eq 0 ]; then
      read -ra SKILLS <<< "$(pick_skills add "$TARGET_DIR")"
    fi
    [ ${#SKILLS[@]} -eq 0 ] && { echo "No skills selected."; exit 1; }
    echo "Adding skills to $TARGET_DIR:"
    cmd_add "$TARGET_DIR" "${SKILLS[@]}"
    ;;
  remove)
    if $USE_ALL; then
      while IFS= read -r s; do SKILLS+=("$s"); done <<< "$(available_skills)"
    elif [ ${#SKILLS[@]} -eq 0 ]; then
      read -ra SKILLS <<< "$(pick_skills remove "$TARGET_DIR")"
    fi
    [ ${#SKILLS[@]} -eq 0 ] && { echo "No skills selected."; exit 1; }
    echo "Removing skills from $TARGET_DIR:"
    cmd_remove "$TARGET_DIR" "${SKILLS[@]}"
    ;;
  *)
    echo "Unknown command: $COMMAND"
    usage
    ;;
esac
