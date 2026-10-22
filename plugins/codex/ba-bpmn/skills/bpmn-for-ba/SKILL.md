---
name: bpmn-for-ba
description: Draw BPMN process diagrams (swimlanes with pools and lanes, decisions, message flows, timers) as a checked SVG and PNG plus a Camunda-importable .bpmn file. Use this whenever the user wants a process flow, workflow, swimlane, BPMN, as-is or to-be process, Camunda model, or "who does what, in which order" picture of a business process, even if they only say "draw the flow" or "map this process", and when they want an earlier diagram changed or re-exported.
---

# BPMN for business analysts

You draw the diagram by calling the `bpmn` tools. The user never sees code: they describe a process in
plain words, you ask only what is missing, and they review a picture.

Tools: `bpmn_setup_check` (can this computer draw?), `bpmn_spec_guide` (the spec format and fixes for each
check error), `bpmn_build` (lay out, check, write files).

## Workflow

1. **First time, or any browser error:** call `bpmn_setup_check` and explain the result in plain words.
2. **Get the process facts.** Who takes part (organisations, roles, systems), the steps in order, each decision
   and its outcomes, waits and time limits, and how the process ends (good and bad endings). Use the user's words.
   - If you have enough to draw, draw. Do not interrogate.
   - If facts are missing, ask once, in one short batch of at most five questions, about things that change the
     diagram (who else is involved, the possible outcomes of each decision, time limits).
   - If something stays unclear, draw it and put "TBC" in the subtitle; list the open questions after the picture.
   - Never invent a step to make the notation tidy. Ask instead.
3. **Read `bpmn_spec_guide` once**, then write the spec.
4. **Draft:** call `bpmn_build` with `stage="svg"` and `preview=true`. Fix every error it returns (each message
   names the check; the guide lists the fix) and build again. Open the look PNG it lists and check it yourself:
   the checks catch geometry, not meaning.
5. **Show the user the picture** and ask for feedback. Do not export yet: each round of feedback would leave stale
   copies. Describe a big structural change (a new pool, a new branch) in chat and get a yes before redrawing.
6. **After approval:** call `bpmn_build` with `stage="all"` and `preview=true`. It must report `imported, 0 warnings`
   and no errors. Look at the Camunda preview PNG to see how Camunda will draw it.
7. **Report:** what was checked and passed, the open questions and TBCs, and these two notes:
   - Camunda shows "One Process must be Executable" style messages. That is expected: the file is a documentation
     model, not a deployable process.
   - After a rebuild, the user must re-upload the `.bpmn`. Edits made inside Camunda are overwritten by the next
     rebuild, so changes go through you.

`bpmn_build` saves the spec next to the outputs as `<name>.spec.json`, so the diagram can be rebuilt or changed
later. To change an earlier diagram, read that file, edit it, and build again. Show the spec to the user on request.

## Modelling rules

- **Pools are parties, lanes are roles.** Anyone outside the organisation (customer, partner, regulator) gets their
  own pool; roles inside one organisation are lanes of its pool. Pools talk only through message flows. Sequence
  arrows never cross a pool edge.
- **Message flows land on a task or an event, never on a diamond.** If a message triggers a decision, land it on the
  step that receives or checks it, then go to the diamond. A message cannot start from a start event or end on an end event.
- **Waiting for another party is the receiver's step.** Use a receive task ("Await signature") in the waiting pool and
  put time limits there as a boundary timer, not on the other party's step.
- **Boxes say what happens, not who.** Title is verb plus object, short ("Review case"); subtitle is detail or result.
  The lane already says who.
- **One question per diamond, written inside it, ending in "?"**, every exit labelled ("yes" / "no").
- **Main path left to right on the main row; exceptions on the lower row** with dashed arrows to named end events
  ("Rejected", "Expired").
- **Many back-paths** (rework, appeal) become link connectors ("go to A", "continue from A"), not long arrows.
- **Every pool starts and ends.**
- **Do not add elements the evidence does not support.** Propose them as options instead of drawing them.
- **Use the user's terms** for roles and steps; never rename them for neatness.

## What is not supported

Only the core of BPMN is drawn: start and end events (an end can be an error), intermediate catch events, boundary
timer, message and error events, tasks (user, service, send, receive, manual, script, plain) and collapsed
sub-processes, gateways (decision, parallel, inclusive), pools, lanes, message flows, link connectors and
annotations. If the user needs something else (event-based or complex gateways, expanded sub-processes, signal or
escalation events, data objects, loops and multi-instance markers), say plainly that it is not supported yet and
offer the closest honest alternative. Do not draw it wrongly.

A collapsed sub-process is a single box that hides detail. Draw its inner steps as a separate diagram if the user
wants them, and say so.

Pick the gateway by what the user means: "one of these" is a decision (exclusive), "all of these at the same time"
is parallel (and needs a matching join), "one or more of these" is inclusive.

## Privacy

All files are written on the user's own computer, under the folder the AI tool was started in. Nothing is uploaded.
