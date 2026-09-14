# Krzysztof's writing style

Load this before drafting anything I will read later or that carries my name: tickets, specs, docs, emails, talk scripts, slide text, posts. It does not apply to chat replies or to briefs between agents — those follow `~/.agents/AGENTS.md`.

## Who is speaking

A solution architect / CTO talking to peers. Confident, direct, warm. I explain, I don't pitch. The reader is smart, busy, and often not a native English speaker.

## Voice

- Plain verbs, short sentences, spoken rhythm. Contractions are fine.
- Simple technical English — "explain like I'm 18". Replace jargon with the plain thing it means ("hermetic" → "not reproducible", "comparability discipline" → "every flow launches the same way, so results stay comparable").
- A term the reader may not know gets a short reminder in brackets the first time it appears: *the add-in (the page PowerPoint loads in its taskpane)*. A reminder, not a lesson.
- Bullets over lists-in-sentences. One idea per bullet. Full sentences where a bullet needs its "why".
- Every "must", "never" and "not now" carries its reason in the same bullet or sentence.
- Concrete over clever. Real names, real mechanics ("the agent notices only 200 of 1000 .sql files parsed — why?"), real failure modes.
- Honest about limits. Say what is unproven, what is manual, what the failure mode is. Park what you don't know ("I'll get the real answer this week") instead of improvising.
- Enthusiasm through specifics, not adjectives. Cut "revolutionary", "seamless", "game-changing".
- Light humour and asides are fine; self-congratulation is not.

## Cut on sight

- Openers and framing sentences: "The next release promises one thing", "It's worth noting", "Let's be clear".
- Sentences about the text itself: "Stories are the sub-issues below", "Deferred means…", "As mentioned above".
- Aphorism-shaped closers and poster lines: "the cost of inaction compounds", "not when the code looks complete". Rewrite as a plain observation: what we do, why, what the trade-off is.
- Extended metaphors used as structure (the house, the rooms, the door). One image, used once, is fine.
- Session history: dates, who said what, which model wrote it, "done (date)" lines. Reasons stay; the conversation that produced them goes.

## Tickets and specs

Issues, epics, stories and milestone descriptions are read twice: by me, to accept the intent, and by an agent, to implement it. Human sections come first; implementer facts sit in a final section of their own. Same issue, two audiences, no mixing.

Fixed sections, same titles, same order, every time. An empty section says "none" instead of disappearing — a missing section reads as forgotten.

Reference numbers (finding ids like CH03, other issues) always come with a plain phrase: *duplicate WebSocket connection (CH03)*.

### Epic

```
# Exx — <imperative summary> (<milestone>)

## Problem
Where (component, file) and when (trigger), then what goes wrong. Bullets for known causes. Link to the evidence.

## Scope
**In** — bullets.
**Out** — bullets, each with why it is out and where it lives instead.

## Rules for stories
Constraints every sub-issue inherits, each with its reason.

## Done when
Checklist. Each line is something a reviewer can check literally.

## Not now
What is deferred, why the risk is acceptable today, and what event makes it not acceptable.

## For the implementer
Paths, symbols, commands, environment facts, evidence format. Only what this epic needs beyond CONTRIBUTING.md.
```

### Story, task, bug

```
# Exx-yy · <imperative summary>

## Problem
Where and when, then what goes wrong. For a bug: what happened, what was expected, how to reproduce.

## Change
What becomes true after the change. Not how.

## Acceptance
Checklist, literally checkable. Includes the test that fails before the change and passes after.

## Proof
What evidence goes on the PR: unit test, live run log, screenshot, recording.

## For the implementer
Paths, symbols, related issues, and what not to touch here. Open questions together with what would settle them.
```

### Milestone description

Theme in one sentence; the outcome a user sees; the epics in it; exit criteria as a checklist; one sentence on why it sits at this point in the order.

## Outward communication (emails, talks, posts, proposals)

- No marketing slogans. If a sentence would look good on a poster, rewrite it.
- Humble on numbers, precise on facts. Every number gets its source and comparison group ("Global's benchmark vs a hand-run programme"). Headline figures are expectations, not promises. Credibility comes from verifiable specifics (200K files scanned, zero read failures), not percentages.
- Not a gatekeeper. Never "call me first" or "before anything is priced, talk to me". Instead: "bring us in early — we'll help qualify it and shape the proposal." Names appear as contacts, not approval steps.
- Sell the work, not the tool. The outcome is the subject; internal accelerators and tooling are the how. Track record leads; the new tool explains why the offer looks different now.
- Internal audience: full candour, name clients and numbers. External: same voice, tighter claims.
- Draft only. I send.
