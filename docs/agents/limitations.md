# Limitations

Known edge cases left unfixed: what, where, the guard if any, what would make it matter, and its issue.

- Template `post-checkout` guard may displace git-lfs's own hook in new clones (`lib/postcheckout-guard.sh`, from #29). No guard. Matters on a machine with git-lfs whose LFS repos rely on lock hooks. #68.
- With `ci: false`, any account's `Local check passed` comment for the head satisfies the local-check proof (the pack's `approvals.py`, `ran()`). No guard here; the owner's spec record and a trusted verifier pass still hold. Matters if a stranger comments on a PR whose check fails. kzarzycki/agent-skills#452.
