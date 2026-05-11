Initialize a Flow workspace for this project. This installs Flow into the project: .work/ directory, CLAUDE.md instructions, and a SessionStart hook for automatic context recovery.

Follow these steps:

1. Check if `.work/` already exists in the project root:
   - If yes: read state.md and brief.md, then ask "Found existing workspace for [project]. Continue with it, or start fresh?"
   - If starting fresh: confirm before deleting

2. Ask conversationally (not an interrogation — 2-3 questions max):
   - "What are you working on?" (project purpose, goals)
   - Follow up once for constraints, key decisions, or tech stack if not obvious
   - "Structured or creative tempo?" (explain: structured = research->plan->execute; creative = small iterations, frequent feedback)

3. Create the .work/ directory structure:
   ```
   .work/
     brief.md
     state.md
     log.md
     ideas.md
     standards/
     research/
     items/
   ```

4. Write brief.md with: project name, description, key constraints, tech decisions from the conversation.

5. Write state.md:
   ```markdown
   # Project State
   Tempo: structured | creative
   Active Item: none

   ## Items
   (none yet)
   ```

6. Write log.md:
   ```markdown
   # Work Log
   - YYYY-MM-DD: Project initialized. Tempo: [tempo].
   ```

7. Write ideas.md:
   ```markdown
   # Ideas
   Quick capture for things to revisit later.
   ```

8. Install Flow into the project's Claude Code configuration:

   a. **CLAUDE.md** — Append a Flow section to `CLAUDE.md` in the project root (create if it doesn't exist). If CLAUDE.md already has a Flow section, skip. Content to append:

   ```markdown

   ## Flow Workflow

   This project uses Flow for persistent workflow orchestration.
   Session state and behavioral instructions are injected automatically via SessionStart hook.
   ```

   b. **SessionStart hook** — Create `.claude/hooks/` directory. Copy the flow-bootstrap.sh script from the Flow skill's scripts/ directory into `.claude/hooks/flow-bootstrap.sh`. Make it executable.

   The script location in the Flow skill is at the path shown by:
   ```bash
   readlink -f ~/.claude/skills/flow/scripts/flow-bootstrap.sh
   ```

   c. **settings.json** — Create or update `.claude/settings.json` to register the hook. If the file exists, merge the hooks section carefully (don't overwrite existing hooks). If it doesn't exist, create it:

   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": ".claude/hooks/flow-bootstrap.sh",
               "timeout": 10
             }
           ]
         }
       ]
     }
   }
   ```

   If settings.json already exists with other hooks, add the SessionStart hook alongside existing ones.

9. Ask about git:
   - "Track .work/ in git (for team sharing) or add to .gitignore (solo/private)?"
   - If gitignore: add `.work/` to .gitignore
   - Note: `.claude/hooks/` and `.claude/settings.json` should always be tracked (they're project config)

10. If the conversation revealed a first work item, offer to create it:
    - "Sounds like '[name]' could be your first item. Create it?"

11. Confirm installation: "Flow installed. .work/ created, CLAUDE.md updated, session hook active. On every new session, project state will be injected automatically."
