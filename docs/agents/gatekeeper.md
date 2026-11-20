# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
loop:
  gate: mise run check
  delegate: all
risk:
  verifier: true
```
