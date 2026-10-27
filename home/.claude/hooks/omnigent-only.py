#!/usr/bin/env python3
"""PreToolUse hook on Bash: deny an agent CLI launched outside Omnigent, and a
kill by a name shared between agents.

Separate agents (worker, reviewer, lead) run as Omnigent sessions, which keeps
them visible, resumable and on the owner's board. A bare `claude -p`,
`codex exec`, `omp`, `gemini -p` or `agy -p` from a tool call bypasses that.
Only command words count: `grep claude`, paths and `claude --version` pass.
Processes not started by a tool call (systemd units) never reach this hook.

Agents on one machine share process names, so `pkill -f 'local-ci --record'` or
`killall java` stops every other agent's matching run. `killall` is always
denied. `pkill` passes when it is scoped by `-P <ppid>` or `-g <pgid>`, or when
its pattern contains a `/`, which only a path the session owns (a worktree's
`run.sh`) matches.

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
# pkill options that take a value in the next word.
PKILL_VALUE = set("PgsStuUGn")
KILL = "kill by name"
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "{", "!"}


def agent_launch(name, args):
    if name == "claude":
        return bool({"-p", "--print"} & set(args))
    if name == "codex":
        return bool({"exec", "e", "review"} & set(args))
    if name == "omp":
        return not args or args[0] not in OMP_TOOLS
    if name in ("gemini", "agy"):
        return bool({"-p", "--print", "--prompt", "-i", "--prompt-interactive"} & set(args))
    return False


def shared_kill(name, args):
    """True for `killall`, and for a `pkill` whose pattern is a bare name or command line."""
    if name == "killall":
        return True
    if name != "pkill":
        return False
    pattern, i = None, 0
    while i < len(args):
        arg = args[i]
        i += 1
        if re.match(r"^-[A-Z0-9]{2,}$", arg):  # a signal: -9, -TERM, -SIGPIPE
            continue
        if arg.startswith("--"):
            if arg.split("=")[0] in ("--parent", "--pgroup"):
                return False
            i += arg in ("--session", "--terminal", "--euid", "--uid", "--group", "--signal", "--newest")
        elif arg.startswith("-") and len(arg) > 1:
            if re.search(r"[Pg]", arg[1:]):  # -P <ppid>, -g <pgid>, also bundled (-fP 12) or attached (-P12)
                return False
            i += arg[-1] in PKILL_VALUE
        elif pattern is None:
            pattern = arg
    return pattern is not None and "/" not in pattern


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
    return out


def launches(cmd):
    """Return the first agent-launching command word in a shell string, or None."""
    lines = drop_heredoc_bodies(cmd)
    # A comment is read as harmless words (shlex would end the whole command at
    # the first #). If one holds an apostrophe (`# don't`), retry without comments.
    for text in (lines, [re.sub(r"(^|[\s;&|])#.*", r"\1", line) for line in lines]):
        lexer = shlex.shlex(";".join(text).replace("`", ";"), posix=True, punctuation_chars=True)
        lexer.whitespace_split, lexer.commenters = True, ""
        try:
            tokens = list(lexer)
            break
        except ValueError:
            tokens = None
    if tokens is None:  # unbalanced quotes: let the shell report it
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
        if words[0] == "command" and words[1:2] in (["-v"], ["-V"]):  # a lookup, not a run
            return None
        wrapper = words[0] in WRAPPERS
        words = words[1:]
        while wrapper and words and (words[0].startswith("-") or re.match(r"^\d+[smhd]?$", words[0])):
            words = words[1:]
    if not words:
        return None
    name, args = os.path.basename(words[0]), words[1:]
    if "--" in args:  # what follows is another program's argv (`claude mcp add x -- cmd -p 1`)
        args = args[:args.index("--")]
    if name in SHELLS:
        for flag, script in zip(args, args[1:]):
            if flag.startswith("-") and "c" in flag:
                return launches(script)
        return None
    if shared_kill(name, args):
        return KILL
    return " ".join(words[:2]) if agent_launch(name, args) else None


def main():
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    hit = launches(command)
    if hit == KILL:
        print("Denied pkill/killall on a name: other agents on this machine run the same command lines, so "
              "it stops their runs too. Save the pid at launch (`cmd & echo $! > run.pid`) and stop its "
              "process group (`kill -TERM -- -<pgid>`, `pkill -g <pgid>`), or use `pkill -P <pid>`; "
              "a `pkill -f` pattern passes only with a path of your own in it.", file=sys.stderr)
        sys.exit(2)
    if hit:
        print(f"Denied `{hit}`: separate agents run as Omnigent sessions, never as a bare CLI call. "
              "Use the orchestrating-agents skill: `python3 <skill>/scripts/omnigent_agent.py run|start ...` "
              "(backends/omnigent.md); for an in-process helper use the Agent tool.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
