import os
import subprocess

import pytest

import bpmn_mcp.spec  # noqa: F401  (puts the engine on the import path)
import bpmn_kit


class Done:
    stdout = "ok"


def test_hung_browser_is_retried_once(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return Done()

    monkeypatch.setattr(bpmn_kit.Diagram, "find_browser", staticmethod(lambda: "browser"))
    monkeypatch.setattr(bpmn_kit.subprocess, "run", run)
    assert bpmn_kit.Diagram._run_browser(["--x"]) == "ok"
    assert len(calls) == 2


def test_browser_that_always_hangs_gives_up(monkeypatch):
    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(bpmn_kit.Diagram, "find_browser", staticmethod(lambda: "browser"))
    monkeypatch.setattr(bpmn_kit.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        bpmn_kit.Diagram._run_browser(["--x"])


@pytest.mark.skipif(os.name != "nt", reason="Windows install locations")
def test_browser_is_found_when_the_host_passes_a_trimmed_environment(monkeypatch):
    """MCP hosts start servers without ProgramFiles; an installed Edge must still be found."""
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "BPMN_BROWSER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SYSTEMDRIVE", "C:")
    standard = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    monkeypatch.setattr(bpmn_kit.Path, "exists", lambda self: str(self) == standard)
    monkeypatch.setattr(bpmn_kit.shutil, "which", lambda name: None)
    assert bpmn_kit.Diagram.find_browser() == standard


def test_missing_browser_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(bpmn_kit.Diagram, "find_browser", staticmethod(lambda: None))
    with pytest.raises(RuntimeError, match="No Edge/Chrome"):
        bpmn_kit.Diagram._run_browser(["--x"])
