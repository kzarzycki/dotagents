# Limitations

Known edge cases left unfixed: what, where, the guard if any, what would make it matter, and its issue.

- Template `post-checkout` guard may displace git-lfs's own hook in new clones (`lib/postcheckout-guard.sh`, from #29). No guard. Matters on a machine with git-lfs whose LFS repos rely on lock hooks. #68.
