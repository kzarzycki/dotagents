FLOWBENCH TOOLKIT ACTIVE (toolkit: flowbench)

Applies to the flowbench pair of repos: `flowbench` (engine) and
`flowbench-scenarios` (scenario packs).

- `flowbench-scenarios` depends on `flowbench` as an editable path dependency
  (`../flowbench`). Engine PRs merge before the paired scenarios PRs that need
  the new engine behavior.
- Conventional commits.
- Python 3.12+, `uv` for envs/deps, `pytest` for tests, `ruff` for lint/format.
- Run outputs live OUTSIDE both repos, in sibling dirs (e.g. `../flowbench-runs`)
  — never commit run artifacts into either repo.
- Live agent runs require omnigent. `ANTHROPIC_API_KEY` must be UNSET in this
  environment — it's a subscription-billing guard; live runs go through the
  subscription, not metered API key billing.
