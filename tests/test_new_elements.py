"""Gateway types, collapsed sub-processes, error events and task-type icons."""
import re

import pytest

from bpmn_mcp import server
from bpmn_mcp.spec import SpecError, build_diagram

POOL = {"id": "P", "title": "Shop", "lanes": [{"name": "Team", "sub": "order desk", "h": 300, "main": 70}]}


def el(kind, id, col, **kw):
    return {"kind": kind, "id": id, "pool": "P", "lane": "Team", "col": col, **kw}


ORDER = {
    "title": "Order handling",
    "pools": [POOL],
    "elements": [
        el("start", "s", 0.3, name="order placed"),
        el("task", "take", 1, name="Take order", type="user"),
        el("gateway", "split", 2, type="parallel"),
        el("task", "stock", 3, name="Check stock", type="service"),
        el("task", "pack", 3, name="Pack goods", type="manual", row=1),
        el("gateway", "join", 4, type="parallel"),
        el("gateway", "extras", 5, type="inclusive"),
        el("task", "note", 6, name="Send gift note", type="send"),
        el("task", "invoice", 6, name="Create invoice", type="script", row=1),
        el("end", "done", 7.75, name="Gift sent"),
        el("end", "billed", 7.75, name="Invoiced", row=1),
    ],
    "flows": [
        {"from": "s", "to": "take"}, {"from": "take", "to": "split"},
        {"from": "split", "to": "stock"}, {"from": "split", "to": "pack"},
        {"from": "stock", "to": "join"}, {"from": "pack", "to": "join"},
        {"from": "join", "to": "extras"},
        {"from": "extras", "to": "note", "label": "gift"}, {"from": "extras", "to": "invoice", "label": "invoice"},
        {"from": "note", "to": "done"}, {"from": "invoice", "to": "billed"},
    ],
}

SUBPROCESS = {
    "title": "Fulfilment",
    "pools": [POOL],
    "elements": [
        el("start", "s", 0.3, name="paid"),
        el("task", "fulfil", 1.5, name="Fulfil order", type="subprocess"),
        {"kind": "boundary", "id": "err", "attached_to": "fulfil", "event": "error", "name": "out of stock"},
        el("end", "ok", 3.2, name="Shipped"),
        el("end", "fail", 3.2, name="Order failed", row=1, event="error"),
    ],
    "flows": [
        {"from": "s", "to": "fulfil"}, {"from": "fulfil", "to": "ok"},
        {"from": "err", "to": "fail", "dashed": True},
    ],
}


@pytest.fixture(params=[ORDER, SUBPROCESS], ids=["gateways-and-tasks", "subprocess-and-errors"])
def diagram_spec(request):
    return request.param


def test_svg_is_valid_xml(diagram_spec):
    """A browser stops drawing at the first XML error (for example a repeated attribute)."""
    import xml.etree.ElementTree as ET
    ET.fromstring(build_diagram(diagram_spec).to_svg()[0])


def test_every_task_icon_is_valid_xml():
    import xml.etree.ElementTree as ET
    types = ("user", "service", "send", "receive", "manual", "script", "task", "subprocess")
    spec = {"title": "Icons", "pools": [POOL],
            "elements": [el("task", f"t{i}", i + 1, name=t, type=t) for i, t in enumerate(types)]}
    ET.fromstring(build_diagram(spec).to_svg()[0])


def test_diagrams_pass_all_checks(diagram_spec):
    errors, _, _ = build_diagram(diagram_spec).check()
    assert errors == []


def test_gateway_types_are_drawn_and_exported():
    d = build_diagram(ORDER)
    svg = d.to_svg()[0]
    assert svg.count('class="gw-parallel"') == 2
    assert svg.count('class="gw-inclusive"') == 1
    xml, errs = d.to_bpmn()
    assert errs == []
    assert xml.count("<bpmn:parallelGateway") == 2
    assert xml.count("<bpmn:inclusiveGateway") == 1


def test_task_icons_are_drawn_for_every_typed_task():
    svg = build_diagram(ORDER).to_svg()[0]
    for kind in ("user", "service", "manual", "send", "script"):
        assert f'class="icon-{kind}"' in svg, kind


def test_plain_task_has_no_icon():
    spec = {**ORDER, "elements": [dict(e, type="task") if e["kind"] == "task" else e for e in ORDER["elements"]]}
    assert 'class="icon-' not in build_diagram(spec).to_svg()[0]


def test_subprocess_is_collapsed_with_a_marker():
    d = build_diagram(SUBPROCESS)
    assert 'class="subprocess-marker"' in d.to_svg()[0]
    xml, _ = d.to_bpmn()
    assert re.search(r"<bpmn:subProcess id=\"fulfil\"", xml)
    assert 'bpmnElement="fulfil" isExpanded="false"' in xml


def test_error_events_are_drawn_and_exported():
    d = build_diagram(SUBPROCESS)
    svg = d.to_svg()[0]
    assert svg.count('class="error-bolt"') == 3          # boundary + end + the legend entry
    xml, _ = d.to_bpmn()
    assert xml.count("<bpmn:errorEventDefinition") == 2


def test_parallel_split_needs_no_exit_labels():
    errors, _, _ = build_diagram(ORDER).check()
    assert not any("10-gw-label" in e for e in errors)


def test_exclusive_decision_still_needs_exit_labels():
    spec = {**ORDER, "elements": [dict(e, type="exclusive", question="Rush order?") if e["id"] == "split" else e
                                  for e in ORDER["elements"]]}
    errors, _, _ = build_diagram(spec).check()
    assert any("10-gw-label" in e for e in errors)


def test_exclusive_gateway_still_needs_a_question():
    spec = {**ORDER, "elements": [dict(e, type="exclusive") if e["id"] == "split" else e for e in ORDER["elements"]]}
    with pytest.raises(SpecError, match="question"):
        build_diagram(spec)


def test_bad_gateway_type_is_rejected():
    spec = {**ORDER, "elements": [dict(e, type="magic") if e["id"] == "split" else e for e in ORDER["elements"]]}
    with pytest.raises(SpecError, match="must be one of"):
        build_diagram(spec)


def test_camunda_accepts_the_new_elements(tmp_path, monkeypatch, diagram_spec):
    if not server.bpmn_setup_check()["ready"]:
        pytest.skip("no browser on this machine")
    monkeypatch.chdir(tmp_path)
    res = server.bpmn_build(diagram_spec, name="t", stage="all")
    assert res["ok"], res
    assert "imported, 0 warnings" in res["log"]
