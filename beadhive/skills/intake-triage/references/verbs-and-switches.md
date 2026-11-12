# Intake-triage verbs and the switches they need

Everything under `intake.external` is **host-owned and off by default**; no key binds a tracker,
holds a credential or pre-approves a write. A verb whose switch is off refuses naming the key
(or `intake_disabled` / `outbox_disabled`) before it writes anything. Refusal codes print in
lower case in the `✗ <verb> refused (<code>)` line. The triage seat reports
that refusal to the operator and never edits config. Check the installed help
(`bh work <verb> --help`) when a flag here and the binary disagree; the binary wins.

| Verb | What it records | Needs on | Refusals worth knowing |
|---|---|---|---|
| `bh work intake [--source github] [--json] [--no-dupes]` | nothing (read: the untriaged queue and `bd find-duplicates` candidates) | — | — |
| `bh work issue <report>` | nothing (read: title, description = issue body, state, edges) | — | — |
| `bh work thread ingest <report>` | the report's `intake.thread` from the tracker's comments (tracker **read** only), then deletion reconciliation | `comments.enabled`, `plugins.tracker-github.enabled`, `plugins.tracker-github.read.comments.enabled` | an incomplete read exits non-zero and keeps what it read |
| `bh work thread show <report> [--json]` | nothing (read: `thread seq`, new evidence, flagged comments, the `tracks` / `investigates` links) | `comments.enabled` | "no thread recorded" until the first ingest |
| `bh work thread considered <report> --through <seq>` | the triage watermark: comments up to `<seq>` stop being new evidence; idempotent; intake state untouched | `comments.enabled` | `--through` is required |
| `bh work accept <report> [--type T] [--priority P]` | `intake` cleared to accepted (plain accept) | — | — |
| `bh work accept <report> --work <id>` / `--new-work [--type T] [--priority P]` | links the report as `tracks` to existing / newly created plain work (`delivery:pending`), then accepts | `enabled` | `target_is_report`, `target_untriaged`, `cross_store_link`, `public_store_id`, `not_a_report` (born-native), `--work` with `--new-work` |
| `bh work link <report> --to <work> [--replace]` / `--remove` | the `tracks` edge (many reports to one work), `delivery:pending`; `--remove` keeps the value and records an `unlinked` fact | `enabled` | `report_closed` (link before you reject), `already_linked_elsewhere` without `--replace` |
| `bh work investigate <report>` | nothing (read: tracked work and investigating beads) | `enabled` | — |
| `bh work investigate <report> --new-work [--type T] [--priority P]` / `--work <id>` / `--work <id> --remove` | bd's `validates` edge work → report; never a milestone, never a `delivery` value, intake untouched; `--new-work` creates "Reproduce: <title>", type `task` by default | `enabled` | `tracked_work` (the work the report tracks cannot also investigate it), the link refusals |
| `bh work reject <report> --reason "<public text>"` | closes the report with a reporter-visible reason | — | — |
| `bh work reroute <report> --to <hive>` / `--super <seat>` | re-files into the right hive / bounces to a superintendent seat | — | exactly one of `--to` / `--super` |
| `bh work promote <report>` | `intake:promoted`, handed to the planner (adopt links it as `tracks` to the epic) | — | — |
| `bh work needs-info <report> --ask "<text>"` | drafts the question as a supervised `reply`, then `intake:needs-info` (out of the queue, still held) | `needs_info.enabled`, `outbox.enabled`, `comments.enabled` | `unread_evidence` (run `thread considered` first), `not_a_report`, closed or already fielded |
| `bh work wake <report>` / `--all` | `intake:needs-info` → `untriaged` when the stored thread holds a reporter's reply; never marks it considered | `needs_info.enabled`; `--all` also `needs_info.sweep` | `not_needs_info` |
| `bh work outbox draft <report> --text "<reply>"` | a drafted `reply` record (leak-checked at once; a finding leaves it held) | `enabled`, `outbox.enabled`, `plugins.tracker-github.enabled` | `outbox_disabled`, tracker not wired |
| `bh work outbox show [<outbox-id>] [--bead <report>] [--open]` | nothing (read: listing, or one record's dry run) | `outbox.enabled` | without a wired tracker it prints the stored draft, no digest |

## Operator-only — not this seat

| Verb | Why it is not yours |
|---|---|
| `bh work outbox approve <id> --op <comment\|labels>:<digest> [--publish <finding>]` | mints a single-use write grant; the state machine refuses agent seats (`dev/`, `disp/`, `crew/`, `coord/`) |
| `bh work outbox send \| discard \| retry <id>` | tracker writes and retirements; operator seat required |
| `bh work outbox reconcile [<id>]` | settles unknown outcomes after a send; part of the operator's send loop |
| `bh work delivery release <tag>` | verifies a release tag, moves reports to `delivery:released` and drafts `released` records |
| `bh work delivery blocked \| deprioritised <work> --reason <text>` | milestone notices to every report tracking the work; need `milestones.draft_on_blocked` / `draft_on_deprioritised` |
| any `intake.external.*` or `plugins.tracker-github.*` edit | host-owned configuration; a fleet push cannot set it and neither can triage |

## Report dimensions you will see

| Dimension | Values | Who writes it |
|---|---|---|
| `intake` | `untriaged`, `needs-info`, `accepted`, `rejected`, `rerouted`, `promoted` | triage verbs only |
| work progress (derived, not stored) | `unlinked`, `open`, `in_progress`, `in_review`, `closed` | nobody — read from the tracked work |
| `delivery` | `pending`, `merged`, `released`, `reverted` | link and the merge / release triggers |
| `notified` | `replied`, `merged`, `released`, `corrected`, … | the outbox sender after a comment is sent |

These are private labels: they never appear in a draft.
