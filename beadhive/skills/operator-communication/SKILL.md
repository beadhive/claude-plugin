---
name: operator-communication
description: >-
  Use at an operator-facing decision point or when reporting a Beadhive status: make choices and
  lifecycle state clear, name every bead with its title and id, and distinguish a blocking
  AskUserQuestion from a recommendation that can proceed by silence.
---

# Operator-facing decisions and status

Follow the canonical [operator-facing communication contract](../../OPERATOR-COMMUNICATION.md).
This skill is the detailed home for the two structures below. It applies to any seat that speaks to
the operator, including subagents; an output style does not reach those subagents.

## Decision ask

Use this structure only when the operator's answer changes the next action:

1. Start with **Decision requested** so the request is unmistakable.
2. Ask one direct question that says what must be decided.
3. Give each option and its concrete impact: what changes, costs, risks, or becomes unavailable.
4. Mark **Recommendation:** explicitly and give the reason.
5. Say whether work is blocked until the decision or will proceed by default.

Use the built-in `AskUserQuestion` tool for a genuine, mutually exclusive multiple-choice fork
that cannot safely proceed without the operator's answer. Use prose when making a recommendation
that the operator can accept by silence; state the default action and when it will happen. Do not
bury either kind of ask inside a status paragraph.

### Worked lifecycle example

**Decision requested:** Should I submit the shared batch now, or add a compatibility test first?

- **Submit now:** `bh-cp-6je.2 — "Skill: decision-ask and status-summary structure for
  operator-facing seats"` and `bh-cp-6je.1 — "Output style: tone, concision, and phrasing for
  operator-facing seats"` move to submitted after the existing checks; the unautomatable
  interactive `/config` check remains for review.
- **Add the test first:** submission waits for one more focused test; it gives stronger drift
  coverage but does not automate the real Claude `/config` session.

**Recommendation:** Add the focused test first, because it protects the canonical contract without
claiming to simulate an interactive Claude session. Work is blocked pending this choice.

## Status summary

Use this structure after an action, handoff, check, or blocker:

1. Lead with the outcome.
2. State what was done and what was not done.
3. Name every affected bead with friendly title and id.
4. State the exact lifecycle state — assigned, submitted, in review, or merged — never a vague
   substitute.
5. State the next action, or the blocker and who owns it.

### Worked lifecycle example

**Status:** I submitted `bh-cp-6je.2 — "Skill: decision-ask and status-summary structure for
operator-facing seats"` and `bh-cp-6je.1 — "Output style: tone, concision, and phrasing for
operator-facing seats"` as one shared batch. I did not approve or merge either bead. Both are
submitted and in review behind their shared review gate. Next, the reviewer decides whether to
approve the batch; the merger can land it only after that gate is resolved.

## Guardrails

- Never refer to a bead by a bare id in operator-facing text.
- Keep verified facts and assumptions separate. If a fact changes the decision, correct it plainly.
- Be concise without becoming cryptic: complete, specific sentences are cheaper than a clarification
  round trip.
