#!/bin/bash
# Status line Claude Code: model | katalog | branch | kontekst % | koszt USD.
# Źródło: centminmod/my-claude-code-setup (README, sekcja "Claude Code Statuslines"), zvendorowane bez zmian.
# Instalowane przez setup/install.sh do ~/.claude/statuslines/statusline.sh. Wymaga jq.
# Read JSON input from stdin
input=$(cat)

# Extract model and workspace values
MODEL_DISPLAY=$(echo "$input" | jq -r '.model.display_name')
CURRENT_DIR=$(echo "$input" | jq -r '.workspace.current_dir')

# Extract context window metrics
INPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_input_tokens')
OUTPUT_TOKENS=$(echo "$input" | jq -r '.context_window.total_output_tokens')
CONTEXT_SIZE=$(echo "$input" | jq -r '.context_window.context_window_size')

# Extract cost metrics
COST_USD=$(echo "$input" | jq -r '.cost.total_cost_usd')
LINES_ADDED=$(echo "$input" | jq -r '.cost.total_lines_added')
LINES_REMOVED=$(echo "$input" | jq -r '.cost.total_lines_removed')

# Extract percentage metrics
USED_PERCENTAGE=$(echo "$input" | jq -r '.context_window.used_percentage')
REMAINING_PERCENTAGE=$(echo "$input" | jq -r '.context_window.remaining_percentage')

# Format tokens as Xk
format_tokens() {
    local num="$1"
    if [ "$num" -ge 1000 ]; then
        echo "$((num / 1000))k"
    else
        echo "$num"
    fi
}

# Generate progress bar for context usage
generate_progress_bar() {
    local percentage=$1
    local bar_width=20
    local filled=$(awk "BEGIN {printf \"%.0f\", ($percentage / 100) * $bar_width}")
    local empty=$((bar_width - filled))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done
    echo "$bar"
}

# Calculate total
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

# Generate progress bar
PROGRESS_BAR=$(generate_progress_bar "$USED_PERCENTAGE")

# Show git branch if in a git repo
GIT_BRANCH=""
if git -C "$CURRENT_DIR" rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git -C "$CURRENT_DIR" branch --show-current 2>/dev/null)
    if [ -n "$BRANCH" ]; then
        # Worktree detection
        GIT_DIR=$(git -C "$CURRENT_DIR" rev-parse --git-dir 2>/dev/null)
        WORKTREE=""
        if [[ "$GIT_DIR" == *".git/worktrees/"* ]] || [[ -f "$GIT_DIR/gitdir" ]]; then
            WORKTREE=" 🌳"
        fi
        # Ahead/behind detection
        AHEAD_BEHIND=""
        UPSTREAM=$(git -C "$CURRENT_DIR" rev-parse --abbrev-ref '@{u}' 2>/dev/null)
        if [ -n "$UPSTREAM" ]; then
            AHEAD=$(git -C "$CURRENT_DIR" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
            BEHIND=$(git -C "$CURRENT_DIR" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
            if [ "$AHEAD" -gt 0 ] && [ "$BEHIND" -gt 0 ]; then
                AHEAD_BEHIND=" ↕${AHEAD}/${BEHIND}"
            elif [ "$AHEAD" -gt 0 ]; then
                AHEAD_BEHIND=" ↑${AHEAD}"
            elif [ "$BEHIND" -gt 0 ]; then
                AHEAD_BEHIND=" ↓${BEHIND}"
            fi
        fi
        GIT_BRANCH=" | 🌿 $BRANCH${WORKTREE}${AHEAD_BEHIND}"
    fi
fi

echo "[$MODEL_DISPLAY] 📁 ${CURRENT_DIR##*/}${GIT_BRANCH}
Context: [$PROGRESS_BAR] ${USED_PERCENTAGE}%
Cost: \$${COST_USD} | +${LINES_ADDED} -${LINES_REMOVED} lines"
