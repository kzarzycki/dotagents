#!/usr/bin/env python3
"""SessionStart hook: materialize + inject a project's toolkit (see
docs/proposals/toolkits.md, Option A / Layer 3).

Reads `.agents-toolkit` (walking up from cwd) to find the toolkit name, loads
`toolkits/<name>/{toolkit.json,CLAUDE.md}` from the dotagents checkout, and:

  - materializes gitignored project files (.claude/settings.local.json,
    .mcp.json, .codex/config.toml) when the toolkit definition's hash has
    changed since the last materialization (stamp file), and
  - always injects the toolkit CLAUDE.md fragment + preloaded skills as
    hookSpecificOutput.additionalContext (skill resolution copied from
    preload-skills.py, which stays untouched).

Fail-safe: any exception -> systemMessage, exit 0. Never blocks session start.
"""
import glob
import hashlib
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
TOOLKITS_DIR = os.environ.get("AGENTS_TOOLKITS_DIR", os.path.join(HOME, "dev", "dotagents", "toolkits"))
SKILLS_POOL = os.path.join(TOOLKITS_DIR, "_skills")
REGISTRY_PATH = os.path.join(HOME, ".agents", "mcp-registry.json")
REGISTRY_LOCAL_PATH = os.path.join(HOME, ".agents", "mcp-registry.local.json")
USER_SETTINGS_PATH = os.path.join(HOME, ".claude", "settings.json")
SOFT_LIMIT = 9500  # Claude Code persists hook output >10KB to a file instead of context

PLUGINS = os.path.join(HOME, ".claude", "plugins")


# --- skill resolution, copied from preload-skills.py (kept in sync by hand) ---

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


# --- registry local overrides ---

def deep_merge_registry(base, local):
    """Deep-merge `local` server defs over `base`, per server. Nested dicts
    (e.g. headers, env) merge key-by-key; other values are replaced."""
    merged = dict(base)
    for name, override in local.items():
        if name in merged and isinstance(merged[name], dict) and isinstance(override, dict):
            def merge_dicts(b, o):
                r = dict(b)
                for k, v in o.items():
                    if k in r and isinstance(r[k], dict) and isinstance(v, dict):
                        r[k] = merge_dicts(r[k], v)
                    else:
                        r[k] = v
                return r
            merged[name] = merge_dicts(merged[name], override)
        else:
            merged[name] = override
    return merged


ENV_PLACEHOLDER_RE = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}|\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env_placeholders(value):
    """Expand ${env:VAR} / ${VAR} from os.environ. Used only for codex's
    config.toml, which codex does not expand itself. Left untouched for
    .mcp.json - Claude Code expands ${VAR} natively."""
    if isinstance(value, str):
        def sub(m):
            var = m.group(1) or m.group(2)
            return os.environ.get(var, m.group(0))
        return ENV_PLACEHOLDER_RE.sub(sub, value)
    if isinstance(value, list):
        return [expand_env_placeholders(v) for v in value]
    if isinstance(value, dict):
        return {k: expand_env_placeholders(v) for k, v in value.items()}
    return value


# --- toolkit lookup ---

def find_toolkit_file(start):
    """Walk up from `start` looking for .agents-toolkit. Return its dir, or None."""
    d = os.path.abspath(start)
    while True:
        candidate = os.path.join(d, ".agents-toolkit")
        if os.path.isfile(candidate):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_toolkit(name):
    tdir = os.path.join(TOOLKITS_DIR, name)
    tjson_path = os.path.join(tdir, "toolkit.json")
    tmd_path = os.path.join(tdir, "CLAUDE.md")
    if not os.path.isdir(tdir):
        return None
    with open(tjson_path, encoding="utf-8") as f:
        tjson_raw = f.read()
    tjson = json.loads(tjson_raw)
    tmd = ""
    if os.path.isfile(tmd_path):
        with open(tmd_path, encoding="utf-8") as f:
            tmd = f.read()
    return tdir, tjson_raw, tjson, tmd_path, tmd


# --- materialization ---

def compute_stamp(tjson_raw, tmd, registry_raw):
    h = hashlib.sha256()
    h.update(tjson_raw.encode("utf-8"))
    h.update(tmd.encode("utf-8"))
    h.update(registry_raw.encode("utf-8"))
    return h.hexdigest()


def append_git_exclude(project_root, entries):
    git_dir = os.path.join(project_root, ".git")
    if not os.path.isdir(git_dir):
        return
    exclude_path = os.path.join(git_dir, "info", "exclude")
    os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
    existing = ""
    if os.path.isfile(exclude_path):
        with open(exclude_path, encoding="utf-8") as f:
            existing = f.read()
    existing_lines = set(existing.splitlines())
    to_add = [e for e in entries if e not in existing_lines]
    if not to_add:
        return
    with open(exclude_path, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        for e in to_add:
            f.write(e + "\n")


def git_tracks(project_root, relpath):
    import subprocess
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relpath],
            cwd=project_root, capture_output=True, timeout=5,
        )
        return out.returncode == 0
    except Exception:
        return False


def merge_settings_local(project_root, toolkit_plugins, claude_in_chrome=False):
    path = os.path.join(project_root, ".claude", "settings.local.json")
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    if toolkit_plugins is not None:
        user_enabled = {}
        if os.path.isfile(USER_SETTINGS_PATH):
            try:
                with open(USER_SETTINGS_PATH, encoding="utf-8") as f:
                    user_enabled = json.load(f).get("enabledPlugins", {})
            except Exception:
                user_enabled = {}

        enabled = {k: False for k in user_enabled}
        for p in toolkit_plugins:
            enabled[p] = True
        data["enabledPlugins"] = enabled

    if claude_in_chrome:
        data["claudeInChromeDefaultEnabled"] = True
    else:
        data.pop("claudeInChromeDefaultEnabled", None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    return path


def write_mcp_json(project_root, mcp_names, registry):
    missing = [n for n in mcp_names if n not in registry]
    present = {n: registry[n] for n in mcp_names if n in registry}
    path = os.path.join(project_root, ".mcp.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": present}, f, indent=2)
        f.write("\n")
    return path, missing


def toml_escape(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_value(v):
    if isinstance(v, str):
        return toml_escape(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise ValueError(f"unsupported TOML value: {v!r}")


def sync_skills(project_root, skill_names):
    """Symlink toolkits/_skills/<name> into <project>/.claude/skills/<name> for
    each wanted name; remove symlinks (into the pool) for names no longer
    wanted. Never touch non-symlink entries."""
    skills_dir = os.path.join(project_root, ".claude", "skills")
    os.makedirs(skills_dir, exist_ok=True)
    wanted = set(skill_names)
    pool_real = os.path.realpath(SKILLS_POOL)
    for entry in os.listdir(skills_dir):
        link_path = os.path.join(skills_dir, entry)
        if os.path.islink(link_path) and os.path.dirname(os.path.realpath(link_path)) == pool_real:
            if entry not in wanted:
                os.remove(link_path)
    for name in wanted:
        link_path = os.path.join(skills_dir, name)
        if os.path.exists(link_path) or os.path.islink(link_path):
            continue  # already present (symlink we want, or a real dir - leave it)
        src = os.path.join(SKILLS_POOL, name)
        if os.path.isdir(src):
            os.symlink(src, link_path)


def write_codex_config(project_root, mcp_names, registry):
    lines = ["# generated by dotagents toolkit hook", ""]
    for name in mcp_names:
        if name not in registry:
            continue
        server = expand_env_placeholders(registry[name])
        lines.append(f"[mcp_servers.{name}]")
        for key in ("command", "args"):
            if key in server:
                lines.append(f"{key} = {toml_value(server[key])}")
        if "env" in server and server["env"]:
            lines.append(f"env = {toml_value(server['env'])}")
        lines.append("")
    codex_dir = os.path.join(project_root, ".codex")
    os.makedirs(codex_dir, exist_ok=True)
    path = os.path.join(codex_dir, "config.toml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


def materialize(project_root, name, tjson, tmd_path, tmd, registry, stamp):
    plugins = tjson.get("plugins", [])
    mcp_names = tjson.get("mcp", [])
    skill_names = tjson.get("skills") or []

    if plugins is not None or tjson.get("claudeInChrome"):
        merge_settings_local(project_root, plugins, tjson.get("claudeInChrome", False))

    mcp_path, missing_mcp = write_mcp_json(project_root, mcp_names, registry)
    write_codex_config(project_root, mcp_names, registry)
    sync_skills(project_root, skill_names)

    exclude_entries = [".mcp.json", ".claude/.toolkit-stamp", ".codex/", ".claude/skills/"]
    if not git_tracks(project_root, os.path.join(".claude", "settings.local.json")):
        exclude_entries.append(".claude/settings.local.json")
    append_git_exclude(project_root, exclude_entries)

    stamp_path = os.path.join(project_root, ".claude", ".toolkit-stamp")
    os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
    with open(stamp_path, "w", encoding="utf-8") as f:
        f.write(stamp)

    return missing_mcp


def build_additional_context(name, tmd, preload_entries):
    loaded, missing, sections = [], [], []
    seen = set()
    for entry in preload_entries:
        hit = resolve(entry)
        if not hit:
            missing.append(entry)
            continue
        skill_name, skill_md = hit
        if skill_name in seen:
            continue
        seen.add(skill_name)
        try:
            with open(skill_md, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            missing.append(f"{entry} ({e.strerror})")
            continue
        content = strip_description(content)
        base = os.path.dirname(skill_md)
        sections.append(
            f"=== PRELOADED SKILL: {skill_name} ===\n"
            f"Base directory: {base}\n"
            f"(Resolve this skill's relative paths, e.g. references/ and assets/, "
            f"against the base directory. Read those files on demand - do not assume "
            f"their content.)\n\n{content}"
        )
        loaded.append(f"{skill_name} ({len(content)} chars)")

    context = f"TOOLKIT: {name}\n\n{tmd}"
    if sections:
        context += (
            "\n\nThe following skills were preloaded by the toolkit hook. "
            "Treat each as an active skill for this whole session - no Skill tool "
            "invocation needed.\n\n" + "\n\n".join(sections)
        )
    # Over the diversion threshold the whole payload lands in a file, not
    # context - worse than truncation. Trim the largest sections to fit,
    # leaving a pointer to read the rest on demand.
    for _ in range(len(sections)):  # bounded: each pass shrinks one section
        if len(context) <= SOFT_LIMIT:
            break
        i = max(range(len(sections)), key=lambda j: len(sections[j]))
        path_line = sections[i].splitlines()[1]  # "Base directory: ..."
        note = (
            f"\n[... truncated by toolkit hook to fit context budget - "
            f"read SKILL.md under the {path_line} for the rest]"
        )
        keep = len(sections[i]) - (len(context) - SOFT_LIMIT) - len(note)
        if keep < 500:  # too small to be useful truncated
            break
        sections[i] = sections[i][:keep] + note
        context = f"TOOLKIT: {name}\n\n{tmd}" + (
            "\n\nThe following skills were preloaded by the toolkit hook. "
            "Treat each as an active skill for this whole session - no Skill tool "
            "invocation needed.\n\n" + "\n\n".join(sections)
        )
    return context, loaded, missing


def main():
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except Exception:
        hook_input = {}
    cwd = hook_input.get("cwd") or os.getcwd()

    project_root = find_toolkit_file(cwd)
    if project_root:
        with open(os.path.join(project_root, ".agents-toolkit"), encoding="utf-8") as f:
            name = f.read().strip()
    else:
        name = "base"  # unbound dir: no project to materialize into, inject base context only

    loaded_toolkit = load_toolkit(name)
    if not loaded_toolkit:
        print(json.dumps({"systemMessage": f"toolkit: error - '{name}' not found under {TOOLKITS_DIR}"}))
        return
    _tdir, tjson_raw, tjson, tmd_path, tmd = loaded_toolkit

    registry = {}
    registry_raw = ""
    if os.path.isfile(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry_raw = f.read()
        try:
            registry = json.loads(registry_raw)
        except Exception:
            registry = {}

    registry_local_raw = ""
    if os.path.isfile(REGISTRY_LOCAL_PATH):
        with open(REGISTRY_LOCAL_PATH, encoding="utf-8") as f:
            registry_local_raw = f.read()
        try:
            registry = deep_merge_registry(registry, json.loads(registry_local_raw))
        except Exception:
            pass
    registry_raw += registry_local_raw

    materialized_note = "n/a (unbound dir, no project to materialize into)"
    missing_mcp = []
    if project_root:
        stamp = compute_stamp(tjson_raw, tmd, registry_raw)
        stamp_path = os.path.join(project_root, ".claude", ".toolkit-stamp")
        old_stamp = None
        if os.path.isfile(stamp_path):
            with open(stamp_path, encoding="utf-8") as f:
                old_stamp = f.read().strip()

        materialized_note = "fresh (stamp unchanged)"
        if stamp != old_stamp:
            missing_mcp = materialize(project_root, name, tjson, tmd_path, tmd, registry, stamp)
            materialized_note = "materialized"

    context, loaded_skills, missing_skills = build_additional_context(
        name, tmd, tjson.get("preloadSkills", [])
    )

    notes = [f"toolkit: {name}", materialized_note]
    if loaded_skills:
        notes.append("skills loaded: " + ", ".join(loaded_skills))
    if missing_skills:
        notes.append("skills NOT FOUND: " + ", ".join(missing_skills))
    if missing_mcp:
        notes.append("mcp NOT in registry (skipped): " + ", ".join(missing_mcp))
    status = " | ".join(notes)

    if len(context) > SOFT_LIMIT:
        status += f" | WARNING: {len(context)} chars > {SOFT_LIMIT}; Claude Code may divert output >10KB to a file"

    out = {
        "systemMessage": status,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context},
    }
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail-safe: never break session start
        print(json.dumps({"systemMessage": f"toolkit hook error: {e}"}))
    sys.exit(0)
