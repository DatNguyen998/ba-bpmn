# BPMN plugin for business analysts

An MCP server and skills that draw checked BPMN swimlane diagrams (SVG, PNG, Camunda `.bpmn`) from a chat. It
ships to Claude, Codex and Antigravity. The users are business analysts, not developers: every message a user
sees must be plain language.

## Commands

```bash
pip install -e ".[test]"
pytest --cov=bpmn_mcp.spec --cov=bpmn_mcp.server
python scripts/sync_plugins.py            # after editing skills/ or packaging.json
python scripts/sync_plugins.py --check    # must pass before every commit
python scripts/sync_plugins.py --release  # before publishing: fails while a "TBC" placeholder is left
```

## Rules that are not obvious

- **Two sources, everything else is generated.** `skills/` and `packaging.json`. Never hand-edit
  `plugins/codex/ba-bpmn/skills/`, `plugins/antigravity/skills/`, `plugins/codex/ba-bpmn/.mcp.json` or
  `plugins/antigravity/mcp_config.json`. Run the sync script.
- **Behaviour lives in `src/bpmn_mcp/`.** The plugin folders stay thin wrappers. A plugin folder must still work as a
  self-contained copy (Codex installs one), so it holds no Python code and no path outside itself.
- **The spec is data, never code.** `spec.py` accepts only whitelisted keys and never runs spec content.
- **Never print to stdout in server code.** Stdout is the MCP channel. The engine prints while building, and
  `server.py` captures it.
- **Output paths stay relative to the working folder.** No absolute paths in tool results.
- **Do not edit `src/bpmn_mcp/engine/assets/bpmn-viewer.development.js`.** Its licence requires the notice and the
  watermark code to stay intact. See `THIRD_PARTY_NOTICES.md`.
- **Keep `mcp` below version 2** until `server.py` is migrated (the server class was renamed).
- **Host format limits.** The Codex plugin folder name must equal its manifest name (`ba-bpmn`). The Antigravity
  manifest allows only `name` and `description`. Every skill stays under 24,000 bytes.
- **The engine here is not the original `bpmn-diagram` skill.** It has new elements and taller SVG task boxes. This
  copy is the one that ships.
- **Look at the picture.** Tests cannot see layout. After any engine change, build a diagram and open the PNG.

## If you change this, also do that

| You change | Also |
|---|---|
| `skills/**` or `packaging.json` | Run the sync script and commit the generated files |
| Version in `pyproject.toml` | Same version in `.claude-plugin/plugin.json` and the Codex `plugin.json` (a test checks), run the sync script (it re-pins the server to `v<version>`), then follow Release |
| A BPMN element in the engine | The whitelist in `spec.py`, `spec_format.md`, "What is not supported" in `skills/bpmn-for-ba/SKILL.md`, the README list, and tests |
| Something that cost real time to debug | Add a numbered entry to `docs/TRAPS.md` |
| A claim that a host install works | Only after it ran in that host. Update the README evidence table |

## Release

1. Bump the version in `pyproject.toml` and both manifests. Run the sync script, the tests, and `--release`.
2. Commit, then tag that commit and push both: `git tag -a v0.1.0 -m "v0.1.0"`, `git push origin main v0.1.0`.
3. The tag must exist on GitHub before anyone installs. Codex and Antigravity fetch the server at `…@v<version>`,
   and a test fails if that tag in their configs differs from the project version.
4. Never move or delete a published tag. Ship a new version instead, and keep tags protected on GitHub.

## Never

- Put client, company or personal data, real process names or secrets in this repository. It is public. Examples
  stay neutral (a leave request, an order).
- Push or publish without the owner's explicit yes.

Read `docs/TRAPS.md` first when something behaves impossibly.
