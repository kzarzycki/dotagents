# Limitations

Known edge cases left unfixed: what, where, the guard if any, what would make it matter, and its issue.

- Template `post-checkout` guard may displace git-lfs's own hook in new clones (`lib/postcheckout-guard.sh`, from #29). No guard. Matters on a machine with git-lfs whose LFS repos rely on lock hooks. #68.
- The pkill/killall guard (`home/.claude/hooks/omnigent-only.py`, from #83) misses a wrapper option that takes a value (`sudo -u bob pkill -f gate`), the existing wrapper-parser ceiling, and trusts any pattern with a `/` or an 8+ character letter-and-digit token as the session's own. No guard. Matters if an agent adds `sudo -u` to a kill or uses a shared path. #83.
