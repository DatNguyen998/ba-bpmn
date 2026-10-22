# BA BPMN plugin

Draw checked BPMN diagrams from a chat. You describe a process in plain words; the assistant asks only what is
missing, shows a picture, and after you approve gives you an SVG, a PNG and a `.bpmn` file that opens in Camunda.

Works in Claude, Codex and Antigravity. One engine, one set of skills, three thin wrappers.

## How it works

**What a business analyst sees.** They describe a process in plain words. The assistant asks only what is missing,
shows a picture for review, redraws it when asked, and writes the files once the picture is approved.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/how-it-works-ba.dark.svg">
  <img alt="Sequence diagram. The business analyst describes a process to an AI tool. The AI tool loads the skills, asks a few short questions, then calls the MCP server, which has the drawing engine lay out and check the diagram. The analyst reviews the picture, asks for a change, approves it, and the files are written." src="docs/diagrams/how-it-works-ba.light.svg">
</picture>

_Diagram source: [`docs/diagrams/how-it-works-ba.mmd`](docs/diagrams/how-it-works-ba.mmd), drawn with [Pele](https://pele.run)._

**What is inside.** Each AI tool only reads the same skills and starts the same small server. All the drawing happens
in one engine on the user's own computer. Nothing is uploaded.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/how-it-works-inside.dark.svg">
  <img alt="Flow diagram. Claude, Codex and Antigravity each have a thin wrapper that uses the same six skills and the same MCP server. The server passes the description to spec.py, which checks it as data, then to the drawing engine, which writes the SVG and the .bpmn and uses a headless browser for the PNG and the Camunda import test. Everything lands in the bpmn-output folder." src="docs/diagrams/how-it-works-inside.light.svg">
</picture>

_Diagram source: [`docs/diagrams/how-it-works-inside.mmd`](docs/diagrams/how-it-works-inside.mmd), drawn with [Pele](https://pele.run)._

Three things make it safe to rely on:

1. **The description is data, never code.** Only listed fields are accepted, and nothing in it is ever run.
2. **Every picture is checked before anyone sees it.** The engine reports overlaps, crossed lines, missing ends and
   more, and the assistant fixes them first.
3. **The Camunda file is tested too.** The `.bpmn` is loaded in Camunda's own viewer before the export is reported
   as done.

## What is in this folder

| Part | What it is |
|---|---|
| `src/bpmn_mcp/server.py` | MCP server with three tools: `bpmn_setup_check`, `bpmn_spec_guide`, `bpmn_build` |
| `src/bpmn_mcp/spec.py` | Turns a JSON diagram description into a drawing. Data only, nothing is executed |
| `src/bpmn_mcp/engine/` | The drawing engine: layout, checks, SVG and `.bpmn` output |
| `skills/` | The single source of the six skills: `bpmn-for-ba` (the workflow) and the shortcuts `bpmn-setup`, `bpmn-new`, `bpmn-change`, `bpmn-export`, `bpmn-check` |
| `.claude-plugin/` | Claude plugin and marketplace manifests (the repository root is the Claude plugin) |
| `plugins/codex/ba-bpmn/` | Codex plugin. The folder name must equal the plugin name |
| `.agents/plugins/marketplace.json` | Codex marketplace file |
| `plugins/antigravity/` | Antigravity plugin |
| `packaging.json` | The repository address. The sync script pins the server to the release tag of the current version (`@v0.1.0`) and writes it into both hosts |
| `scripts/sync_plugins.py` | Copies `skills/` into the Codex and Antigravity folders and writes their server configs |
| `scripts/prepublish.py`, `.githooks/` | The checks to run before publishing (links, text rules, tests, leak scans, a preview of the README as GitHub draws it) and a Git hook that runs them before every push |
| `AGENTS.md`, `CLAUDE.md` | Instructions for anyone (or any AI tool) changing this repository. `CLAUDE.md` only imports `AGENTS.md` |
| `docs/diagrams/` | The two diagrams above as Mermaid text (`.mmd`) and the pictures drawn from them with Pele (`.svg`) |
| `docs/TRAPS.md` | Numbered list of problems that cost real time, and why the code looks the way it does |
| `examples/leave_request.json` | A worked example |
| `tests/` | Tests for the spec, the server, the new BPMN elements, the browser helper and the packaging |

## Install

> **Status:** these commands follow each tool's documentation and the draw.io plugin, but none has been run in the real tool yet. See "What has been tested, and what has not" below.

You need `uv` (a small helper that runs Python programs) and Chrome or Edge (for the PNG and the Camunda check).

| Tool | Commands |
|---|---|
| Claude | `/plugin marketplace add huytquocxx/ba-bpmn`, then `/plugin install ba-bpmn@ba-bpmn` |
| Codex | `codex plugin marketplace add huytquocxx/ba-bpmn`, then `codex plugin add ba-bpmn@ba-bpmn` |
| Antigravity | `agy plugin install https://github.com/huytquocxx/ba-bpmn/tree/main/plugins/antigravity` |

Then start a new chat and say "set up the BPMN tools" (or use the `bpmn-setup` shortcut, for example
`/ba-bpmn:bpmn-setup`), and describe a process.

How the server starts differs: Claude runs it from the plugin's own folder (`${CLAUDE_PLUGIN_ROOT}`). Codex
installs a self-contained copy of its folder and Antigravity documents no folder variable, so both run
`uvx --from <source> bpmn-mcp`, with the source set in `packaging.json`.

## What it needs on the computer

- `uv` (or Python 3.10+ with `pip install .`)
- Chrome or Edge, only for the PNG and the Camunda import check. Set `BPMN_BROWSER` if it is not found.

## What has been tested, and what has not

| Claim | Status |
|---|---|
| The engine draws, checks and exports (SVG, PNG, `.bpmn`) | Tested: 80+ automated tests, and every picture looked at |
| The `.bpmn` loads in Camunda's own viewer (bpmn-js) | Tested: "imported, 0 warnings" |
| The server starts through its `bpmn-mcp` command and works when an AI tool launches it | Tested on Windows with a Python client |
| The file opens in Camunda Modeler itself | Not tested |
| Install and use in Claude | Not tested (manifests follow Anthropic's documentation) |
| Install and use in Codex | Not tested (follows the draw.io plugin and the Codex checks of `sebahrens/bpmn-mcp`) |
| Install and use in Antigravity | Not tested (follows the draw.io plugin and Google's docs; paths differ between sources) |
| `uvx` fetches and starts the server from the repository | Not tested yet |
| Business analysts can install and use it without help | Not tested; planned pilot |

## What it draws

Start and end events (an end can be an error), intermediate catch events, boundary timer, message and error events;
user, service, send, receive, manual and script tasks with their type icons; collapsed sub-processes; decision,
parallel and inclusive gateways; pools, lanes, message flows, link connectors, annotations.
Not yet: event-based and complex gateways, expanded sub-processes, signal and escalation events, data objects,
loop and multi-instance markers.

## Privacy

Files are written on your own computer, under the folder the assistant was started in. Nothing is uploaded.

## Develop

```bash
pip install -e ".[test]"
pytest --cov=bpmn_mcp.spec --cov=bpmn_mcp.server
python scripts/sync_plugins.py          # after editing skills/ or packaging.json
python scripts/sync_plugins.py --check  # fails if the host folders drifted
python scripts/prepublish.py --preview  # every check before publishing, and a preview of the README
python scripts/prepublish.py --install-hook  # once per clone: run the checks before every git push
```

## Known limits and open items

- **Not yet run in the real tools.** The Claude, Codex and Antigravity installs, and `uvx` start-up, have not been tried
  on a clean Windows laptop. The plugin formats were checked against the draw.io plugins and the Codex checks of
  `sebahrens/bpmn-mcp`, not against a running Codex or Antigravity.
- **Headless Edge or Chrome hangs now and then** (about 2 in 15 calls in testing). The engine retries once.
- **The bundled bpmn-js viewer** is used unmodified under the bpmn.io licence. See `THIRD_PARTY_NOTICES.md`.
- **Maintainers:** see `AGENTS.md` for the release steps and `docs/TRAPS.md` for known pitfalls.
