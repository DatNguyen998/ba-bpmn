---
name: bpmn-setup
description: Check that this computer is ready to draw BPMN diagrams, and help fix what is missing. Use when the user asks to set up, install, check or test the BPMN tools, or when a diagram build fails with a browser error.
---

# BPMN setup check

Run the `bpmn_setup_check` tool. Explain the result in plain words for a non-technical user.

If something is missing:
- Say what it is and why it is needed (a browser is needed for the PNG and the Camunda import check).
- Offer to help, and ask before installing anything. Never change security or system settings.
- If a step needs administrator rights, stop and write a short, ready-to-send request for the user's IT team
  (for example: "Please install Google Chrome or Microsoft Edge on my laptop").

If everything is fine, draw a tiny sample diagram with `bpmn_build` (`stage="svg"`) to prove it works, then say
"Ready. Describe a process and I will draw it."
