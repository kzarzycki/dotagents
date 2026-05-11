Research a topic, optionally tied to an active work item.

Arguments: $ARGUMENTS (the research topic or question)

Follow these steps:

1. Determine research scope:
   - If there's an active item in state.md and the topic relates to it: item-specific research
   - Otherwise: standalone research

2. Check for existing research:
   - Item-specific: check items/<name>/research.md
   - Standalone: check .work/research/ for related files
   - If found: "Found existing research on [topic]. Build on it, or start fresh?"

3. Gather context for the research agent:
   - Read the research methodology from the flow skill's references/research.md
   - Read .work/brief.md
   - Read .work/standards/ (if any files exist)
   - If item-specific: read the item's ITEM.md and any existing research

4. Spawn research agent:
   - Inline ALL context into the prompt (methodology + brief + standards + item context + the research question)
   - Use subagent_type: "general-purpose"
   - Description: "Research: <topic summary>"

5. When agent returns:
   - Write findings to the appropriate location:
     - Item-specific: .work/items/<name>/research.md
     - Standalone: .work/research/<slug>.md (slugify the topic)
   - If item-specific: update ITEM.md status to "researching", add log entry, check progress box
   - Append to .work/log.md: "YYYY-MM-DD: Research completed — <topic>"

6. Present a brief summary of findings and recommendation to the user.
