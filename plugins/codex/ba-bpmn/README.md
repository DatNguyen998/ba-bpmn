# BPMN for BAs: Codex plugin

Draw checked BPMN swimlane diagrams from a chat. You describe a process in plain words; the assistant asks only
what is missing, shows a picture, and after you approve gives you an SVG, a PNG and a `.bpmn` file for Camunda.

## Install

> **Status:** these commands follow the Codex plugin format and the draw.io plugin, but have not been run in a real
> Codex yet.

You need `uv` (a small helper that runs Python programs) and Chrome or Edge (for the PNG and the Camunda check).

```bash
codex plugin marketplace add huytquocxx/ba-bpmn
codex plugin add ba-bpmn@ba-bpmn
```

Start a new session, then say "set up the BPMN tools". The `bpmn-setup` skill checks the computer and explains
anything missing in plain words. After that, describe a process, or use `/ba-bpmn:bpmn-new`.

## What is in this folder

| Path | Purpose |
|---|---|
| `.codex-plugin/plugin.json` | Plugin manifest. The folder name `ba-bpmn` must equal the manifest `name` (Codex requires this) |
| `.mcp.json` | Starts the drawing server with `uvx`. **Generated** from `packaging.json`; do not edit by hand |
| `skills/` | The six skills. **Copied** byte for byte from the repository's `skills/` folder; do not edit here |

The skills are: `bpmn-for-ba` (the whole workflow), and the shortcuts `bpmn-setup`, `bpmn-new`, `bpmn-change`,
`bpmn-export`, `bpmn-check`.

Codex installs a self-contained copy of this folder, so the Python code is not inside it. The server is fetched
by `uvx` from the source named in `packaging.json`.

## Test locally

```bash
codex plugin marketplace add /path/to/ba-bpmn
codex plugin add ba-bpmn@ba-bpmn
codex plugin list
```

Confirm `ba-bpmn@ba-bpmn` is listed, then ask for a diagram.

## Changing it

Edit the repository's `skills/` or `packaging.json`, then run `python scripts/sync_plugins.py`. CI runs
`python scripts/sync_plugins.py --check`; before publishing, run it with `--release` to catch placeholders.
