"""The Claude, Codex and Antigravity packages must agree with each other and with the host formats we verified."""
import importlib.util
import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("sync_plugins", ROOT / "scripts" / "sync_plugins.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

CODEX, ANTI = sync.CODEX, sync.ANTIGRAVITY
SKILLS = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
ANTIGRAVITY_SKILL_LIMIT = 24_000          # Antigravity reads only this many bytes of a skill body


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_host_folders_are_in_sync_with_the_source():
    assert sync.drift() == []


def test_every_skill_is_copied_byte_for_byte_into_both_hosts():
    for name in SKILLS:
        source = (ROOT / "skills" / name / "SKILL.md").read_bytes()
        for host in (CODEX, ANTI):
            assert (host / "skills" / name / "SKILL.md").read_bytes() == source


@pytest.mark.parametrize("name", SKILLS)
def test_skill_file_is_well_formed(name):
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert front, "missing frontmatter"
    fields = dict(line.split(": ", 1) for line in front.group(1).splitlines())
    assert fields["name"] == name, "skill name must equal its folder name"
    assert fields["description"].strip()
    assert len(text.encode("utf-8")) <= ANTIGRAVITY_SKILL_LIMIT


def test_every_skill_the_main_skill_mentions_exists():
    text = (ROOT / "skills" / "bpmn-for-ba" / "SKILL.md").read_text(encoding="utf-8")
    for tool in ("bpmn_setup_check", "bpmn_spec_guide", "bpmn_build"):
        assert tool in text


def test_codex_plugin_folder_name_equals_manifest_name():
    manifest = load(CODEX / ".codex-plugin" / "plugin.json")
    assert CODEX.name == manifest["name"]            # Codex requires this
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    for key in ("skills", "mcpServers"):
        assert (CODEX / manifest[key]).exists()


def test_codex_marketplace_points_at_the_plugin():
    market = load(ROOT / ".agents" / "plugins" / "marketplace.json")
    entry = market["plugins"][0]
    assert entry["source"]["source"] == "local"
    assert entry["source"]["path"].startswith("./")
    assert (ROOT / entry["source"]["path"]).resolve() == CODEX.resolve()
    assert entry["name"] == load(CODEX / ".codex-plugin" / "plugin.json")["name"]
    assert {"installation", "authentication"} <= set(entry["policy"])


def test_codex_mcp_config_is_a_direct_one_server_map():
    cfg = load(CODEX / ".mcp.json")
    assert "mcpServers" not in cfg and list(cfg) == ["bpmn"]
    server = cfg["bpmn"]
    assert server["command"] == "uvx" and server["default_tools_approval_mode"] == "writes"


def test_antigravity_manifest_uses_only_the_allowed_fields():
    assert set(load(ANTI / "plugin.json")) <= {"name", "description", "$schema"}


def test_antigravity_mcp_config_declares_the_server():
    server = load(ANTI / "mcp_config.json")["mcpServers"]["bpmn"]
    assert server["command"] == "uvx"


def test_all_hosts_start_the_same_server():
    cfg = load(ROOT / "packaging.json")
    codex = load(CODEX / ".mcp.json")["bpmn"]["args"]
    anti = load(ANTI / "mcp_config.json")["mcpServers"]["bpmn"]["args"]
    assert codex == anti == ["--from", cfg["server_source"], cfg["server_command"]]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert cfg["server_command"] in project["scripts"]


def test_versions_agree_everywhere():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    claude = load(ROOT / ".claude-plugin" / "plugin.json")["version"]
    codex = load(CODEX / ".codex-plugin" / "plugin.json")["version"]
    assert project == claude == codex


def test_claude_plugin_still_has_its_server_and_no_stale_commands_folder():
    cfg = load(ROOT / ".claude-plugin" / "plugin.json")
    assert cfg["mcpServers"]["bpmn"]["command"] == "uvx"
    assert not (ROOT / "commands").exists(), "commands were replaced by skills"


def test_plugin_folders_contain_no_python_source_or_absolute_paths():
    """Codex installs a self-contained copy of the plugin folder, so it must not rely on files outside it."""
    for host in (CODEX, ANTI):
        for path in host.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".md"):
                text = path.read_text(encoding="utf-8")
                assert not re.search(r"[A-Za-z]:\\|/Users/|\.\./", text), path


def test_release_check_detects_a_placeholder(tmp_path, monkeypatch):
    marker = tmp_path / "x.json"
    marker.write_text('{"a": "TBC"}', encoding="utf-8")
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    monkeypatch.setattr(sync, "HAND_WRITTEN", [marker])
    assert sync.release_problems() == ["'TBC' left in x.json"]


def test_repository_is_release_ready():
    assert sync.release_problems() == []
