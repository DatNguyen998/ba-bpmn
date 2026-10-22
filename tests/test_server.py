import asyncio
import json
import os
import sys
from pathlib import Path

from bpmn_mcp import server

ROOT = Path(__file__).parent.parent
EXAMPLE = json.loads((ROOT / "examples" / "leave_request.json").read_text(encoding="utf-8"))


def test_setup_check_reports_findings():
    res = server.bpmn_setup_check()
    assert isinstance(res["ready"], bool)
    assert any("Drawing engine" in f for f in res["findings"])
    assert not any(":\\" in f or "/Users/" in f for f in res["findings"]), "no file paths in output"


def test_spec_guide_has_the_format():
    assert "Diagram spec format" in server.bpmn_spec_guide()


def test_build_svg_writes_relative_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(EXAMPLE, name="leave", stage="svg")
    assert res["ok"], res
    assert res["files"] == [str(Path("bpmn-output") / "leave.svg"), str(Path("bpmn-output") / "leave.spec.json")]
    assert (tmp_path / "bpmn-output" / "leave.svg").exists()
    saved = json.loads((tmp_path / "bpmn-output" / "leave.spec.json").read_text(encoding="utf-8"))
    assert saved == EXAMPLE


def test_log_has_no_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(EXAMPLE, name="leave", stage="svg")
    assert str(tmp_path) not in res["log"]
    assert "leave.svg" in res["log"]


def test_full_export_with_preview_lists_every_file(tmp_path, monkeypatch):
    import pytest
    if not server.bpmn_setup_check()["ready"]:
        pytest.skip("no browser on this machine")
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(EXAMPLE, name="leave", stage="all", preview=True)
    assert res["ok"], res
    names = {Path(f).name for f in res["files"]}
    assert {"leave.svg", "leave.bpmn", "leave.png", "leave.camunda-preview.png"} <= names
    assert "imported, 0 warnings" in res["log"]


def test_browser_timeout_is_reported_not_raised(tmp_path, monkeypatch):
    import subprocess

    def hang(self, *a, **k):
        raise subprocess.TimeoutExpired("browser", 1)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server.Diagram, "export_png", hang)
    res = server.bpmn_build(EXAMPLE, name="leave", stage="svg", preview=True)
    assert not res["ok"] and "took too long" in res["errors"][0]


def test_out_dir_cannot_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(EXAMPLE, name="leave", out_dir="..")
    assert not res["ok"] and "inside the current working folder" in res["errors"][0]


def test_bad_name_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(EXAMPLE, name="../evil")
    assert not res["ok"] and "name may use only" in res["errors"][0]


def test_bad_stage_is_rejected():
    assert not server.bpmn_build(EXAMPLE, stage="everything")["ok"]


def test_invalid_spec_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build({"title": "x", "bogus": 1})
    assert not res["ok"] and res["errors"][0].startswith("[spec]")


def test_stdio_protocol_stays_clean(tmp_path):
    """The engine prints while building; that must not corrupt the MCP stream."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "bpmn_mcp.server"], cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})

    async def run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                result = await session.call_tool("bpmn_build", {"spec": EXAMPLE, "name": "leave"})
                return tools, result

    tools, result = asyncio.run(asyncio.wait_for(run(), 120))
    assert {"bpmn_build", "bpmn_setup_check", "bpmn_spec_guide"} <= tools
    assert not result.isError
    assert json.loads(result.content[0].text)["ok"] is True
    assert (tmp_path / "bpmn-output" / "leave.svg").exists()
