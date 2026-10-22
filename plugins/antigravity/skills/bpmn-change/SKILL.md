---
name: bpmn-change
description: Change a BPMN diagram drawn earlier (add, move or remove steps) and redraw it. Use only when the user explicitly asks to change an existing diagram.
---

# Change a BPMN diagram

Use the `bpmn-for-ba` skill to change the diagram drawn earlier in this conversation, or saved as a
`<name>.spec.json` file in the output folder.

If the user did not say what to change, ask. Edit the spec (never the exported files), describe any structural
change (new pool, new branch) and get a yes first, then rebuild with `stage="svg"`, fix all check errors and show
the new picture. Do not export until the user approves.
