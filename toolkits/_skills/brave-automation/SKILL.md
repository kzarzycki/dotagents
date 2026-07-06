---
name: brave-automation
description: "Drive the user's logged-in Brave browser via playwright-cli over CDP. Use when the Chrome extension is down or a task needs existing logged-in sessions (Google etc.)."
---

# Brave automation (playwright-cli over CDP)

Drive the user's real, logged-in Brave session. Use when sites need existing login state (Google, etc.). The Claude-in-Chrome MCP extension uses the live session too - prefer it if connected; this is the fallback when it isn't.

## Attach

Brave runs with `--remote-debugging-port=9222`.
```
playwright-cli -s=brave attach --cdp=http://127.0.0.1:9222
```

**Gotcha:** `connectOverCDP` enumerates ALL targets and times out (30s) when too many tabs/iframes are open (~200 fails; that was the blocker - it connects at the ws layer then hangs). Keep it under ~40. Check first:
```
curl -s http://127.0.0.1:9222/json/list | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
```
If too high, ask the user to close tabs.

## Act (all commands take `-s=brave`)

- `tab-new <url>`, `tab-list`, `goto <url>`
- `snapshot` -> element refs (e.g. `e149`); then `click <ref>`, `fill <ref> <text>`, `check <ref>`, `select <ref> <val>`
- `eval "() => ({url:location.href})"` for page state
- `screenshot` -> saves a PNG you can Read
- `upload <file>` for file inputs

## Notes

- Refs (`e194` etc.) come from the latest `snapshot`; re-snapshot after navigation.
- Downloads are captured to `.playwright-cli/`, not `~/Downloads`.
- Deep reference: `~/dev/kb/personal/wiki/tools/brave-playwright-automation.md`.
