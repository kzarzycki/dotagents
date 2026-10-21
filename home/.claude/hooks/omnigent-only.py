#!/usr/bin/env python3
"""PreToolUse hook on Bash: deny an agent CLI launched outside Omnigent.

Separate agents (worker, reviewer, lead) run as Omnigent sessions, which keeps
them visible, resumable and on the owner's board. A bare `claude -p`,
`codex exec`, `omp`, `gemini -p` or `agy -p` from a tool call bypasses that.
Only command words count: `grep claude`, paths and `claude --version` pass.
Processes not started by a tool call (systemd units) never reach this hook.

Cases: tests/test_omnigent_only.py.
"""
import json
import os
import re
import shlex
import sys

WRAPPERS = {"env", "exec", "command", "nohup", "time", "sudo", "nice", "setsid", "timeout", "xargs", "stdbuf"}
SHELLS = {"sh", "bash", "zsh", "dash"}
SEPARATORS = set("();|&")
# omp commands that start no agent: the audited-upgrade gate (docs/knowledge/omp.md) and housekeeping.
OMP_TOOLS = {"--version", "-v", "--help", "-h", "--upgrade-status", "--upgrade-check", "--upgrade-apply",
             "safe-update", "config", "plugin", "install", "models", "completions", "login", "gc"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "{", "!"}


def agent_launch(name, args):
    if name == "claude":
        return bool({"-p", "--print"} & set(args))
    if name == "codex":
        return bool({"exec", "e"} & set(args))
    if name == "omp":
        return not args or args[0] not in OMP_TOOLS
    if name in ("gemini", "agy"):
        return bool({"-p", "--print", "--prompt", "-i", "--prompt-interactive"} & set(args))
    return False


def drop_heredoc_bodies(cmd):
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        tags = re.findall(r"(?<!<)<<(?!<)-?\s*['\"]?([\w.-]+)", lines[i])
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1
    return ";".join(out)


def launches(cmd):
    """Return the first agent-launching command word in a shell string, or None."""
    lexer = shlex.shlex(drop_heredoc_bodies(cmd).replace("`", ";"), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # shlex would end the whole command at the first #; a comment is a harmless word here
    try:
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes: let the shell report it
        return None
    segment = []
    for tok in tokens + [";"]:
        if tok and set(tok) <= SEPARATORS:
            hit = check_segment(segment)
            if hit:
                return hit
            segment = []
        else:
            segment.append(tok)
    return None


def check_segment(words):
    # Skip assignments, shell keywords (`do`, `then`) and wrappers with their flags (`env -i`, `timeout 60`).
    # ponytail: a wrapper flag that takes a value (`sudo -u bob`) hides the command.
    while words and (re.match(r"^\w+=", words[0]) or words[0] in WRAPPERS or words[0] in KEYWORDS):
        wrapper = words[0] in WRAPPERS
        words = words[1:]
        while wrapper and words and (words[0].startswith("-") or re.match(r"^\d+[smhd]?$", words[0])):
            words = words[1:]
    if not words:
        return None
    name, args = os.path.basename(words[0]), words[1:]
    if name in SHELLS:
        for flag, script in zip(args, args[1:]):
            if flag.startswith("-") and "c" in flag:
                return launches(script)
        return None
    return " ".join(words[:2]) if agent_launch(name, args) else None


def main():
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    hit = launches(command)
    if hit:
        print(f"Denied `{hit}`: separate agents run as Omnigent sessions, never as a bare CLI call. "
              "Use the orchestrating-agents skill: `python3 <skill>/scripts/omnigent_agent.py run|start ...` "
              "(backends/omnigent.md); for an in-process helper use the Agent tool.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
