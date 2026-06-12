#!/usr/bin/env python3
"""SessionStart hook: inject configured skills' SKILL.md into context.

Reads ~/.claude/preload-skills.txt (one skill per line), resolves each to a
SKILL.md, and emits hookSpecificOutput.additionalContext with the contents.
Fail-safe: missing/unreadable skills are reported, never fatal; always exits 0.
"""
import glob
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".claude", "preload-skills.txt")
SOFT_LIMIT = 9500  # Claude Code persists hook output >10KB to a file instead of context


PLUGINS = os.path.join(HOME, ".claude", "plugins")


def resolve(entry):
    """Return (skill_name, skill_md_path) or None."""
    path = os.path.expanduser(entry)
    if os.path.sep in path:
        if os.path.isdir(path):
            path = os.path.join(path, "SKILL.md")
        return (os.path.basename(os.path.dirname(path)), path) if os.path.isfile(path) else None
    if ":" in entry:
        plugin, name = entry.split(":", 1)
        patterns = [
            os.path.join(PLUGINS, "marketplaces", "*", plugin, "skills", name, "SKILL.md"),
            os.path.join(PLUGINS, "cache", "*", plugin, "*", "skills", name, "SKILL.md"),
        ]
    else:
        name = entry
        patterns = [
            os.path.join(HOME, ".claude", "skills", name, "SKILL.md"),
            os.path.join(PLUGINS, "marketplaces", "*", "*", "skills", name, "SKILL.md"),
            os.path.join(PLUGINS, "cache", "*", "*", "*", "skills", name, "SKILL.md"),
        ]
    hits = [h for p in patterns for h in glob.glob(p)]
    if not hits:
        return None
    return (name, max(hits, key=os.path.getmtime))


def strip_description(content):
    """Drop frontmatter description: it's trigger-matching text, dead weight once preloaded."""
    m = re.match(r"^---\n(.*?\n)---\n", content, re.S)
    if not m:
        return content
    fm = re.sub(r"^description:.*\n(?:[ \t]+\S.*\n)*", "", m.group(1), flags=re.M)
    return "---\n" + fm + "---\n" + content[m.end():]


def main():
    loaded, missing, sections = [], [], []

    if not os.path.isfile(CONFIG):
        print(json.dumps({"systemMessage": f"preload-skills: no config at {CONFIG}, nothing loaded"}))
        return

    with open(CONFIG, encoding="utf-8") as f:
        entries = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]

    seen = set()
    for entry in entries:
        hit = resolve(entry)
        if not hit:
            missing.append(entry)
            continue
        name, skill_md = hit
        if name in seen:  # first entry wins - list preferred sources first
            continue
        seen.add(name)
        try:
            with open(skill_md, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            missing.append(f"{entry} ({e.strerror})")
            continue
        content = strip_description(content)
        base = os.path.dirname(skill_md)
        sections.append(
            f"=== PRELOADED SKILL: {name} ===\n"
            f"Base directory: {base}\n"
            f"(Resolve this skill's relative paths, e.g. references/ and assets/, "
            f"against the base directory. Read those files on demand - do not assume "
            f"their content.)\n\n{content}"
        )
        loaded.append(f"{name} ({len(content)} chars)")

    notes = []
    if loaded:
        notes.append("loaded: " + ", ".join(loaded))
    if missing:
        notes.append("NOT FOUND (skipped): " + ", ".join(missing))
    if not notes:
        notes.append("config has no entries")
    status = "preload-skills: " + "; ".join(notes)

    context = ""
    if sections:
        context = (
            "The following skills were preloaded by the user's SessionStart hook. "
            "Treat each as an active skill for this whole session - no Skill tool "
            "invocation needed.\n[" + status + "]\n\n" + "\n\n".join(sections)
        )
        if len(context) > SOFT_LIMIT:
            status += f" | WARNING: {len(context)} chars > {SOFT_LIMIT}; Claude Code may divert output >10KB to a file - trim the list"

    out = {"systemMessage": status}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": context}
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail-safe: never break session start
        print(json.dumps({"systemMessage": f"preload-skills hook error: {e}"}))
    sys.exit(0)
