Execute a quick task without the full item/research/plan ceremony.

Arguments: $ARGUMENTS (the task to do)

Follow these steps:

1. If .work/ doesn't exist, create a minimal one:
   - .work/log.md
   - .work/ideas.md
   (Skip the full init conversation — this is quick mode)

2. Execute the task directly — no agent delegation, no research/plan cycle.
   Just do the work in the main context.

3. After completion, append to .work/log.md:
   - "YYYY-MM-DD: Quick — <brief description of what was done>"

4. If the work reveals follow-ups or larger scope:
   - Capture them in .work/ideas.md
   - Mention to the user: "This might be worth a full item. Captured in ideas for now."
