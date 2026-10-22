import copy
import json
from pathlib import Path

import pytest

from bpmn_mcp.spec import SpecError, build_diagram

EXAMPLE = json.loads((Path(__file__).parent.parent / "examples" / "leave_request.json").read_text(encoding="utf-8"))


def spec(**changes):
    s = copy.deepcopy(EXAMPLE)
    s.update(changes)
    return s


def test_leave_example_builds_and_passes_checks():
    errors, warnings, _ = build_diagram(EXAMPLE).check()
    assert errors == []


def test_rejects_unknown_top_level_field():
    with pytest.raises(SpecError, match="unknown top-level"):
        build_diagram(spec(script="print(1)"))


def test_rejects_unknown_element_field():
    s = spec()
    s["elements"][6]["sub"] = "not allowed on a gateway"
    with pytest.raises(SpecError, match="unknown field 'sub'"):
        build_diagram(s)


def test_rejects_bad_task_type():
    s = spec()
    s["elements"][1]["type"] = "robot"
    with pytest.raises(SpecError, match="must be one of"):
        build_diagram(s)


def test_rejects_missing_required_field():
    s = spec()
    del s["elements"][1]["name"]
    with pytest.raises(SpecError, match="missing field 'name'"):
        build_diagram(s)


def test_rejects_unknown_kind():
    s = spec()
    s["elements"][0]["kind"] = "teleport"
    with pytest.raises(SpecError, match="unknown kind"):
        build_diagram(s)


def test_timer_before_its_task_gives_a_helpful_error():
    s = spec()
    timer = next(e for e in s["elements"] if e["kind"] == "timer")
    s["elements"].remove(timer)
    s["elements"].insert(0, timer)
    with pytest.raises(SpecError, match="come earlier"):
        build_diagram(s)


def test_rejects_unknown_lane():
    s = spec()
    s["elements"][1]["lane"] = "Nobody"
    with pytest.raises(SpecError):
        build_diagram(s)


def test_boolean_is_not_a_number():
    s = spec()
    s["elements"][1]["col"] = True
    with pytest.raises(SpecError, match="must be a number"):
        build_diagram(s)


def test_rejects_too_many_elements():
    s = spec()
    s["elements"] = s["elements"] * 20
    with pytest.raises(SpecError, match="too many elements"):
        build_diagram(s)


def test_spec_text_is_never_executed(tmp_path):
    marker = tmp_path / "ran"
    s = spec(title=f"__import__('pathlib').Path(r'{marker}').write_text('x')")
    build_diagram(s)
    assert not marker.exists()


def test_duplicate_id_is_reported():
    s = spec()
    s["elements"][1]["id"] = s["elements"][0]["id"]
    with pytest.raises(SpecError, match="duplicate id"):
        build_diagram(s)
