import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_agent_layer_is_not_part_of_home_payload():
    forbidden = (
        "apm.yml",
        "apm.lock.yaml",
        "mise.toml",
        ".apm",
        ".agents/skills",
        ".claude/skills",
    )
    for relative in forbidden:
        assert not (ROOT / "home" / relative).exists(), relative


def test_project_instruction_source_records_scope_boundary():
    source = ROOT / ".apm/instructions/project.instructions.md"
    text = source.read_text()
    assert 'applyTo: "**"' in text
    assert "`home/` contains user- and machine-scope configuration" in text
    assert "Repository-root agent configuration serves dotagents development" in text


def test_installed_user_instructions_do_not_claim_project_ownership():
    text = (ROOT / "home/.agents/AGENTS.md").read_text()
    assert "apm.lock.yaml" not in text
    assert "agent-skills/engineering" not in text


def test_installed_user_instructions_match_stage3_base_byte_for_byte():
    current = (ROOT / "home/.agents/AGENTS.md").read_bytes()
    base = subprocess.check_output(
        ["git", "show", "ce9a031:home/.agents/AGENTS.md"],
        cwd=ROOT,
    )
    assert hashlib.sha256(current).hexdigest() == hashlib.sha256(base).hexdigest()
    assert current == base
