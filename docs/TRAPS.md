# Traps

Read this first when something behaves impossibly. It explains why some code looks odd, so nobody "simplifies" a
workaround back into the bug.

Rules: entries are numbered and never renumbered, because code and notes cite them. A fixed trap is marked
**Fixed**, never deleted. Add the next one at the bottom when something cost real time.

Each entry: the symptom as first seen, the real cause, and where the fix lives.

## Trap 1: the server would not start with the newest MCP library

- **Symptom:** importing `mcp.server.fastmcp` failed with "No module named" after a fresh install.
- **Cause:** version 2 of the `mcp` library renamed `FastMCP` to `MCPServer`. `mcp>=1.2` resolved to version 2.
- **Fix lives in:** `pyproject.toml` pins `mcp>=1.2,<2`. Migrate `server.py` before lifting the pin.
- **Status:** Fixed (pinned).

## Trap 2: the setup check said "not ready" on a normal laptop

- **Symptom:** `bpmn_setup_check` reported no browser when started by an AI tool, but found Edge when run by hand.
- **Cause:** AI tools start MCP servers with a trimmed environment that has no `ProgramFiles` or `ProgramFiles(x86)`.
- **Fix lives in:** `find_browser` in `src/bpmn_mcp/engine/scripts/bpmn_kit.py` falls back to the standard folders on the
  system drive. Test: `tests/test_engine_browser.py`.
- **Status:** Fixed.

## Trap 3: a diagram stopped drawing halfway and tests were green

- **Symptom:** the PNG showed a browser XML error ("Attribute 'stroke-width' is redefined") and half a diagram.
- **Cause:** the hand icon repeated an attribute. The tests checked strings in the SVG, not that the SVG was valid.
- **Fix lives in:** the icon code in `bpmn_kit.py`; `tests/test_new_elements.py` now parses every SVG as XML.
- **Lesson:** open the picture after any engine change (see `AGENTS.md`).
- **Status:** Fixed.

## Trap 4: an export sometimes hung

- **Symptom:** a browser step ran for 120 seconds and then failed. It happened in about 2 of 15 calls, on diagrams that
  worked a minute later.
- **Cause:** headless Edge or Chrome occasionally hangs. The cause is not known.
- **Fix lives in:** `_run_browser` in `bpmn_kit.py` retries once with a 60-second limit; `server.py` turns a final
  timeout into a plain message instead of an exception.
- **Status:** Reduced, not removed. Watch for it in the pilot.

## Trap 5: the AI tool lost the connection while a diagram was built

- **Symptom:** the client reported a broken stream during `bpmn_build`.
- **Cause:** the engine prints progress to stdout, and stdout is the MCP channel.
- **Fix lives in:** `server.py` captures stdout while building and returns it as `log`. Test:
  `test_stdio_protocol_stays_clean` in `tests/test_server.py`.
- **Status:** Fixed.

## Trap 6: the preview image was silently missing

- **Symptom:** `preview=true` reported success but no preview file existed.
- **Cause:** the engine does not create the preview folder, and the browser then fails quietly.
- **Fix lives in:** `server.py` creates the folder before building. Test: `test_full_export_with_preview_lists_every_file`.
- **Status:** Fixed.

## Trap 7: a double quote in a name made the Camunda file invalid

- **Symptom:** a task named `Check "balance"` produced a `.bpmn` that did not parse. Text like `x" onload="y` added real
  attributes to the file. The SVG was fine, so the picture looked right.
- **Cause:** `xml.sax.saxutils.escape` does not escape the double quote, and names are written inside double-quoted
  attributes. Found in the pre-publication security review.
- **Fix lives in:** `attr()` in `bpmn_kit.py`, used for every attribute value in `to_bpmn`. Tests:
  `tests/test_xml_escaping.py`, which also round-trips names through a real XML parser.
- **Status:** Fixed.

## Trap 8: the server was fetched from whatever was newest in the repository

- **Symptom:** none yet. Found in the pre-publication security review. The Codex and Antigravity configs ran
  `uvx --from git+<repository>`, so anyone able to change the repository, including a stolen account, could change
  what runs on every user's computer at its next start.
- **Cause:** an address with no version in it.
- **Fix lives in:** `server_source()` in `scripts/sync_plugins.py` pins it to the tag `v<version>` of
  `pyproject.toml`. Tests: `test_server_source_is_pinned_to_the_version_tag` and
  `test_all_hosts_start_the_same_server` in `tests/test_packaging.py`.
- **Status:** Fixed in this repository. Needs the tag to exist on GitHub and tags to be protected there (see Release
  in `AGENTS.md`).
