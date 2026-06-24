# Shell extensions for dotagents-managed tools (memsearch, mdsmith, claude
# wrappers in ~/.local/bin). Sourced from ~/.bashrc / ~/.zshrc via a line
# `dotagents install` appends; the rc files themselves stay machine-owned.
# POSIX sh — keep bash/zsh compatible. Add entries only for tools/skills this
# repo introduces, not general shell config.

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# memsearch global memory store
[ -d "$HOME/dev/kb/memory" ] && export MEMSEARCH_DIR="$HOME/dev/kb/memory"

# Per-directory agent config profile. Sets CLAUDE_CONFIG_DIR by cwd so every tool
# that honors it (claude, omnigent, oh-my-pi) shares one config home per project
# group. Outside a group the var is unset → tools use their own default ~/.claude,
# which is the dev profile. So a forgotten group, a GUI/Dock launch, or a daemon
# started without the var all land on dev. Add a group = add a case line.
_dotagents_profile() {
  case "$PWD/" in
    "$HOME"/knowledge/*) export CLAUDE_CONFIG_DIR="$HOME/.claude-knowledge" ;;
    *) unset CLAUDE_CONFIG_DIR ;;
  esac
}
if [ -n "${ZSH_VERSION:-}" ]; then
  autoload -Uz add-zsh-hook 2>/dev/null && add-zsh-hook chpwd _dotagents_profile
elif [ -n "${BASH_VERSION:-}" ]; then
  case ";${PROMPT_COMMAND:-};" in
    *";_dotagents_profile;"*) ;;
    *) PROMPT_COMMAND="_dotagents_profile;${PROMPT_COMMAND:-}" ;;
  esac
fi
_dotagents_profile  # set for the shell's starting directory

# pixelshot (pixelbrowse skill) browser: its cdp backend can't self-provision a
# browser on macOS (auto-download is linux-x64 only), so point it at an installed
# Chromium-based one. Brave preferred, Chrome fallback. No-op elsewhere / on Linux.
if [ -z "${CHROME_PATH:-}" ]; then
  for _b in \
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    [ -x "$_b" ] && { export CHROME_PATH="$_b"; break; }
  done
  unset _b
fi
