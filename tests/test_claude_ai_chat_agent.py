"""The claude-ai-chat agent config and its prompt refresh script."""

import subprocess
import sys

from test_install_subsets import ROOT

AGENTS = ROOT / "patches/omnigent/agents"
PAGE = """\
---
title: t
---

## November 9, 2026

```text wrap
<a>
Today is {{currentDateTime}}.
  indented line

<example>
```

```text wrap
tail
</a>
```

## October 27, 2026

```text wrap
old
```
"""


def prompt_of(config_text):
    """The `prompt: |` block, de-indented (pytest's env has no YAML parser)."""
    body = config_text.split("\nprompt: |\n", 1)[1]
    return "".join(l[2:] if l.strip() else l for l in body.splitlines(True))


def test_committed_config_is_a_filled_prompt():
    text = (AGENTS / "claude-ai-chat/config.yaml").read_text()
    assert "model: claude-opus-5-5" in text
    prompt = prompt_of(text)
    assert "{{" not in prompt and "```" not in prompt


def test_refresh_takes_newest_section_and_joins_the_split_blocks(tmp_path):
    work = tmp_path / "agents"
    (work / "claude-ai-chat").mkdir(parents=True)
    script = work / "refresh-claude-ai-chat"
    script.write_text((AGENTS / "refresh-claude-ai-chat").read_text())
    cfg = work / "claude-ai-chat/config.yaml"
    cfg.write_text("name: x\nprompt: |\n  stale\n")
    page = tmp_path / "page.md"
    page.write_text(PAGE)
    subprocess.run([sys.executable, str(script), "--file", str(page), "--date", "Monday, May 4, 2026"], check=True)
    text = cfg.read_text()
    assert text.startswith("name: x\nprompt: |\n")
    assert prompt_of(text) == "<a>\nToday is Monday, May 4, 2026.\n  indented line\n\n<example>\ntail\n</a>\n"
