#!/usr/bin/env bash
# PreCompact hook: capture full pre-compaction conversation state.
# Fires before Claude Code compacts context (manual /compact or auto-compact),
# so the captured transcript is the rich pre-compact content — not the lossy
# compaction-summary that would survive into the post-compact session.
# Local patch on top of memsearch v0.4.2 — not upstream.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# PreCompact input adds `trigger` ("manual"|"auto") and possibly `custom_instructions`.
TRIGGER=$(_json_val "$INPUT" "trigger" "auto")

# Skip when the required API key is missing — same logic as stop.sh.
_required_env_var() {
  case "$1" in
    openai) echo "OPENAI_API_KEY" ;;
    google) echo "GOOGLE_API_KEY" ;;
    voyage) echo "VOYAGE_API_KEY" ;;
    jina) echo "JINA_API_KEY" ;;
    mistral) echo "MISTRAL_API_KEY" ;;
    *) echo "" ;;
  esac
}
_PROVIDER=$($MEMSEARCH_CMD config get embedding.provider 2>/dev/null || echo "onnx")
_REQ_KEY=$(_required_env_var "$_PROVIDER")
if [ -n "$_REQ_KEY" ] && [ -z "${!_REQ_KEY:-}" ]; then
  _CONFIG_API_KEY=""
  if [ -n "$MEMSEARCH_CMD" ]; then
    _CONFIG_API_KEY=$($MEMSEARCH_CMD config get embedding.api_key 2>/dev/null || echo "")
  fi
  if [ -z "$_CONFIG_API_KEY" ]; then
    echo '{}'
    exit 0
  fi
fi

TRANSCRIPT_PATH=$(_json_val "$INPUT" "transcript_path" "")
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo '{}'
  exit 0
fi

LINE_COUNT=$(wc -l < "$TRANSCRIPT_PATH" 2>/dev/null || echo "0")
if [ "$LINE_COUNT" -lt 3 ]; then
  echo '{}'
  exit 0
fi

ensure_memory_dir

PARSED=$("$SCRIPT_DIR/parse-transcript.sh" "$TRANSCRIPT_PATH" 2>/dev/null || true)
if [ -z "$PARSED" ] || [ "$PARSED" = "(empty transcript)" ] || [ "$PARSED" = "(no user message found)" ] || [ "$PARSED" = "(empty turn)" ]; then
  echo '{}'
  exit 0
fi

TODAY=$(date +%Y-%m-%d)
NOW=$(date +%H:%M)
MEMORY_FILE="$MEMORY_DIR/$TODAY.md"

SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
LAST_USER_TURN_UUID=$(python3 -c "
import json, sys
uuid = ''
with open(sys.argv[1]) as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('type') == 'user' and isinstance(obj.get('message', {}).get('content'), str):
                uuid = obj.get('uuid', '')
        except: pass
print(uuid)
" "$TRANSCRIPT_PATH" 2>/dev/null || true)

AGENT_NAME="Claude Code"
PROMPT_FILE=""
if [ -n "$MEMSEARCH_CMD" ]; then
  PROMPT_FILE=$($MEMSEARCH_CMD config get prompts.summarize 2>/dev/null || true)
fi
if [ -n "$PROMPT_FILE" ] && [ -f "$PROMPT_FILE" ]; then
  SYSTEM_PROMPT=$(sed "s/{{AGENT_NAME}}/$AGENT_NAME/g" "$PROMPT_FILE")
elif [ -f "${CLAUDE_PLUGIN_ROOT}/prompts/summarize.txt" ]; then
  SYSTEM_PROMPT=$(sed "s/{{AGENT_NAME}}/$AGENT_NAME/g" "${CLAUDE_PLUGIN_ROOT}/prompts/summarize.txt")
else
  SYSTEM_PROMPT="You are a third-person note-taker. Summarize the transcript as 2-6 bullet points. Write in third person. Output ONLY bullet points."
fi

SUMMARY=""
if command -v claude &>/dev/null; then
  SUMMARIZE_MODEL="haiku"
  if [ -n "$MEMSEARCH_CMD" ]; then
    CONFIG_MODEL=$($MEMSEARCH_CMD config get plugins.claude-code.summarize.model 2>/dev/null || true)
    if [ -n "$CONFIG_MODEL" ]; then
      SUMMARIZE_MODEL="$CONFIG_MODEL"
    fi
  fi
  SUMMARY=$(printf '%s' "$PARSED" | MEMSEARCH_NO_WATCH=1 CLAUDECODE= claude -p \
    --model "$SUMMARIZE_MODEL" \
    --no-session-persistence \
    --no-chrome \
    --system-prompt "$SYSTEM_PROMPT" \
    2>/dev/null || true)
fi

if [ -z "$SUMMARY" ]; then
  SUMMARY="$PARSED"
fi

{
  echo "### $NOW (pre-compact, trigger=$TRIGGER)"
  if [ -n "$SESSION_ID" ]; then
    echo "<!-- session:${SESSION_ID} turn:${LAST_USER_TURN_UUID} transcript:${TRANSCRIPT_PATH} precompact:${TRIGGER} -->"
  fi
  echo "$SUMMARY"
  echo ""
} >> "$MEMORY_FILE"

kill_orphaned_index
run_memsearch index "$MEMORY_DIR"

echo '{}'
