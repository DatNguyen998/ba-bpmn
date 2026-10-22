# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

Only the latest release gets fixes. If you use an older one, update first.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private form instead: [report a vulnerability](https://github.com/huytquocxx/ba-bpmn/security/advisories/new).
Only the maintainer can see what you send.

## What to include

- What you found and where: the file, the tool (`bpmn_build`, `bpmn_setup_check`, `bpmn_spec_guide`), or the step.
- How to reproduce it. A short diagram description that triggers it is ideal.
- What you think the impact is.
- Which AI tool (Claude, Codex or Antigravity), which operating system and which version of this plugin.

## What to expect

- A first reply within 7 days. This is a one-person project, so this is best effort.
- For a confirmed problem, a fix or a clear decision within 30 days, and credit in the release notes if you want it.
- Nothing about your report is made public before a fix is available.

## In scope

- The MCP server, the diagram description checking, the drawing engine, and the skill and plugin files.
- A diagram description that writes outside the output folder, runs code, or shows local file paths.
- A skill or plugin file that could make an AI tool do something the user did not ask for.
- A secret or personal detail committed to this repository by mistake.

## Out of scope

- The bundled bpmn-js viewer and other third-party software. Report those to their own projects.
- Problems that need an attacker who already controls your computer.
