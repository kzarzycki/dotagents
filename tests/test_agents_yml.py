import os
import subprocess
from pathlib import Path

from test_install_subsets import make_checkout, run_install

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "home/.agents/agents.yml"


def resolve(cfg, role, key, **attrs):
    """Hand-walk of the spec: top level, then the role, then the matched by_<attr> entry; deepest wins."""
    value = cfg.get(key)
    node = cfg.get(role) or {}
    if key in node:
        value = node[key]
    for attr, label in attrs.items():
        sub = (node.get(f"by_{attr}") or {}).get(label)
        if sub and key in sub:
            value = sub[key]
    return value


def mini_yaml(text):
    """Nested `key: value` / `key:` maps only: enough for this file where PyYAML is not installed (CI)."""
    root, stack = {}, [(-1, {})]
    stack[0] = (-1, root)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        while stack[-1][0] >= indent:
            stack.pop()
        value = value.strip()
        if value:
            stack[-1][1][key] = value
        else:
            child = {}
            stack[-1][1][key] = child
            stack.append((indent, child))
    return root


def load():
    text = STARTER.read_text()
    try:
        import yaml
    except ImportError:
        return mini_yaml(text)
    return yaml.safe_load(text)


def test_starter_file_parses_with_known_shape():
    cfg = load()
    assert set(cfg) <= {"effort", "lead", "worker", "verifier", "helper"}
    for role in ("lead", "worker", "verifier", "helper"):
        assert isinstance(cfg.get(role, {}), dict)


def test_starter_values_resolve_as_the_owner_chose():
    cfg = load()
    assert resolve(cfg, "verifier", "route") == "codex"
    assert resolve(cfg, "verifier", "model", risk="low") == "gpt-6.1-terra"
    for risk in ("medium", "high", None):
        attrs = {"risk": risk} if risk else {}
        assert resolve(cfg, "verifier", "model", **attrs) == "gpt-6.2-sol"
    assert resolve(cfg, "verifier", "effort", risk="low") == "medium"
    assert resolve(cfg, "lead", "model", size="XS") == "sonnet"
    # worker and helper are left to the harness
    assert resolve(cfg, "worker", "model") is None
    assert resolve(cfg, "helper", "model") is None


def test_install_links_starter_into_home_agents(tmp_path):
    repo, home = make_checkout(tmp_path)
    result = run_install(repo, home)
    assert result.returncode == 0, result.stdout + result.stderr
    target = home / ".agents/agents.yml"
    assert target.is_symlink()
    assert target.resolve() == (repo / "home/.agents/agents.yml").resolve()
