"""Text typed by a user must come out of the .bpmn exactly as typed, and must never add attributes."""
import xml.etree.ElementTree as ET

import pytest

from bpmn_mcp.spec import build_diagram

NASTY = [
    'Check "balance"',
    'x" onload="alert(1)',
    "Tom's <R&D> review",
    'a & "b" < c',
    "</script><script>alert(1)</script>",
]


def spec(name):
    return {
        "title": "T",
        "pools": [
            {"id": "A", "title": f"Pool {name}", "lanes": [{"name": f"Lane one {name}"}, {"name": "Lane two"}]},
            {"id": "B", "title": "Other", "lanes": [{"name": "Only"}]},
        ],
        "elements": [
            {"kind": "start", "id": "s", "pool": "A", "lane": 0, "col": 0.3, "name": "go"},
            {"kind": "task", "id": "t", "pool": "A", "lane": 0, "col": 1, "name": name},
            {"kind": "link_to", "id": "lt", "pool": "A", "lane": 0, "col": 2, "link": name},
            {"kind": "link_from", "id": "lf", "pool": "A", "lane": 1, "col": 2, "link": name},
            {"kind": "end", "id": "e", "pool": "A", "lane": 1, "col": 3, "name": "done"},
            {"kind": "start", "id": "s2", "pool": "B", "lane": 0, "col": 1, "name": "in", "message": True},
            {"kind": "end", "id": "e2", "pool": "B", "lane": 0, "col": 2, "name": "out"},
        ],
        "flows": [{"from": "s", "to": "t"}, {"from": "t", "to": "lt", "label": name},
                  {"from": "lf", "to": "e"}, {"from": "s2", "to": "e2"}],
        "messages": [{"from": "t", "to": "s2", "label": name}],
    }


def parse(name):
    xml, _ = build_diagram(spec(name)).to_bpmn()
    root = ET.fromstring(xml)          # raises if the file is not well-formed
    return {el.attrib["id"]: el for el in root.iter() if "id" in el.attrib}


@pytest.mark.parametrize("name", NASTY)
def test_bpmn_is_well_formed_and_names_survive_exactly(name):
    by_id = parse(name)
    assert by_id["t"].attrib["name"] == name                    # task
    assert by_id["A"].attrib["name"] == f"Pool {name}"          # pool
    assert by_id["A_Lane0"].attrib["name"] == f"Lane one {name}"  # lane
    assert by_id["lt_Def"].attrib["name"] == name               # link event
    labels = [el.attrib["name"] for el in by_id.values() if el.tag.endswith(("sequenceFlow", "messageFlow"))
              and "name" in el.attrib]
    assert labels == [name, name]                                # one sequence flow, one message flow


@pytest.mark.parametrize("name", NASTY)
def test_user_text_cannot_add_attributes(name):
    by_id = parse(name)
    assert set(by_id["t"].attrib) == {"id", "name"}
    assert set(by_id["A"].attrib) == {"id", "name", "processRef"}
    assert set(by_id["A_Lane0"].attrib) == {"id", "name"}
    assert set(by_id["lt_Def"].attrib) == {"id", "name"}
    for el in by_id.values():
        assert not any(a.lower().startswith("on") for a in el.attrib), el.attrib


@pytest.mark.parametrize("name", NASTY)
def test_svg_stays_well_formed(name):
    ET.fromstring(build_diagram(spec(name)).to_svg()[0])
