---
name: bpmn-new
description: Start drawing a new BPMN process diagram from a plain description. Use only when the user explicitly asks to start a new diagram from scratch.
---

# New BPMN diagram

Use the `bpmn-for-ba` skill to draw a new process diagram from what the user described after the command.

If the user gave no description, ask them to describe the process in a few sentences. Then follow that skill's
workflow: ask only what is missing (one short batch), draft the SVG, fix all check errors, show the picture, and
wait for feedback before exporting.
