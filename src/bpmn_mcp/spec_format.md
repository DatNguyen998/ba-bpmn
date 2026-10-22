# Diagram spec format

A diagram is one JSON object. It is data only: unknown fields are rejected.

```json
{
  "title": "Leave request",
  "description": "One sentence for screen readers",
  "pools": [{"id": "Pool_A", "title": "Employee", "lanes": [{"name": "Employee", "sub": "staff member", "color": "customer"}]}],
  "elements": [{"kind": "start", "id": "s1", "pool": "Pool_A", "lane": "Employee", "col": 0.3, "name": "needs time off"}],
  "flows": [{"from": "s1", "to": "t1", "label": "yes"}],
  "messages": [{"from": "t1", "to": "r1", "label": "request"}]
}
```

## Pools and lanes
- A pool is a party (company, customer, partner). Lanes are roles inside one pool.
- `pools[]`: `id` (letters, digits, `_ - .`; starts with a letter), `title`, `external` (optional), `lanes[]`.
- `lanes[]`: `name`, `sub` (optional detail), `color`, `h` (height, default 176), `main` (raise to 64-70 when an arrow must loop over the top), `center`.
- `color`: `customer` (coral), `staff` (teal), `system` (grey), `backoffice` (purple), `partner` (amber), `external` (blue).
- Refer to a lane by its name or its number (0 is the first).

## Elements (`elements[]`, each has a `kind`)
All placed elements need `id`, `pool`, `lane`, `col`. `col` is the column (176 px apart, fractions allowed). `row` is 0 (main row) or 1 (lower row, for exits and end events).

| kind | extra fields | meaning |
|---|---|---|
| `start` | `name`, `message` (true if another pool's message starts it), `timer`, `label` | start event |
| `end` | `name` (the outcome, e.g. "Rejected"), `label`, `event`: "error" for a failure ending | end event |
| `task` | `name` (verb + object), `sub` (detail), `type`: user, service, send, receive, manual, script, task, subprocess | step box with a type icon; `subprocess` is a collapsed sub-process with a + marker (no `sub` text, put detail in the name) |
| `gateway` | `type`: exclusive (default), parallel, inclusive; `question` | exclusive = a decision, one path: needs a `question` ending in "?" and a label on every exit. parallel = all paths at once (a split, or the join that waits for all): no question, no exit labels. inclusive = one or more paths: label every exit; an optional `question` is written beside the diamond |
| `catch` | `name`, `message`, `timer` | intermediate wait event (prefer a `receive` task when a time limit is needed) |
| `timer` | `id`, `attached_to`, `duration` (ISO, e.g. P3D), `name`, `edge` | boundary timer on a task |
| `boundary` | `id`, `attached_to`, `event` (message, timer or error), `name`, `edge`, `duration` | interrupting event on a task or collapsed sub-process; `error` is for "this step failed", its flow goes to an exception path |
| `link_to` / `link_from` | `link` (same text in both, e.g. "A: Rework") | "go to" / "continue from" connectors replacing long back-arrows |

`label` is below, above, right or left. `edge` is bottom-right, bottom-left, bottom, top-right, top-left, top. `dy` nudges an element vertically. Elements that attach to a task (`timer`, `boundary`) must come after it in the list.

## Connections
- `flows[]`: `from`, `to`, optional `label`, `dashed` (exception paths), `exit` and `entry` (sides l, r, t, b), `channel`, `exit_dx`, `entry_dx`, `label_at`. A sequence flow stays inside one pool.
- `messages[]`: `from`, `to`, optional `label`, `dx`, `tdx`, `channel`, `label_side`. A message flow goes between pools. It lands on a task or event, never on a diamond, never from a start event or into an end event.

## Extras
- `notes[]`: `{"pool", "lines": [...]}` text beside a pool.
- `legend_notes[]`: extra lines under the legend (abbreviations, open questions).
- `annotations[]`: `{"node", "text", "dx", "dy", "width"}` a note linked to one step.

## Layout rules that avoid check errors
- Main path left to right on row 0; exceptions on row 1 with `dashed` flows to named end events.
- Put a start event at `col` 0.3 before a column-1 box; put an end event at (last box col + 0.75).
- Decisions: main outcome straight right, the other going down. Every exit labelled.
- Every parallel split needs its parallel join later (the join waits for all paths). Use an inclusive gateway when
  one or more paths may run, an exclusive one when exactly one does.
- A branch should run in the lane where its next step lives (use `exit` and `entry` to turn at the diamond).
- Many back-paths (rework, appeal): use `link_to` / `link_from` and explain the symbol in `legend_notes`.
- Boxes say what happens, not who does it. The lane already says who.

## Fixing check errors
Each error starts with a code. The usual fixes:
- `1-text` text too wide: shorten, move detail to `sub`.
- `2-arrow` arrow too short: move the target a column further or use `row` 1.
- `4-overlap`, `4-lane`: different column or row; widen lane `h`.
- `4-label-*`, `5-through-*`: change `label`, move the element, or change `exit` / `entry`.
- `5-same-line`: give one arrow other `exit` / `entry` sides.
- `8-gateway`, `8-msg-start`, `8-msg-end`: land messages on a task or a receive task.
- `9-reach`, `9-deadend`, `9-noend`: connect it, add an end event, add the exit branch.
- `10-gw-label`: label every decision exit.
- `12-import`: read the message; usually an id or reference problem.
