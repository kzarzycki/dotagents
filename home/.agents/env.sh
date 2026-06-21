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
