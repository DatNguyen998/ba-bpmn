---
name: bpmn-export
description: Export the approved BPMN diagram as SVG, PNG and a Camunda .bpmn file. Use only when the user says the diagram is approved and asks to export it.
---

# Export a BPMN diagram

Use the `bpmn-for-ba` skill to export the diagram the user has approved.

Confirm which diagram this is if more than one exists. Then call `bpmn_build` with `stage="all"` and
`preview=true`. It must report `imported, 0 warnings` and no errors. Look at the Camunda preview, then report the
files written, what was checked, the open questions and TBCs, and the two Camunda notes from the `bpmn-for-ba` skill.
