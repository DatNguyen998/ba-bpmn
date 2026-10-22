"""MCP server: lets an AI tool draw BPMN diagrams with the bundled engine."""
import contextlib
import io
import json
import os
import platform
import re
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .spec import SpecError, build_diagram, Diagram

import bpmn_kit  # noqa: E402  (importable once .spec has put the engine on the path)

mcp = FastMCP("bpmn")

_GUIDE = Path(__file__).resolve().parent / "spec_format.md"
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def _safe_out_dir(out_dir):
    """Outputs go under the folder the AI tool was started in, never elsewhere."""
    base = Path.cwd().resolve()
    target = (base / out_dir).resolve()
    if target != base and base not in target.parents:
        raise ValueError("out_dir must be inside the current working folder")
    return target, base


@mcp.tool()
def bpmn_setup_check() -> dict:
    """Check that this computer can draw diagrams. Writes nothing.

    Returns plain-language findings. Run this when a user asks to set up, or when a build fails
    with a browser error.
    """
    findings, ready = [], True
    findings.append(f"Python {platform.python_version()}: ok")
    try:
        Diagram("setup check")
        findings.append("Drawing engine: ok")
    except Exception as e:  # engine could not start
        findings.append(f"Drawing engine: failed ({type(e).__name__})")
        ready = False
    if bpmn_kit.VIEWER_JS.exists():
        findings.append("Camunda import checker: ok")
    else:
        findings.append("Camunda import checker: missing")
        ready = False
    browser = Diagram.find_browser()
    if browser:
        findings.append(f"Browser for PNG and import check: ok ({Path(browser).stem})")
    else:
        findings.append("Browser for PNG and import check: not found. Install Chrome or Edge, "
                        "or set BPMN_BROWSER to its location. SVG-only drawing still works.")
        ready = False
    return {"ready": ready, "findings": findings}


@mcp.tool()
def bpmn_spec_guide() -> str:
    """Return the diagram spec format, layout rules and the fixes for each check error.

    Read this before the first bpmn_build call.
    """
    return _GUIDE.read_text(encoding="utf-8")


@mcp.tool()
def bpmn_build(spec: dict, name: str = "diagram", out_dir: str = "bpmn-output",
               stage: str = "svg", preview: bool = False) -> dict:
    """Lay out and check a diagram, and write the files.

    spec: the diagram as a JSON object (see bpmn_spec_guide).
    name: file name without extension (letters, digits, - and _).
    out_dir: folder under the current working folder for the outputs.
    stage: "svg" = checks plus SVG only (use while drafting); "all" = also PNG, .bpmn and the
           Camunda import check (use only after the user approved the drawing).
    preview: also write a look-at-it PNG (svg stage) or a Camunda preview (all stage).

    Returns ok, errors (fix every one and build again), warnings, files (relative paths) and the log.
    """
    if stage not in ("svg", "all"):
        return {"ok": False, "errors": ["stage must be 'svg' or 'all'"], "warnings": [], "files": [], "log": ""}
    if not _NAME.match(name):
        return {"ok": False, "errors": ["name may use only letters, digits, - and _ (max 60)"],
                "warnings": [], "files": [], "log": ""}
    try:
        target, base = _safe_out_dir(out_dir)
        diagram = build_diagram(spec)
    except (ValueError, SpecError) as e:
        return {"ok": False, "errors": [f"[spec] {e}"], "warnings": [], "files": [], "log": ""}

    target.mkdir(parents=True, exist_ok=True)
    spec_path = target / f"{name}.spec.json"  # kept so the diagram can be rebuilt or changed later
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    preview_dir = target / "preview"
    if preview:
        preview_dir.mkdir(parents=True, exist_ok=True)  # the engine does not create it
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):  # the engine prints; stdout belongs to the MCP protocol
            res = diagram.build(target, name, stage, preview_dir if preview else None)
    except RuntimeError as e:
        return {"ok": False, "errors": [f"[browser] {e}"], "warnings": [], "files": [],
                "log": _relative(log.getvalue(), base)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": ["[browser] the browser took too long to draw the picture. "
                                        "Close other Chrome or Edge windows and try again."],
                "warnings": [], "files": [], "log": _relative(log.getvalue(), base)}
    files = [str(Path(f).resolve().relative_to(base)) for f in res["files"]] + [str(spec_path.relative_to(base))]
    if preview:
        files += [str(p.relative_to(base)) for p in sorted(preview_dir.glob(f"{name}.*"))]
    return {"ok": not res["errors"], "errors": res["errors"], "warnings": res["warnings"],
            "files": files, "log": _relative(log.getvalue(), base)}


def _relative(text, base):
    """Show paths relative to the working folder; users do not need the full location."""
    return text.replace(str(base) + os.sep, "").replace(str(base), ".")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
