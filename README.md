# BA BPMN plugin (v0.1, work in progress)

Draw checked BPMN diagrams from a chat. You describe a process in plain words; the assistant asks only what is
missing, shows a picture, and after you approve gives you an SVG, a PNG and a `.bpmn` file that opens in Camunda.

Works in Claude, Codex and Antigravity. One engine, one set of skills, three thin wrappers.

## What is in this folder

| Part | What it is |
|---|---|
| `src/bpmn_mcp/server.py` | MCP server with three tools: `bpmn_setup_check`, `bpmn_spec_guide`, `bpmn_build` |
| `src/bpmn_mcp/spec.py` | Turns a JSON diagram description into a drawing. Data only, nothing is executed |
| `src/bpmn_mcp/engine/` | The drawing engine. Started as a copy of the `bpmn-diagram` skill's engine and now changed (see below) |
| `skills/` | The single source of the six skills: `bpmn-for-ba` (the workflow) and the shortcuts `bpmn-setup`, `bpmn-new`, `bpmn-change`, `bpmn-export`, `bpmn-check` |
| `.claude-plugin/` | Claude plugin and marketplace manifests (the repository root is the Claude plugin) |
| `plugins/codex/ba-bpmn/` | Codex plugin. The folder name must equal the plugin name |
| `.agents/plugins/marketplace.json` | Codex marketplace file |
| `plugins/antigravity/` | Antigravity plugin |
| `packaging.json` | Where Codex and Antigravity fetch the server from. One setting, written into both hosts |
| `scripts/sync_plugins.py` | Copies `skills/` into the Codex and Antigravity folders and writes their server configs |
| `AGENTS.md`, `CLAUDE.md` | Instructions for anyone (or any AI tool) changing this repository. `CLAUDE.md` only imports `AGENTS.md` |
| `docs/TRAPS.md` | Numbered list of problems that cost real time, and why the code looks the way it does |
| `examples/leave_request.json` | A worked example |
| `tests/` | Tests for the spec, the server, the new BPMN elements, the browser helper and the packaging |

## Install (none of these has been tested in the real tool yet)

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
| The engine draws, checks and exports (SVG, PNG, `.bpmn`) | Tested here: 60+ automated tests, and every picture looked at |
| The `.bpmn` loads in Camunda's own viewer (bpmn-js) | Tested here: "imported, 0 warnings" |
| The server starts through its `bpmn-mcp` command and works when an AI tool launches it | Tested here, on Windows, with a Python client |
| The file opens in Camunda Modeler itself | Not tested |
| Install and use in Claude | Not tested (manifests follow Anthropic's documentation) |
| Install and use in Codex | Not tested (follows the draw.io plugin and sebahrens's Codex checks) |
| Install and use in Antigravity | Not tested (follows the draw.io plugin and Google's docs; paths differ between sources) |
| `uvx` fetches and starts the server from the repository | Not tested; `uv` was not installed where this was built |
| Business analysts can install and use it without help | Not tested; planned pilot |

## What it draws (v0.1)

Start and end events (an end can be an error), intermediate catch events, boundary timer, message and error events;
user, service, send, receive, manual and script tasks with their type icons; collapsed sub-processes; decision,
parallel and inclusive gateways; pools, lanes, message flows, link connectors, annotations.
Not yet: event-based and complex gateways, expanded sub-processes, signal and escalation events, data objects,
loop and multi-instance markers.

Note: the engine here is no longer identical to the original `bpmn-diagram` skill. SVG task boxes are 8 px taller
(room for the icons), and the engine has the new elements above.

## Privacy

Files are written on your own computer, under the folder the assistant was started in. Nothing is uploaded.

## Develop

```bash
pip install -e ".[test]"
pytest --cov=bpmn_mcp.spec --cov=bpmn_mcp.server
python scripts/sync_plugins.py          # after editing skills/ or packaging.json
python scripts/sync_plugins.py --check  # fails if the host folders drifted
```

## Open items before release

- The install commands only work once the repository exists at the address in `packaging.json`. Run
  `python scripts/sync_plugins.py --release` before each release: it fails while a "TBC" placeholder is left.
- The bundled bpmn-js viewer is allowed under the bpmn.io licence if its notice stays and its watermark is not hidden
  (see `THIRD_PARTY_NOTICES.md`). This summary is not legal advice; read the licence once before going public.
- Verify all three installs, and `uvx` start-up, on a clean Windows laptop. No host tool was available here.
- Headless Edge or Chrome hangs now and then (about 2 in 15 calls in testing). The engine retries once; watch for it in the pilot.
- The newest MCP library (version 2) renamed the server class, so the dependency is pinned below 2.
- Codex and Antigravity plugin formats were checked against the draw.io plugins and sebahrens's Codex validator, not
  against a running Codex or Antigravity.
