"""Keep the Codex and Antigravity plugin folders in step with the single source.

    python scripts/sync_plugins.py            write the generated files
    python scripts/sync_plugins.py --check    exit 1 if any generated file differs (use in CI)
    python scripts/sync_plugins.py --release  also exit 1 while any "TBC" placeholder is left

Source of truth: `skills/` (copied byte for byte into each host) and `packaging.json` (where the MCP server is
fetched from). The host manifests (plugin.json, marketplace.json) are written by hand.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEX = ROOT / "plugins" / "codex" / "ba-bpmn"        # folder name must equal the plugin name in its manifest
ANTIGRAVITY = ROOT / "plugins" / "antigravity"
HAND_WRITTEN = [ROOT / ".claude-plugin" / "plugin.json", ROOT / ".claude-plugin" / "marketplace.json",
                ROOT / ".agents" / "plugins" / "marketplace.json", CODEX / ".codex-plugin" / "plugin.json",
                ANTIGRAVITY / "plugin.json", ROOT / "packaging.json"]


def _json(data):
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def project_version():
    match = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return match.group(1)


def server_source(cfg):
    """The address the server is fetched from, pinned to the release tag of the current version. An unpinned
    address would run whatever is newest in the repository on every user's computer."""
    return f"git+{cfg['repository']}@v{project_version()}"


def expected_files():
    """Every generated or copied file: {path: bytes}."""
    cfg = json.loads((ROOT / "packaging.json").read_text(encoding="utf-8"))
    args = ["--from", server_source(cfg), cfg["server_command"]]
    files = {
        # Codex: a direct one-server map (no "mcpServers" wrapper); only writes ask for approval
        CODEX / ".mcp.json": _json({"bpmn": {"command": "uvx", "args": args, "default_tools_approval_mode": "writes"}}),
        ANTIGRAVITY / "mcp_config.json": _json({"mcpServers": {"bpmn": {"command": "uvx", "args": args}}}),
    }
    for src in sorted((ROOT / "skills").rglob("*")):
        if src.is_file():
            rel = src.relative_to(ROOT / "skills")
            for host in (CODEX, ANTIGRAVITY):
                files[host / "skills" / rel] = src.read_bytes()
    return files


def stale_files(expected):
    """Files inside a host's skills folder that no longer have a source."""
    found = []
    for host in (CODEX, ANTIGRAVITY):
        base = host / "skills"
        if base.exists():
            found += [p for p in base.rglob("*") if p.is_file() and p not in expected]
    return found


def drift():
    expected = expected_files()
    problems = [f"missing or different: {p.relative_to(ROOT)}" for p, data in expected.items()
                if not p.exists() or p.read_bytes() != data]
    problems += [f"no longer in skills/: {p.relative_to(ROOT)}" for p in stale_files(expected)]
    return problems


def release_problems():
    """Placeholders that must be filled before the plugins are published."""
    return [f"'TBC' left in {p.relative_to(ROOT)}" for p in HAND_WRITTEN
            if p.exists() and "TBC" in p.read_text(encoding="utf-8")]


def write():
    expected = expected_files()
    for p in stale_files(expected):
        p.unlink()
    for p, data in expected.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return len(expected)


def main(argv):
    check, release = "--check" in argv, "--release" in argv
    problems = drift() if check or release else []
    if release:
        problems += release_problems()
    if check or release:
        for line in problems:
            print(line)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    print(f"wrote {write()} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
