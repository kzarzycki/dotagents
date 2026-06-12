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
