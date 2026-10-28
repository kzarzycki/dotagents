# Limitations

Known edge cases left unfixed: what, where, the guard if any, what would make it matter, and its issue.

- The pkill/killall guard (`home/.claude/hooks/omnigent-only.py`, from #83) misses a wrapper option that takes a value (`sudo -u bob pkill -f gate`), the existing wrapper-parser ceiling, and trusts any pattern with a `/` or an 8+ character letter-and-digit token as the session's own. No guard. Matters if an agent adds `sudo -u` to a kill or uses a shared path. #83.
- An LFS repo whose `.pre-commit-config.yaml` opts into `post-checkout` keeps the template guard, so git-lfs's lock hooks (`post-checkout`, `post-commit`, `post-merge`) are not installed in its clones (`lib/postcheckout-guard.sh`, the `ponytail:` line). No guard; `git lfs update` says so. Matters if a repo uses both LFS file locking and a pre-commit post-checkout hook. #68.
- `skill_requirements` (`bin/dotagents`, the `ponytail:` line) reads `metadata.requires` line by line, so a flow mapping (`metadata: {requires: ..}`) is missed, and it takes each declared name as both the command and its mise tool. No guard. Matters if a skill writes its frontmatter in flow style or needs a tool whose mise name differs from its command. #97.
- The doctor's stale-copy scan (`check_stale_skill_copies` in `bin/dotagents`) prunes every directory named `tmp`, `.tmp` or `.cache`, so a project checked out below one (`~/tmp/proj/.claude/skills`) is not scanned. No guard. Matters if agents are run in projects under such a directory. #103.
