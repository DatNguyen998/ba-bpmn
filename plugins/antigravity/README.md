# BPMN for BAs: Antigravity plugin

Draw checked BPMN swimlane diagrams from a chat. You describe a process in plain words; the assistant asks only
what is missing, shows a picture, and after you approve gives you an SVG, a PNG and a `.bpmn` file for Camunda.

## Install

> **Status:** these commands follow the Antigravity documentation and the draw.io plugin, but have not been run in a
> real Antigravity yet.

You need `uv` (a small helper that runs Python programs) and Chrome or Edge (for the PNG and the Camunda check).

Install from this folder's address on GitHub, not from the repository address. The repository also holds the plugins
for other tools, and installing it whole would pull those in under the same name.

```bash
agy plugin install https://github.com/huytquocxx/ba-bpmn/tree/main/plugins/antigravity
agy plugin validate
```

Start a new session, then say "set up the BPMN tools". The `bpmn-setup` skill checks the computer and explains
anything missing in plain words. After that, describe a process.

## What is in this folder

| Path | Purpose |
|---|---|
| `plugin.json` | Plugin manifest. Antigravity accepts only `name` and `description` here |
| `mcp_config.json` | Starts the drawing server with `uvx`. **Generated** from `packaging.json`; do not edit by hand |
| `skills/` | The six skills. **Copied** byte for byte from the repository's `skills/` folder; do not edit here |

Antigravity finds skills and the MCP config by folder name, so the manifest does not list them.

## Things to know

- Antigravity reads only the first 24,000 bytes of a skill. A test keeps every skill under that limit.
- The server is fetched by `uvx` from the source named in `packaging.json`, so the plugin folder holds no Python code.
- Antigravity installs differ between versions: sources disagree on where plugins and the MCP config live. Check on
  your version after installing.

## Changing it

Edit the repository's `skills/` or `packaging.json`, then run `python scripts/sync_plugins.py`. CI runs
`python scripts/sync_plugins.py --check`; before publishing, run it with `--release` to catch placeholders.
