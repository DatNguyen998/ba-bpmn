"""Turn a JSON-style spec (a plain dict) into a bpmn_kit Diagram.

The spec is data, never code: only the keys listed below are accepted, every value is type-checked,
and nothing in it is executed. This is what lets an AI tool hand us a diagram safely.
"""
import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent / "engine" / "scripts"
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from bpmn_kit import Diagram  # noqa: E402

MAX_ELEMENTS = 200
MAX_TEXT = 200
MAX_DESCRIPTION = 1000


class SpecError(ValueError):
    """The spec is not valid. The message says where and what to change."""


# ---------------------------------------------------------------- value checks
def _str(v, where, limit=MAX_TEXT):
    if not isinstance(v, str):
        raise SpecError(f"{where} must be text")
    if len(v) > limit:
        raise SpecError(f"{where} is longer than {limit} characters")
    return v


def _num(v, where):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SpecError(f"{where} must be a number")
    if not -1000 <= v <= 1000:
        raise SpecError(f"{where} is out of range")
    return v


def _bool(v, where):
    if not isinstance(v, bool):
        raise SpecError(f"{where} must be true or false")
    return v


def _enum(*allowed):
    def check(v, where):
        if isinstance(v, bool) or v not in allowed:
            raise SpecError(f"{where} must be one of: {', '.join(map(str, allowed))}")
        return v
    return check


def _lane_ref(v, where):
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        raise SpecError(f"{where} must be a lane name or a lane number")
    return v


def _channel(v, where):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _num(v, where)
    if isinstance(v, list) and len(v) == 2:
        return tuple(_num(x, where) for x in v)
    raise SpecError(f"{where} must be a number or a pair of numbers")


def _pair(v, where):
    if isinstance(v, list) and len(v) == 2:
        return tuple(_num(x, where) for x in v)
    raise SpecError(f"{where} must be a pair of numbers")


def _raw(v, where):
    """Pass-through for fields whose structure is checked by the caller."""
    return v


S, N, B = _str, _num, _bool
LABEL = _enum("below", "above", "right", "left")
ROW = _enum(0, 1)
SIDE = _enum("l", "r", "t", "b")
EDGE = _enum("bottom-right", "bottom-left", "bottom", "top-right", "top-left", "top")
TASK_TYPE = _enum("user", "service", "send", "receive", "manual", "script", "task", "subprocess")
GATEWAY_TYPE = _enum("exclusive", "parallel", "inclusive")
LANE_COLOR = _enum("customer", "staff", "system", "backoffice", "partner", "external")
BOUNDARY_EVENT = _enum("message", "timer", "error")

_POS = {"id": S, "pool": S, "lane": _lane_ref, "col": N}
_POS_REQ = ("id", "pool", "lane", "col")

# kind -> (engine method, allowed keys with checks, required keys)
ELEMENTS = {
    "start": ("start", {**_POS, "name": S, "row": ROW, "message": B, "timer": S, "label": LABEL, "dy": N}, _POS_REQ),
    "end": ("end", {**_POS, "name": S, "row": ROW, "label": LABEL, "dy": N, "event": _enum("error")}, _POS_REQ),
    "catch": ("catch", {**_POS, "name": S, "row": ROW, "message": B, "timer": S, "label": LABEL, "dy": N}, _POS_REQ),
    "task": ("task", {**_POS, "name": S, "sub": S, "type": TASK_TYPE, "row": ROW, "dy": N, "implicit_end": B},
             _POS_REQ + ("name",)),
    "gateway": ("gateway", {**_POS, "question": S, "row": ROW, "dy": N, "type": GATEWAY_TYPE}, _POS_REQ),
    "link_to": ("link_to", {**_POS, "link": S, "row": ROW, "label": LABEL, "dy": N}, _POS_REQ + ("link",)),
    "link_from": ("link_from", {**_POS, "link": S, "row": ROW, "label": LABEL, "dy": N}, _POS_REQ + ("link",)),
    "timer": ("timer", {"id": S, "attached_to": S, "name": S, "duration": S, "edge": EDGE, "label": LABEL},
              ("id", "attached_to", "duration")),
    "boundary": ("boundary", {"id": S, "attached_to": S, "name": S, "event": BOUNDARY_EVENT, "edge": EDGE,
                              "label": LABEL, "duration": S}, ("id", "attached_to")),
}

FLOW_KEYS = {"from": S, "to": S, "label": S, "exit": SIDE, "entry": SIDE, "channel": _channel, "dashed": B,
             "exit_dx": N, "entry_dx": N, "label_at": _pair}
MESSAGE_KEYS = {"from": S, "to": S, "label": S, "dx": N, "tdx": N, "channel": _channel,
                "label_side": _enum("left", "right")}
LANE_KEYS = {"name": S, "sub": S, "color": LANE_COLOR, "h": N, "main": N, "center": B}
POOL_KEYS = {"id": S, "title": S, "external": B, "lanes": _raw}
ANNOTATION_KEYS = {"node": S, "text": S, "dx": N, "dy": N, "width": N}
TOP_KEYS = {"title", "description", "pools", "elements", "flows", "messages", "notes", "legend_notes",
            "annotations"}


def _check_obj(obj, schema, required, where):
    if not isinstance(obj, dict):
        raise SpecError(f"{where} must be an object")
    for key in obj:
        if key not in schema:
            raise SpecError(f"{where}: unknown field '{key}'. Allowed: {', '.join(sorted(schema))}")
    for key in required:
        if key not in obj:
            raise SpecError(f"{where}: missing field '{key}'")
    return {k: schema[k](v, f"{where}.{k}") for k, v in obj.items()}


def _list(spec, key):
    items = spec.get(key, [])
    if not isinstance(items, list):
        raise SpecError(f"'{key}' must be a list")
    return items


def build_diagram(spec):
    """Validate `spec` and return the bpmn_kit Diagram it describes. Raises SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("the spec must be an object")
    unknown = set(spec) - TOP_KEYS
    if unknown:
        raise SpecError(f"unknown top-level field(s): {', '.join(sorted(unknown))}")
    if "title" not in spec:
        raise SpecError("missing field 'title'")
    elements = _list(spec, "elements")
    if len(elements) > MAX_ELEMENTS:
        raise SpecError(f"too many elements ({len(elements)}); the limit is {MAX_ELEMENTS}")

    d = Diagram(_str(spec["title"], "title"), description=_str(spec.get("description", ""), "description", MAX_DESCRIPTION))
    try:
        _add_pools(d, _list(spec, "pools"))
        for i, el in enumerate(elements):
            _add_element(d, el, f"elements[{i}]")
        for i, f in enumerate(_list(spec, "flows")):
            c = _check_obj(f, FLOW_KEYS, ("from", "to"), f"flows[{i}]")
            d.flow(c.pop("from"), c.pop("to"), **c)
        for i, m in enumerate(_list(spec, "messages")):
            c = _check_obj(m, MESSAGE_KEYS, ("from", "to"), f"messages[{i}]")
            d.message(c.pop("from"), c.pop("to"), **c)
        for i, n in enumerate(_list(spec, "notes")):
            c = _check_obj(n, {"pool": S, "lines": _raw}, ("pool", "lines"), f"notes[{i}]")
            if not isinstance(c["lines"], list):
                raise SpecError(f"notes[{i}].lines must be a list of text lines")
            d.note(c["pool"], [_str(x, f"notes[{i}].lines") for x in c["lines"]])
        for i, t in enumerate(_list(spec, "legend_notes")):
            d.legend_note(_str(t, f"legend_notes[{i}]"))
        for i, a in enumerate(_list(spec, "annotations")):
            c = _check_obj(a, ANNOTATION_KEYS, ("node", "text"), f"annotations[{i}]")
            d.annotate(c.pop("node"), c.pop("text"), **c)
    except SpecError:
        raise
    except (ValueError, KeyError) as e:
        raise SpecError(str(e).strip("'\"")) from e
    return d


def _add_pools(d, pools):
    for i, p in enumerate(pools):
        where = f"pools[{i}]"
        c = _check_obj(p, POOL_KEYS, ("id", "title", "lanes"), where)
        raw_lanes = p["lanes"]
        if not isinstance(raw_lanes, list) or not raw_lanes:
            raise SpecError(f"{where}.lanes must be a non-empty list")
        lanes = []
        for j, lane in enumerate(raw_lanes):
            lc = _check_obj(lane, LANE_KEYS, ("name",), f"{where}.lanes[{j}]")
            lanes.append(Diagram.lane(lc.pop("name"), **lc))
        d.pool(c["id"], c["title"], lanes, external=c.get("external", False))


def _add_element(d, el, where):
    if not isinstance(el, dict) or "kind" not in el:
        raise SpecError(f"{where} must be an object with a 'kind'")
    kind = el["kind"]
    if kind not in ELEMENTS:
        raise SpecError(f"{where}: unknown kind '{kind}'. Allowed: {', '.join(ELEMENTS)}")
    method, schema, required = ELEMENTS[kind]
    c = _check_obj({k: v for k, v in el.items() if k != "kind"}, schema, required, where)
    if kind == "gateway" and c.get("type", "exclusive") == "exclusive" and not c.get("question"):
        raise SpecError(f"{where}: a decision (exclusive gateway) needs a 'question'")
    try:
        getattr(d, method)(c.pop("id"), *[c.pop(k) for k in _positional(kind)], **c)
    except KeyError as e:
        raise SpecError(f"{where}: unknown element {e}; an element it attaches to must come earlier in the list") from e


def _positional(kind):
    """Engine positional parameters after the id, in order."""
    return {
        "start": ("pool", "lane", "col"), "end": ("pool", "lane", "col"), "catch": ("pool", "lane", "col"),
        "task": ("pool", "lane", "col", "name"), "gateway": ("pool", "lane", "col"),
        "link_to": ("pool", "lane", "col", "link"), "link_from": ("pool", "lane", "col", "link"),
        "timer": ("attached_to",), "boundary": ("attached_to",),
    }[kind]
