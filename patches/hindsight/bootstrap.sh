#!/usr/bin/env bash
# Install pinned client hooks and converge private settings on Mac/VPS.
# The API and database run only on the VPS.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" = true ]; then
  exit 0
fi
for tool in node npx jq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[hindsight-bootstrap] missing $tool" >&2
    exit 1
  fi
done

profile=
if [ -f "$HOME/.dotagents-profile" ]; then
  IFS= read -r profile < "$HOME/.dotagents-profile" || :
fi
case "$profile" in
  mac) url=https://cc-experiments.taile39822.ts.net:9077 ;;
  vps) url=http://127.0.0.1:9077 ;;
  *work*)
    echo "[hindsight-bootstrap] profile $profile is a company machine; its memory stays off the homelab" >&2
    exit 1
    ;;
  *)
    echo "[hindsight-bootstrap] install dotagents with --profile mac or vps first" >&2
    exit 1
    ;;
esac
config_dir="$HOME/.hindsight"
config="$config_dir/coding-agent.json"
mkdir -p "$config_dir"
chmod 700 "$config_dir"
if [ -L "$config" ]; then
  echo "[hindsight-bootstrap] $config is a symlink; refusing to replace it" >&2
  exit 1
fi
if [ -e "$config" ] && ! jq -e 'type == "object"' "$config" >/dev/null; then
  echo "[hindsight-bootstrap] $config is not a JSON object; leaving it untouched" >&2
  exit 1
fi

# The official Codex installer stages the shared runtime and merges only Codex
# hooks. Claude hooks already live in dotagents' settings.shared.json.
npx --yes @vectorize-io/hindsight-coding-agents@0.6.1 install codex \
  --server self-hosted --api-url "$url"

# With reflect's synthesis down, the hooks inject raw recalled observations
# instead (10 KB seen, none of it on topic), which every later turn re-reads.
# 0.6.1 has no option for that, so the fallback branch is cut out of each
# bundled hook; the agent still has the Hindsight tools to search.
# ponytail: string patch on the pinned bundle; drop it once upstream has an opt-out.
dist="$config_dir/coding-agents/dist"
patched='e instanceof ReflectError && e.fallbackEligible && false)'
for js in "$dist"/*.js; do
  if grep -qF 'e instanceof ReflectError && e.fallbackEligible)' "$js"; then
    perl -pi -e 's/e instanceof ReflectError && e\.fallbackEligible\)/e instanceof ReflectError \&\& e.fallbackEligible \&\& false)/' "$js"
  fi
done
if ! grep -qF "$patched" "$dist/claude-hook.js" 2>/dev/null; then
  echo "[hindsight-bootstrap] $dist/claude-hook.js has no reflect fallback to switch off; recheck the patch for this version" >&2
  exit 1
fi

# The tool guide comes once per session at SessionStart; pageRefreshEveryTurns
# re-injects it every N turns. 0 reads as 10 (`|| 10`), so N outlasts any session.
tmp=$(mktemp "$config_dir/.coding-agent.XXXXXX")
trap 'rm -f "$tmp"' EXIT
jq --arg url "$url" '. + {
  serverMode: "self-hosted",
  apiUrl: $url,
  autoUpdate: false,
  autoSeed: false,
  gitIngest: "none",
  codebaseSurvey: false,
  bankIdTemplate: "coding-agent-{gitProject}",
  maxParallelRetains: 2,
  retainSessions: true,
  reflectTimeoutMs: 5000,
  pageRefreshEveryTurns: 1000000
}' "$config" > "$tmp"
chmod 600 "$tmp"
if ! cmp -s "$config" "$tmp"; then
  mv "$tmp" "$config"
fi
omp_dir="$HOME/.omp/agent"
env_file="$omp_dir/.env"
mkdir -p "$omp_dir"
if [ -L "$env_file" ] || { [ -e "$env_file" ] && [ ! -f "$env_file" ]; }; then
  echo "[hindsight-bootstrap] $env_file is not a regular private file" >&2
  exit 1
fi
env_tmp=$(mktemp "$omp_dir/.env.XXXXXX")
trap 'rm -f "$tmp" "$env_tmp"' EXIT
if [ -f "$env_file" ]; then
  sed '/^HINDSIGHT_API_URL=/d' "$env_file" > "$env_tmp"
fi
printf 'HINDSIGHT_API_URL=%s\n' "$url" >> "$env_tmp"
chmod 600 "$env_tmp"
if ! cmp -s "$env_file" "$env_tmp"; then
  mv "$env_tmp" "$env_file"
fi
chmod 600 "$env_file"
echo "[hindsight-bootstrap] $profile client configured; server and database remain on the VPS"
