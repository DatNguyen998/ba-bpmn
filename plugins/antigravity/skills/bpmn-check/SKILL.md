---
name: bpmn-check
description: Show the quality checks and open questions for the current BPMN diagram. Use only when the user asks for a review or check of a diagram.
---

# Check a BPMN diagram

Rebuild the current diagram with `bpmn_build` (`stage="svg"`, `preview=true`) and report in plain words:
- the checks that passed, and every error or warning with what it means and how you would fix it;
- any "TBC" items and open questions still in the diagram;
- anything that looks like it breaks the modelling rules in the `bpmn-for-ba` skill.

Do not change the diagram. Ask whether the user wants the fixes applied.
