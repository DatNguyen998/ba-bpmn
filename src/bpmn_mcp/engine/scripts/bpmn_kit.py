"""bpmn_kit: describe a BPMN diagram once, get a checked SVG, a PNG and a Camunda-importable .bpmn.

The spec places every element on a grid (pool, lane, column, row). Routing, labels, the SVG
drawing, the BPMN XML and all checks are derived from that one description, so the picture
and the Camunda file can never drift apart.
"""
import json, math, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
VIEWER_JS = HERE.parent / "assets" / "bpmn-viewer.development.js"

# fill, stroke, title text, subtitle text
COLORS = {
    "customer":   ("#FAECE7", "#993C1D", "#712B13", "#993C1D"),
    "staff":      ("#E1F5EE", "#0F6E56", "#085041", "#0F6E56"),
    "system":     ("#F1EFE8", "#5F5E5A", "#444441", "#5F5E5A"),
    "backoffice": ("#EEEDFE", "#534AB7", "#3C3489", "#534AB7"),
    "partner":    ("#FAEEDA", "#854F0B", "#633806", "#854F0B"),
    "external":   ("#E6F1FB", "#185FA5", "#0C447C", "#185FA5"),
}
LINE, INK, TEXT, MUTED = "#888780", "#444441", "#2C2C2A", "#5F5E5A"
TASK_TAGS = {"user": "userTask", "service": "serviceTask", "send": "sendTask", "receive": "receiveTask",
             "manual": "manualTask", "script": "scriptTask", "task": "task", "subprocess": "subProcess", None: "task"}
GATEWAY_TAGS = {"exclusive": "exclusiveGateway", "parallel": "parallelGateway", "inclusive": "inclusiveGateway"}
MIN_ARROW = 40          # px before an arrowhead (check 2)
ROW_GAP = 112           # distance from the main row to the lower row (row=1)
LANE_PAD = 20           # minimum empty space above and below a lane's contents


def text_w(s, size=12, bold=False):
    return len(s) * size * (0.55 if bold else 0.535)


# ---------------------------------------------------------------- model
class YRef(float):
    """An absolute y that remembers its pool and lane, so it follows them when lanes grow or the
    diagram is stacked into a bigger one (Diagram.include)."""
    def __new__(cls, value, pool, rel, lane=0):
        obj = float.__new__(cls, value)
        obj.pool, obj.rel, obj.lane = pool, rel, lane
        return obj


def _resolve_y(v):
    return v.pool.lane_top(v.lane) + v.rel if isinstance(v, YRef) else v


class Lane:
    def __init__(self, name, sub="", color="system", h=176, main=30, center=True):
        self.name, self.sub, self.color, self.h, self.main = name, sub, color, h, main
        self.center = center      # centre the lane's contents as one block (keeps their relative positions)


class Pool:
    def __init__(self, pid, title, lanes, external=False):
        self.id, self.title, self.lanes, self.top, self.notes = pid, title, lanes, 0, []
        # external: a band of outside services that only answer requests (message flows in and out);
        # its boxes have no sequence flow, so the start/end/reachability checks skip it
        self.external = external
        self.gap_before = None    # extra space above this pool (used between stacked sections)

    def lane_index(self, ref):
        if isinstance(ref, int):
            return ref
        for i, l in enumerate(self.lanes):
            if l.name == ref:
                return i
        raise ValueError(f"pool {self.id!r} has no lane named {ref!r}")

    def lane_top(self, i):
        return self.top + sum(l.h for l in self.lanes[:i])

    @property
    def bottom(self):
        return self.top + sum(l.h for l in self.lanes)


class Node:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Flow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Geo:
    """Shape sizes for one output. Vertical positions are shared; widths/heights differ per output."""
    def __init__(self, mode):
        svg = mode == "svg"
        self.mode = mode
        self.pool_w = 48 if svg else 30
        self.lane_col = 175 if svg else 30
        self.pad = 90 if svg else 70
        self.pitch, self.bw = 176, 122
        self.bh = 54 if svg else 60       # svg boxes keep a 14 px strip at the top for the task-type icon
        self.r = 15 if svg else 18
        self.gw, self.gh = (56, 36) if svg else (25, 25)

    def content_x(self):
        return self.pool_w + self.lane_col

    def cx(self, col):
        return self.content_x() + self.pad + (col - 1) * self.pitch + self.pitch / 2


# ---------------------------------------------------------------- diagram
class Diagram:
    def __init__(self, title, description="", gap=70):
        self.title, self.description, self.gap = title, description, gap
        self.pools, self.nodes, self.flows, self.msgs, self.legend_notes = [], {}, [], [], []
        self.sections = []
        self.annotations = []
        self._ids = set()

    # ---- building API
    @staticmethod
    def lane(name, sub="", color="system", h=176, main=30, center=True):
        return Lane(name, sub, color, h, main, center)

    def pool(self, pid, title, lanes, external=False):
        self._new_id(pid)
        p = Pool(pid, title, lanes, external)
        self.pools.append(p)
        return p

    def _pool(self, ref):
        if isinstance(ref, Pool):
            return ref
        for p in self.pools:
            if p.id == ref:
                return p
        raise ValueError(f"no pool {ref!r}")

    def _new_id(self, nid):
        if not re.match(r"^[A-Za-z_][\w\-.]*$", nid):
            raise ValueError(f"id {nid!r} must start with a letter and use letters, digits, _ - .")
        if nid in self._ids:
            raise ValueError(f"duplicate id {nid!r}")
        self._ids.add(nid)

    def _node(self, nid, kind, pool, lane, col, name, row=0, dy=0, **kw):
        self._new_id(nid)
        p = self._pool(pool)
        n = Node(id=nid, kind=kind, pool=p, lane=p.lane_index(lane), col=col, row=row, dy=dy, name=name,
                 sub=kw.pop("sub", ""), ttype=kw.pop("type", None), event=kw.pop("event", None),
                 label_pos=kw.pop("label", "below"), attached=None, edge=None, duration=None)
        n.__dict__.update(kw)
        self.nodes[nid] = n
        return n

    def start(self, nid, pool, lane, col, name="", row=0, message=False, timer=None, label="below", dy=0):
        return self._node(nid, "start", pool, lane, col, name, row, dy, label=label,
                          event="message" if message else ("timer" if timer else None), duration=timer)

    def end(self, nid, pool, lane, col, name="", row=0, label="below", dy=0, event=None):
        """event=None: plain end. event="error": the process ends with an error (a failure outcome)."""
        if event not in (None, "error"):
            raise ValueError(f"end event {nid!r}: event must be None or 'error'")
        return self._node(nid, "end", pool, lane, col, name, row, dy, label=label, event=event)

    def catch(self, nid, pool, lane, col, name="", row=0, message=True, timer=None, label="below", dy=0):
        return self._node(nid, "catch", pool, lane, col, name, row, dy, label=label,
                          event="timer" if timer else "message", duration=timer)

    def task(self, nid, pool, lane, col, name, sub="", type="user", row=0, dy=0, implicit_end=False):
        """implicit_end=True: the path may stop at this task with no end event (the user asked for it;
        BPMN tolerates it, Camunda's linter warns). Checks 9-deadend and 9-noend accept it."""
        return self._node(nid, "task", pool, lane, col, name, row, dy, sub=sub, type=type, implicit_end=implicit_end)

    def link_to(self, nid, pool, lane, col, link, row=0, label="below", dy=0):
        """'Go to' connector (link throw event): replaces a long back-arrow. `link` like 'A: Rework'."""
        return self._node(nid, "throw", pool, lane, col, link, row, dy, label=label, event="link")

    def link_from(self, nid, pool, lane, col, link, row=0, label="below", dy=0):
        """'Continue from' connector (link catch event) matching link_to calls with the same `link` text."""
        return self._node(nid, "catch", pool, lane, col, link, row, dy, label=label, event="link")

    def gateway(self, nid, pool, lane, col, question="", row=0, dy=0, type="exclusive"):
        """type "exclusive": a decision, one path (the question goes inside, every exit is labelled).
        "parallel": all paths at once (a split or the join that waits for all). "inclusive": one or more
        paths. Parallel and inclusive diamonds carry a marker; their optional text sits outside."""
        if type not in GATEWAY_TAGS:
            raise ValueError(f"gateway {nid!r}: type must be one of {', '.join(GATEWAY_TAGS)}")
        return self._node(nid, "gateway", pool, lane, col, question, row, dy, gtype=type)

    def timer(self, nid, attached_to, name="", duration=None, edge="bottom-right", label="right"):
        """Boundary timer on a task: when it fires the task is cancelled and the timer's flow is taken."""
        return self.boundary(nid, attached_to, name, "timer", edge, label, duration)

    def boundary(self, nid, attached_to, name="", event="message", edge="bottom-right", label="right", duration=None):
        """Event on a task's edge that interrupts it, e.g. 'Approver recalls' (message) or a timer."""
        t = self.nodes[attached_to]
        n = self._node(nid, "boundary", t.pool, t.lane, t.col, name, t.row, 0, label=label, event=event)
        n.attached, n.edge, n.duration = attached_to, edge, duration
        return n

    def flow(self, src, tgt, label="", exit=None, entry=None, channel=None, dashed=False,
             exit_dx=None, entry_dx=None, label_at=None):
        f = Flow(id=f"Flow_{len(self.flows) + 1}", src=src, tgt=tgt, label=label, exit=exit, entry=entry,
                 channel=channel, dashed=dashed, exit_dx=exit_dx, entry_dx=entry_dx, label_at=label_at, msg=False)
        self.flows.append(f)
        return f

    def message(self, src, tgt, label="", dx=0, tdx=None, channel=None, label_side="right"):
        f = Flow(id=f"Message_{len(self.msgs) + 1}", src=src, tgt=tgt, label=label, dx=dx, tdx=tdx,
                 channel=channel, label_side=label_side, msg=True)
        self.msgs.append(f)
        return f

    def lane_y(self, pool, lane, offset):
        """Absolute y of a point `offset` px below the top of a lane, for channel=... values."""
        self._place_pools()
        p = self._pool(pool)
        idx = p.lane_index(lane)
        y = p.lane_top(idx) + offset
        return YRef(y, p, offset, idx)

    def include(self, other, prefix, title_prefix="", gap_before=None):
        """Stack another diagram's pools below this one's (ids get `prefix`, pool titles `title_prefix`).
        Used to put several levels (L1, L2, L3) on one Camunda canvas."""
        pmap = {}
        for i, p in enumerate(other.pools):
            q = self.pool(prefix + p.id, title_prefix + p.title, p.lanes, p.external)
            q.notes = list(p.notes)
            if i == 0 and gap_before is not None:
                q.gap_before = gap_before
            pmap[id(p)] = q
        def remap(ch):
            if isinstance(ch, YRef):
                return YRef(float(ch), pmap[id(ch.pool)], ch.rel, ch.lane)
            if isinstance(ch, tuple):
                return tuple(remap(c) for c in ch)
            return ch
        for n in other.nodes.values():
            self._new_id(prefix + n.id)
            m = Node(**n.__dict__)
            m.id, m.pool = prefix + n.id, pmap[id(n.pool)]
            if n.attached:
                m.attached = prefix + n.attached
            self.nodes[m.id] = m
        for fl in other.flows:
            g = Flow(**fl.__dict__)
            g.id, g.src, g.tgt, g.channel = prefix + fl.id, prefix + fl.src, prefix + fl.tgt, remap(fl.channel)
            self.flows.append(g)
        for ms in other.msgs:
            g = Flow(**ms.__dict__)
            g.id, g.src, g.tgt, g.channel = prefix + ms.id, prefix + ms.src, prefix + ms.tgt, remap(ms.channel)
            self.msgs.append(g)
        self.legend_notes += [f"{title_prefix}{t}" for t in other.legend_notes]
        for a in other.annotations:
            self.annotations.append(dict(a, id=prefix + a["id"], node=prefix + a["node"]))
        first = pmap[id(other.pools[0])] if other.pools else None
        for sec in other.sections:
            self.sections.append({"col": sec["col"], "text": sec["text"],
                                  "pool": pmap[id(sec["pool"])] if sec["pool"] else first})

    def note(self, pool, lines):
        self._pool(pool).notes.extend(lines if isinstance(lines, list) else [lines])

    def legend_note(self, text):
        self.legend_notes.append(text)

    def annotate(self, node, text, dx=0, dy=-80, width=230):
        """Text annotation linked to one step by a dotted line (BPMN textAnnotation + association).
        The note's centre sits dx/dy px from the step's centre; text wraps to `width`."""
        self.annotations.append({"id": f"Annot_{len(self.annotations) + 1}", "node": node, "text": text,
                                 "dx": dx, "dy": dy, "w": width})

    def _annot_geom(self, a, g):
        """(box, text lines, association line points) of an annotation for geometry `g`."""
        words, lines, cur = a["text"].split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if cur and text_w(t) > a["w"] - 12:
                lines.append(cur)
                cur = w
            else:
                cur = t
        if cur:
            lines.append(cur)
        n = self.nodes[a["node"]]
        cx, cy = self._center(n, g)
        w, h = a["w"], 10 + 15 * len(lines)
        x0, y0 = cx + a["dx"] - w / 2, cy + a["dy"] - h / 2
        box = (x0, y0, x0 + w, y0 + h)
        hw, hh = self._half(n, g)
        ax = min(max(cx, x0 + 8), x0 + w - 8)     # the line meets the note's edge facing the step
        if box[3] <= cy - hh:            # note above the step
            start, end = (ax, y0 + h), (ax if abs(ax - cx) < hw - 6 else cx, cy - hh)
        elif box[1] >= cy + hh:          # note below
            start, end = (ax, y0), (ax if abs(ax - cx) < hw - 6 else cx, cy + hh)
        else:                            # note beside
            start = (x0, y0 + h / 2) if x0 > cx else (x0 + w, y0 + h / 2)
            end = (cx + hw if x0 > cx else cx - hw, cy)
        return box, lines, [start, end]

    def section(self, col, text, pool=None):
        """A section title written just above a pool (default: the top pool), starting at column `col`.
        Use it when one diagram holds several separate stories, e.g. "A. Name screening"."""
        self.sections.append({"col": col, "text": text, "pool": self._pool(pool) if pool else None})

    # ---- layout
    def _place_pools(self):
        """Lay pools out top to bottom. Each lane's contents are measured as one block (rows, labels in
        both the SVG and the Camunda layout, edge events, loop corridors); a lane too short for its block
        grows, and the block is centred so the space above and below is equal."""
        self._shift = {}
        rel = lambda n: (n.pool.lanes[n.lane].main if n.row == 0 else n.pool.lanes[n.lane].main + ROW_GAP) + 23 + n.dy
        ext = {}
        def grow(k, top, bot):
            lo, hi = ext.get(k, (top, bot))
            ext[k] = (min(lo, top), max(hi, bot))
        for n in self.nodes.values():
            if n.kind == "boundary":
                t = self.nodes[n.attached]
                cy = rel(t)
                if n.edge.startswith("top"):
                    grow((t.pool.id, t.lane), cy - 30 - 18 - 4, cy)
                else:
                    grow((t.pool.id, t.lane), cy, cy + 30 + 18 + (20 if n.label_pos == "below" else 4))
                continue
            cy = rel(n)
            half = {"task": 30, "gateway": 36}.get(n.kind, 18)
            top, bot = cy - half, cy + half
            if n.kind == "gateway":
                top = cy - 25 - 28        # Camunda writes the question above the diamond
            elif n.kind != "task" and n.name:
                if n.label_pos == "below":
                    bot = cy + 36
                elif n.label_pos == "above":
                    top = cy - 36
            grow((n.pool.id, n.lane), top, bot)
        # loops that return over the top (or under the bottom) of a lane need their corridor inside the block
        g = Geo("svg")
        for p in self.pools:              # provisional tops so _sides can compare positions
            pass
        for fl in self.flows:
            if fl.channel is not None or fl.src not in self.nodes or fl.tgt not in self.nodes:
                continue
            ex, en = self._sides(fl, g)
            if ex == en and ex in "tb":
                for nid in (fl.src, fl.tgt):
                    n = self.nodes[nid]
                    if n.kind == "boundary":
                        continue
                    half = {"task": 30, "gateway": 36}.get(n.kind, 18)
                    cy = rel(n)
                    grow((n.pool.id, n.lane), cy - half - 46, cy) if ex == "t" else \
                        grow((n.pool.id, n.lane), cy, cy + half + 46)
        for p in self.pools:
            for i, l in enumerate(p.lanes):
                if (p.id, i) in ext:
                    lo, hi = ext[(p.id, i)]
                    need = (hi - lo) + 2 * LANE_PAD
                    if l.h < need:
                        l.h = int(math.ceil(need))
        y = 0
        for p in self.pools:
            if p.gap_before is not None and p is not self.pools[0]:
                y += p.gap_before - self.gap
            p.top = y
            y = p.bottom + self.gap
        for p in self.pools:
            for i, l in enumerate(p.lanes):
                if not l.center or (p.id, i) not in ext:
                    continue
                lo, hi = ext[(p.id, i)]
                shift = l.h / 2 - (lo + hi) / 2
                shift = max(min(shift, l.h - LANE_PAD - hi), LANE_PAD - lo)   # keep the padding
                self._shift[(p.id, i)] = shift

    def _cy_raw(self, n):
        lane = n.pool.lanes[n.lane]
        return n.pool.lane_top(n.lane) + (lane.main if n.row == 0 else lane.main + ROW_GAP) + 23 + n.dy

    def _cy(self, n):
        if n.kind == "boundary":
            return None
        return self._cy_raw(n) + getattr(self, "_shift", {}).get((n.pool.id, n.lane), 0)

    def _half(self, n, g):
        if n.kind == "task":
            return g.bw / 2, g.bh / 2
        if n.kind == "gateway":
            return g.gw, g.gh
        return g.r, g.r

    def _center(self, n, g):
        if n.kind == "boundary":
            t = self.nodes[n.attached]
            tx, ty = self._center(t, g)
            hw, hh = self._half(t, g)
            return {"bottom-right": (tx + hw - 10, ty + hh), "bottom-left": (tx - hw + 10, ty + hh),
                    "bottom": (tx, ty + hh), "top-right": (tx + hw - 6, ty - hh),
                    "top-left": (tx - hw + 6, ty - hh), "top": (tx, ty - hh)}[n.edge]
        return g.cx(n.col), self._cy(n)

    def _bbox(self, n, g, pad=0):
        x, y = self._center(n, g)
        hw, hh = self._half(n, g)
        return (x - hw - pad, y - hh - pad, x + hw + pad, y + hh + pad)

    def _side_point(self, n, side, off, g):
        x, y = self._center(n, g)
        hw, hh = self._half(n, g)
        round_ = n.kind in ("start", "end", "catch", "boundary", "throw")
        if side in "tb":
            s = -1 if side == "t" else 1
            if round_:
                return x + off, y + s * math.sqrt(max(g.r ** 2 - off ** 2, 0))
            if n.kind == "gateway":
                return x + off, y + s * hh * (1 - min(abs(off) / hw, 1))
            return x + off, y + s * hh
        s = 1 if side == "r" else -1
        if round_:
            return x + s * math.sqrt(max(g.r ** 2 - off ** 2, 0)), y + off
        if n.kind == "gateway":
            return x + s * hw * (1 - min(abs(off) / hh, 1)), y + off
        return x + s * hw, y + off

    def _sides(self, f, g):
        s, t = self.nodes[f.src], self.nodes[f.tgt]
        (sx, sy), (tx, ty) = self._center(s, g), self._center(t, g)
        dx, dy = tx - sx, ty - sy
        if f.exit and f.entry:
            return f.exit, f.entry
        if s.kind == "boundary":
            ex, en = "b", ("l" if dx > 0 else "r")
        elif abs(dy) < 1:
            # same row: go straight if nothing sits in between, otherwise detour (forward below, back over the top)
            lo, hi = sorted((sx, tx))
            blocked = any(n.pool is s.pool and n.id not in (s.id, t.id) and n.kind != "boundary"
                          and self._bbox(n, g)[1] < sy < self._bbox(n, g)[3]
                          and lo < self._center(n, g)[0] < hi for n in self.nodes.values())
            if not blocked:
                ex, en = ("r", "l") if dx > 0 else ("l", "r")
            else:
                ex, en = ("b", "b") if dx > 0 else ("t", "t")
        elif abs(dx) < 1:
            ex, en = ("b", "t") if dy > 0 else ("t", "b")
        elif s.kind == "gateway":
            ex, en = ("b" if dy > 0 else "t"), ("l" if dx > 0 else "r")
        elif dx > 0:
            ex, en = "r", ("t" if dy > 0 else "b")
        else:
            ex, en = ("b" if dy > 0 else "t"), "r"
        return f.exit or ex, f.entry or en

    def _route(self, p0, s0, p1, s1, channel):
        h0, h1 = s0 in "lr", s1 in "lr"
        if isinstance(channel, tuple):
            # two-bend detour: (x, y) of the corridor. Horizontal exit: across to x, along y, into the target.
            cx_, cy_ = channel
            if h0 and not h1:
                pts = [p0, (cx_, p0[1]), (cx_, cy_), (p1[0], cy_), p1]
            elif not h0 and h1:
                pts = [p0, (p0[0], cy_), (cx_, cy_), (cx_, p1[1]), p1]
            elif h0 and h1:
                pts = [p0, (cx_, p0[1]), (cx_, cy_), (p1[0] + (-30 if s1 == "l" else 30), cy_),
                       (p1[0] + (-30 if s1 == "l" else 30), p1[1]), p1]
            else:
                pts = [p0, (p0[0], cy_), (cx_, cy_), (cx_, p1[1] + (-30 if s1 == "t" else 30)),
                       (p1[0], p1[1] + (-30 if s1 == "t" else 30)), p1]
            out = [pts[0]]
            for q in pts[1:]:
                if abs(q[0] - out[-1][0]) > 0.01 or abs(q[1] - out[-1][1]) > 0.01:
                    out.append(q)
            return out
        if h0 and h1:
            if abs(p0[1] - p1[1]) < 0.5:
                pts = [p0, p1]
            else:
                xm = channel if channel is not None else (p0[0] + p1[0]) / 2
                pts = [p0, (xm, p0[1]), (xm, p1[1]), p1]
        elif h0:
            pts = [p0, (p1[0], p0[1]), p1]
        elif h1:
            pts = [p0, (p0[0], p1[1]), p1]
        elif abs(p0[0] - p1[0]) < 0.5:
            pts = [p0, p1]
        else:
            if channel is None:
                if s0 == "t" and s1 == "t":
                    channel = min(p0[1], p1[1]) - 40
                elif s0 == "b" and s1 == "b":
                    channel = max(p0[1], p1[1]) + 40
                else:
                    channel = (p0[1] + p1[1]) / 2
            pts = [p0, (p0[0], channel), (p1[0], channel), p1]
        out = [pts[0]]
        for q in pts[1:]:
            if abs(q[0] - out[-1][0]) > 0.01 or abs(q[1] - out[-1][1]) > 0.01:
                out.append(q)
        return out

    def _gap_mid(self, pa, pb):
        up, lo = (pa, pb) if pa.top < pb.top else (pb, pa)
        return (up.bottom + lo.top) / 2

    def _layout(self, g):
        """Return {flow_id: points} for sequence and message flows in geometry g."""
        sides = {f.id: self._sides(f, g) for f in self.flows}
        # ends per (node, side): fixed offsets (message flows, explicit dx) and auto ones to spread
        ends = {}
        def add(nid, side, flow, which, off, other):
            ends.setdefault((nid, side), []).append([flow, which, off, other])
        msg_geo = {}
        for m in self.msgs:
            s, t = self.nodes[m.src], self.nodes[m.tgt]
            down = t.pool.top > s.pool.top
            ss, ts = ("b", "t") if down else ("t", "b")
            sx, _ = self._center(s, g)
            tx, _ = self._center(t, g)
            x = sx + (m.dx or 0)
            hw = self._half(t, g)[0]
            reach = {"task": hw - 10, "gateway": 0}.get(t.kind, g.r * 0.5)
            toff = (x - tx) if (m.tdx is None and abs(x - tx) <= reach) else (m.tdx or 0)
            msg_geo[m.id] = (ss, ts, m.dx or 0, toff)
            add(m.src, ss, m, "src", m.dx or 0, tx)
            add(m.tgt, ts, m, "tgt", toff, sx)
        for f in self.flows:
            ex, en = sides[f.id]
            s, t = self.nodes[f.src], self.nodes[f.tgt]
            add(f.src, ex, f, "src", f.exit_dx, self._center(t, g)[0 if ex in "tb" else 1])
            add(f.tgt, en, f, "tgt", f.entry_dx, self._center(s, g)[0 if en in "tb" else 1])
        offs = {}
        for (nid, side), lst in ends.items():
            n = self.nodes[nid]
            fixed = [e[2] for e in lst if e[2] is not None]
            auto = [e for e in lst if e[2] is None]
            for e in lst:
                if e[2] is not None:
                    offs[(e[0].id, e[1])] = e[2]
            if not auto:
                continue
            if n.kind != "task" or len(auto) + len(fixed) == 1:
                for e in auto:
                    offs[(e[0].id, e[1])] = 0
                continue
            step = 40 if side in "tb" else 12
            room = (g.bw if side in "tb" else g.bh) - 16       # keep every end on the box side
            if len(auto) + len(fixed) > 1:
                step = min(step, room / (len(auto) + len(fixed) - 1))
            # an arrow that arrives in a straight line (source aligned with this node) keeps the centre,
            # so it stays straight; the others move aside toward their own source
            c0 = self._center(n, g)[0 if side in "tb" else 1]
            straight = [e for e in auto if abs(e[3] - c0) < 1]
            if straight and not any(abs(fx) < step / 2 for fx in fixed):
                offs[(straight[0][0].id, straight[0][1])] = 0
                rest = [e for e in auto if e is not straight[0]]
                below = sorted([e for e in rest if e[3] > c0], key=lambda e: e[3])
                above = sorted([e for e in rest if e[3] <= c0], key=lambda e: -e[3])
                for i, e in enumerate(below):
                    offs[(e[0].id, e[1])] = step * (0.75 + i * 0.75)
                for i, e in enumerate(above):
                    offs[(e[0].id, e[1])] = -step * (0.75 + i * 0.75)
                continue
            if not fixed:
                cands = [(i - (len(auto) - 1) / 2) * step for i in range(len(auto))]
            else:
                pool_ = [0, -step * .75, step * .75, -step * 1.5, step * 1.5, -step * 2.2, step * 2.2]
                cands = sorted([c for c in pool_ if all(abs(c - fx) >= step / 2 for fx in fixed)][:len(auto)])
            for e, c in zip(sorted(auto, key=lambda e: e[3]), sorted(cands)):
                offs[(e[0].id, e[1])] = c
        pts = {}
        for f in self.flows:
            ex, en = sides[f.id]
            s, t = self.nodes[f.src], self.nodes[f.tgt]
            p0 = self._side_point(s, ex, offs[(f.id, "src")], g)
            p1 = self._side_point(t, en, offs[(f.id, "tgt")], g)
            # channel: x is given in columns (layouts differ in x), y in absolute units (shared)
            ch = f.channel
            if isinstance(ch, tuple):
                ch = (g.cx(ch[0]), _resolve_y(ch[1]))
            elif ch is not None and ex in "lr" and en in "lr":
                ch = g.cx(ch)
            elif ch is not None:
                ch = _resolve_y(ch)
            pts[f.id] = self._route(p0, ex, p1, en, ch)
        for m in self.msgs:
            s, t = self.nodes[m.src], self.nodes[m.tgt]
            ss, ts, so, to = msg_geo[m.id]
            p0 = self._side_point(s, ss, so, g)
            p1 = self._side_point(t, ts, to, g)
            if abs(p0[0] - p1[0]) < 0.5:
                pts[m.id] = [p0, p1]
            else:
                ym = _resolve_y(m.channel) if m.channel is not None else self._gap_mid(s.pool, t.pool)
                pts[m.id] = [p0, (p0[0], ym), (p1[0], ym), p1]
        return pts

    def _pool_right(self, g, pts):
        """Pools linked by message flows share one width; each group is as wide as its content needs."""
        parent = {p.id: p.id for p in self.pools}
        def find(a):
            while parent[a] != a:
                a = parent[a]
            return a
        for m in self.msgs:
            parent[find(self.nodes[m.src].pool.id)] = find(self.nodes[m.tgt].pool.id)
        need = {}
        for n in self.nodes.values():
            x1 = self._bbox(n, g)[2]
            for lb in self._node_labels(n, g):
                x1 = max(x1, lb["box"][2])
            k = find(n.pool.id)
            need[k] = max(need.get(k, 0), x1 + 60)
        for f in self.flows + self.msgs:
            k = find(self.nodes[f.src].pool.id)
            need[k] = max(need.get(k, 0), max(x for x, _ in pts[f.id]) + 40)
        return {p.id: need.get(find(p.id), g.cx(2)) for p in self.pools}

    # ---- labels (positions + approximate boxes, used for drawing and for checks)
    def _gateway_lines(self, q):
        if "\n" in q:
            return q.split("\n")[:2]
        if len(q) <= 12 or " " not in q:
            return [q]
        mid = len(q) / 2
        cut = min((i for i, ch in enumerate(q) if ch == " "), key=lambda i: abs(i - mid))
        return [q[:cut], q[cut + 1:]]

    def _node_labels(self, n, g):
        """External text labels of an event (gateway text sits inside the diamond in the SVG)."""
        if n.kind in ("task", "gateway") or not n.name:
            if n.kind == "gateway" and n.name and (g.mode == "bpmn" or n.gtype != "exclusive"):
                # Camunda writes the question outside the diamond: put it on a side no arrow uses
                x, y = self._center(n, g)
                used = set()
                for f in self.flows:
                    if f.src == n.id or f.tgt == n.id:
                        ex, en = self._sides(f, g)
                        used.add(ex if f.src == n.id else en)
                for m in self.msgs:
                    if m.src == n.id or m.tgt == n.id:
                        used.add("t" if self.nodes[m.tgt if m.src == n.id else m.src].pool.top < n.pool.top else "b")
                txt = n.name.replace("\n", " ")
                w = max(60, text_w(txt) + 6)
                if "t" not in used:
                    box = (x - w / 2, y - g.gh - 26, x + w / 2, y - g.gh - 8)
                elif "b" not in used:
                    box = (x - w / 2, y + g.gh + 6, x + w / 2, y + g.gh + 24)
                else:
                    # top-left diagonal: arrows leave a diamond at its corners, and exit labels sit to the
                    # right of vertical arrows, so this quadrant is the one most likely to be empty
                    box = (x - g.gw / 2 - w, y - g.gh - 20, x - g.gw / 2, y - g.gh - 2)
                return [{"x": x, "y": box[3] - 4, "anchor": "middle", "text": txt, "box": box, "owner": n.id}]
            return []
        x, y = self._center(n, g)
        bold = n.kind == "end"
        size = 13 if bold else 12
        w = text_w(n.name, size, bold)
        r = g.r
        if n.label_pos == "left":
            lx, ly, anchor = x - r - 6, (y + 14 if n.kind == "boundary" else y + 4), "end"
            box = (lx - w, ly - 11, lx, ly + 3)
        elif n.label_pos == "right":
            lx, ly, anchor = x + r + 6, (y + 14 if n.kind == "boundary" else y + 4), "start"
            box = (lx, ly - 11, lx + w, ly + 3)
        elif n.label_pos == "above":
            lx, ly, anchor = x, y - r - 8, "middle"
            box = (lx - w / 2, ly - 11, lx + w / 2, ly + 3)
        else:
            lx, ly, anchor = x, y + r + 15, "middle"
            box = (lx - w / 2, ly - 11, lx + w / 2, ly + 3)
        return [{"x": lx, "y": ly, "anchor": anchor, "text": n.name, "box": box, "owner": n.id,
                 "cls": "ev" if bold else "ts"}]

    def _flow_label(self, f, pts, g):
        if not f.label:
            return None
        w = text_w(f.label)
        if f.msg:
            # put it in the gap between the two pools, beside the segment that crosses it
            s, t = self.nodes[f.src], self.nodes[f.tgt]
            gy = self._gap_mid(s.pool, t.pool)
            x = pts[0][0]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                if abs(x1 - x2) < 0.5 and min(y1, y2) <= gy <= max(y1, y2):
                    x = x1
                    break
            if getattr(f, "label_side", "right") == "left":
                lx, anchor, box = x - 8, "end", (x - 8 - w, gy - 7, x - 8, gy + 7)
            else:
                lx, anchor, box = x + 8, "start", (x + 8, gy - 7, x + 8 + w, gy + 7)
            return {"x": lx, "y": gy + 4, "anchor": anchor, "text": f.label, "box": box, "owner": f.id, "cls": "tm"}
        (x0, y0), (x1, y1) = pts[0], pts[1]
        if f.label_at:
            lx, ly = x0 + f.label_at[0], y0 + f.label_at[1]
            return {"x": lx, "y": ly, "anchor": "start", "text": f.label, "box": (lx, ly - 11, lx + w, ly + 3),
                    "owner": f.id, "cls": "ts"}
        if abs(y0 - y1) < 0.5:
            if abs(x1 - x0) <= 200:
                lx, ly, anchor = (x0 + x1) / 2, y0 - 8, "middle"
                box = (lx - w / 2, ly - 11, lx + w / 2, ly + 3)
            else:
                lx, ly, anchor = (x0 + 10, y0 - 8, "start") if x1 > x0 else (x0 - 10, y0 - 8, "end")
                box = (lx, ly - 11, lx + w, ly + 3) if anchor == "start" else (lx - w, ly - 11, lx, ly + 3)
        else:
            down = y1 > y0
            lx, ly, anchor = x0 + 7, (y0 + 18 if down else y0 - 8), "start"
            box = (lx, ly - 11, lx + w, ly + 3)
        return {"x": lx, "y": ly, "anchor": anchor, "text": f.label, "box": box, "owner": f.id, "cls": "ts"}

    # ---------------------------------------------------------------- checks
    def check(self):
        errs, warns = [], []
        E = lambda code, msg: errs.append(f"[{code}] {msg}")
        W = lambda code, msg: warns.append(f"[{code}] {msg}")
        g = Geo("svg")
        self._place_pools()
        pts = self._layout(g)
        right = self._pool_right(g, pts)

        # 6. references
        for f in self.flows + self.msgs:
            for end in (f.src, f.tgt):
                if end not in self.nodes:
                    E("6-ref", f"{f.id} points to unknown element {end!r}")
        if errs:
            return errs, warns, pts
        # 7 / 8. sequence vs message flows
        for f in self.flows:
            if self.nodes[f.src].pool is not self.nodes[f.tgt].pool:
                E("7-pool", f"sequence flow {f.src} -> {f.tgt} crosses pools; use d.message() between pools")
        for m in self.msgs:
            s, t = self.nodes[m.src], self.nodes[m.tgt]
            if s.pool is t.pool:
                E("7-pool", f"message flow {m.src} -> {m.tgt} stays inside one pool; use d.flow()")
            if s.kind == "gateway" or t.kind == "gateway":
                E("8-gateway", f"message flow {m.src} -> {m.tgt} touches a gateway; land it on a task or event before the diamond")
            if t.kind == "end":
                E("8-msg-end", f"message flow into end event {m.tgt}; an end event cannot receive")
            if s.kind == "start":
                E("8-msg-start", f"message flow out of start event {m.src}; a start event cannot send")
            if t.kind in ("start", "catch") and t.event != "message":
                W("8-msg-def", f"{m.tgt} receives a message but is not a message event (use message=True)")
        # 11. boundary timers
        for n in self.nodes.values():
            if n.kind == "boundary" and self.nodes[n.attached].kind != "task":
                E("11-timer", f"timer {n.id} must sit on a task, not on {n.attached}")
        # 13. link connectors: every 'go to X' has exactly one 'continue from X' in the same pool, and vice versa
        for n in self.nodes.values():
            if n.event != "link":
                continue
            same = [m for m in self.nodes.values() if m.event == "link" and m.name == n.name and m.pool is n.pool]
            if n.kind == "throw" and sum(m.kind == "catch" for m in same) != 1:
                E("13-link", f"'go to {n.name}' ({n.id}) needs exactly one link_from with the same text in its pool")
            if n.kind == "catch" and not any(m.kind == "throw" for m in same):
                E("13-link", f"'continue from {n.name}' ({n.id}) has no link_to pointing at it")
            if any(f.src == n.id for f in self.flows) and n.kind == "throw":
                E("13-link", f"'go to {n.name}' ({n.id}) cannot have an outgoing arrow")
            if any(f.tgt == n.id for f in self.flows) and n.kind == "catch":
                E("13-link", f"'continue from {n.name}' ({n.id}) cannot have an incoming arrow")
            if any(m.src == n.id or m.tgt == n.id for m in self.msgs):
                E("13-link", f"link connector {n.id} cannot send or receive messages")
        # 9 / 10. per-pool reachability and gateways
        outs, ins = {}, {}
        for f in self.flows:
            outs.setdefault(f.src, []).append(f)
            ins.setdefault(f.tgt, []).append(f)
        for p in self.pools:
            pn = [n for n in self.nodes.values() if n.pool is p]
            if not pn:
                continue
            if p.external:
                for n in pn:
                    if n.kind != "task":
                        E("14-external", f"{n.id}: an external pool holds only service boxes (tasks)")
                    if any(f.src == n.id or f.tgt == n.id for f in self.flows):
                        E("14-external", f"{n.id}: external services talk only through message flows")
                    if not any(m.src == n.id or m.tgt == n.id for m in self.msgs):
                        W("14-external", f"{n.id}: external service with no request or response arrow")
                continue
            starts = [n.id for n in pn if n.kind == "start"]
            if not starts:
                W("9-start", f"pool '{p.title}' has no start event; flow begins at elements with no incoming arrow")
            links = {}
            for n in pn:
                if n.event == "link" and n.kind == "catch":
                    links.setdefault(n.name, []).append(n.id)
            def nxt(a):
                out_ = [f.tgt for f in outs.get(a, [])]
                out_ += [b.id for b in pn if b.kind == "boundary" and b.attached == a]
                if self.nodes[a].kind == "throw":
                    out_ += links.get(self.nodes[a].name, [])
                return out_
            entry = set(starts) | {n.id for n in pn if n.kind not in ("boundary",) and not ins.get(n.id)
                                   and not (n.kind == "catch" and n.event == "link")}
            seen, stack = set(), list(entry)
            while stack:
                a = stack.pop()
                if a in seen:
                    continue
                seen.add(a)
                stack += nxt(a)
            for n in pn:
                if n.id not in seen:
                    E("9-reach", f"{n.id} ('{n.name}') cannot be reached from a start")
                if n.kind not in ("end", "throw") and not outs.get(n.id) and not getattr(n, "implicit_end", False):
                    E("9-deadend", f"{n.id} ('{n.name}') has no outgoing arrow; add an end event")
            ends_ = {n.id for n in pn if n.kind == "end" or getattr(n, "implicit_end", False)}
            for n in pn:
                seen2, stack = set(), [n.id]
                while stack:
                    a = stack.pop()
                    if a in seen2:
                        continue
                    seen2.add(a)
                    stack += nxt(a)
                if n.kind != "end" and not (seen2 & ends_) and (outs.get(n.id) or n.kind == "throw"):
                    E("9-noend", f"from {n.id} ('{n.name}') no end event can be reached (loop with no exit?)")
            for n in pn:
                if n.kind == "gateway":
                    o = outs.get(n.id, [])
                    if len(o) >= 2 and n.gtype != "parallel" and any(not f.label for f in o):
                        E("10-gw-label", f"decision {n.id} ('{n.name}'): every exit needs a label (e.g. yes/no)")
                    if len(o) == 1 and len(ins.get(n.id, [])) == 1:
                        W("10-gw-pointless", f"gateway {n.id} has one way in and one way out")
                    if len(o) >= 2 and n.gtype == "exclusive" and not n.name.strip().endswith("?"):
                        W("style-question", f"decision {n.id}: write it as a question ending in '?'")
        # style: who-does-it belongs to the lane
        for n in self.nodes.values():
            if n.kind == "task" and re.search(r"\bby (the )?[A-Z]\w*|\bby (PM|RM|staff|system)\b", f"{n.name} {n.sub}"):
                W("style-who", f"{n.id}: '{n.name} / {n.sub}' says who does it; the lane already shows that")
            if n.kind == "task" and n.ttype == "subprocess" and n.sub:
                W("style-sub-detail", f"{n.id}: a collapsed sub-process shows its + marker where the detail line sits; "
                                      "put the detail in the name or leave it out")

        # 1. text fits
        for n in self.nodes.values():
            if n.kind == "task":
                for txt, size, bold in ((n.name, 14, True), (n.sub, 12, False)):
                    if txt and text_w(txt, size, bold) > g.bw - 4:
                        E("1-text", f"{n.id}: '{txt}' is too wide for its box ({text_w(txt, size, bold):.0f} > {g.bw - 4}px); shorten it")
            if n.kind == "gateway" and n.gtype == "exclusive":
                lines = self._gateway_lines(n.name)
                for i, ln in enumerate(lines):
                    off = 0 if len(lines) == 1 else (-7 if i == 0 else 8)
                    avail = 2 * g.gw * (1 - abs(off) / g.gh) - 10
                    if text_w(ln) > avail:
                        E("1-text", f"decision {n.id}: line '{ln}' does not fit in the diamond; shorten or split with \\n")
        # geometry collections
        nboxes = {n.id: self._bbox(n, g) for n in self.nodes.values()}
        labels = []
        for n in self.nodes.values():
            labels += self._node_labels(n, g)
        for f in self.flows + self.msgs:
            lb = self._flow_label(f, pts[f.id], g)
            if lb:
                labels.append(lb)
        for a in self.annotations:
            if a["node"] not in self.nodes:
                E("6-ref", f"annotation points to unknown step '{a['node']}'")
                continue
            box, _, _ = self._annot_geom(a, g)
            labels.append({"box": box, "text": "note: " + a["text"][:30], "owner": a["node"]})
            an = self.nodes[a["node"]]
            ob = self._bbox(an, g, 6)
            if box[0] < ob[2] and ob[0] < box[2] and box[1] < ob[3] and ob[1] < box[3]:
                E("4-annot-own", f"the note on {a['node']} covers the step itself; increase dx or dy")
            lt = an.pool.lane_top(an.lane)
            if box[1] < lt + 2 or box[3] > lt + an.pool.lanes[an.lane].h - 2:
                E("4-annot-lane", f"the note on {a['node']} crosses its lane edge; change dy/dx or give the lane more height")

        def rects_overlap(a, b, pad=0):
            return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad

        def rect_hits_node(r, n):
            x0, y0, x1, y1 = r
            cx, cy = self._center(n, g)
            if n.kind == "gateway":
                inside = lambda x, y: abs(x - cx) / g.gw + abs(y - cy) / g.gh <= 1
                return any(inside(x, y) for x in (x0, x1) for y in (y0, y1)) or \
                    any(x0 <= vx <= x1 and y0 <= vy <= y1 for vx, vy in
                        ((cx - g.gw, cy), (cx + g.gw, cy), (cx, cy - g.gh), (cx, cy + g.gh))) or \
                    (x0 <= cx <= x1 and y0 <= cy <= y1)
            if n.kind == "task":
                return rects_overlap(r, nboxes[n.id])
            nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
            return (nx - cx) ** 2 + (ny - cy) ** 2 < g.r ** 2

        def seg_hits_rect(p, q, r, shrink=0):
            x0, y0, x1, y1 = r[0] + shrink, r[1] + shrink, r[2] - shrink, r[3] - shrink
            if abs(p[1] - q[1]) < 0.5:
                return y0 < p[1] < y1 and min(p[0], q[0]) < x1 and max(p[0], q[0]) > x0
            return x0 < p[0] < x1 and min(p[1], q[1]) < y1 and max(p[1], q[1]) > y0

        ids = list(self.nodes)
        # 4. shapes overlapping each other / leaving their lane
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                na, nb = self.nodes[a], self.nodes[b]
                if na.kind == "boundary" and na.attached == b or nb.kind == "boundary" and nb.attached == a:
                    continue
                if rects_overlap(self._bbox(na, g, 4), self._bbox(nb, g, 4)):
                    E("4-overlap", f"{a} and {b} overlap; move one to another column or row")
        for n in self.nodes.values():
            if n.kind == "boundary":
                continue
            x0, y0, x1, y1 = nboxes[n.id]
            lt = n.pool.lane_top(n.lane)
            if y0 < lt + 4 or y1 > lt + n.pool.lanes[n.lane].h - 4:
                E("4-lane", f"{n.id} sticks out of lane '{n.pool.lanes[n.lane].name}'; adjust row/dy or lane height")
            if x0 < g.content_x() + 8 or x1 > right[n.pool.id] - 8:
                E("4-pool", f"{n.id} is too close to the pool edge")
        for lb in labels:
            owner = self.nodes.get(lb["owner"])
            pool = owner.pool if owner else self.nodes[next(f for f in self.flows + self.msgs if f.id == lb["owner"]).src].pool
            if lb["owner"] not in {m.id for m in self.msgs}:
                if lb["box"][1] < pool.top + 2 or lb["box"][3] > pool.bottom - 2 or lb["box"][2] > right[pool.id] - 4:
                    E("4-label-edge", f"label '{lb['text']}' touches or leaves its pool")
            for n in self.nodes.values():
                if n.id != lb["owner"] and rect_hits_node(lb["box"], n):
                    E("4-label-shape", f"label '{lb['text']}' overlaps {n.id} ('{n.name}')")
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                if rects_overlap(a["box"], b["box"], 2):
                    E("4-label-label", f"labels '{a['text']}' and '{b['text']}' overlap")
        # a boundary timer must not cover its task's text
        for n in self.nodes.values():
            if n.kind != "boundary":
                continue
            t = self.nodes[n.attached]
            tx, ty = self._center(t, g)
            top = ty - g.bh / 2
            for txt, size, bold, base in ((t.name, 14, True, top + 19), (t.sub, 12, False, top + 36)):
                if not txt:
                    continue
                w = text_w(txt, size, bold)
                if rect_hits_node((tx - w / 2, base - size + 2, tx + w / 2, base + 3), n):
                    E("4-timer-text", f"timer {n.id} covers the text of {t.id}; use edge='bottom-left' "
                                      f"or 'bottom-right', or shorten '{txt}'")
        # sequence flows must stay inside their pool
        for f in self.flows:
            p = self.nodes[f.src].pool
            for x, y in pts[f.id]:
                if y < p.top + 4 or y > p.bottom - 4 or x > right[p.id] - 4:
                    E("4-route-pool", f"arrow {f.src} -> {f.tgt} runs outside its pool; give the lane more room "
                                      f"(Lane main=70) or set channel=")
                    break
        # 5. two arrows to different targets must not run along the same line (they read as one doubled arrow);
        #    arrows merging into the same target may share their last stretch
        allf = self.flows + self.msgs
        def segs(p):
            return list(zip(p, p[1:]))
        for i, fa in enumerate(allf):
            for fb in allf[i + 1:]:
                if fa.tgt == fb.tgt:
                    continue
                hit = False
                for (a0, a1) in segs(pts[fa.id]):
                    for (b0, b1) in segs(pts[fb.id]):
                        if abs(a0[1] - a1[1]) < 0.5 and abs(b0[1] - b1[1]) < 0.5 and abs(a0[1] - b0[1]) < 5:
                            lo, hi = max(min(a0[0], a1[0]), min(b0[0], b1[0])), min(max(a0[0], a1[0]), max(b0[0], b1[0]))
                            hit = hit or hi - lo > 20
                        elif abs(a0[0] - a1[0]) < 0.5 and abs(b0[0] - b1[0]) < 0.5 and abs(a0[0] - b0[0]) < 5:
                            lo, hi = max(min(a0[1], a1[1]), min(b0[1], b1[1])), min(max(a0[1], a1[1]), max(b0[1], b1[1]))
                            hit = hit or hi - lo > 20
                if hit:
                    E("5-same-line", f"arrows {fa.src} -> {fa.tgt} and {fb.src} -> {fb.tgt} run along the same line; "
                                     f"give one of them other exit/entry sides")
        # 15. section titles above the same pool must not overlap
        by_pool = {}
        for sec in self.sections:
            by_pool.setdefault(id(sec["pool"] or self.pools[0]), []).append(sec)
        for secs in by_pool.values():
            secs = sorted(secs, key=lambda q: q["col"])
            for a, b in zip(secs, secs[1:]):
                if g.cx(a["col"]) - 15 + text_w(a["text"], 15, True) > g.cx(b["col"]) - 15 - 20:
                    E("15-section", f"section titles '{a['text']}' and '{b['text']}' overlap; shorten the first or start the second further right")
        # 2 / 3 / 5. arrows
        for f in self.flows + self.msgs:
            p = pts[f.id]
            (ax, ay), (bx, by) = p[-2], p[-1]
            if not f.msg and math.hypot(bx - ax, by - ay) < MIN_ARROW:
                E("2-arrow", f"arrow {f.src} -> {f.tgt}: last segment {math.hypot(bx - ax, by - ay):.0f}px "
                             f"(< {MIN_ARROW}); leave a wider gap or move the target")
            if f.msg and math.hypot(bx - ax, by - ay) < 25:
                E("2-arrow", f"message {f.src} -> {f.tgt}: last segment too short")
            for (x0, y0), (x1, y1) in zip(p[1:-2], p[2:-1]):
                if math.hypot(x1 - x0, y1 - y0) < 14:
                    E("5-kink", f"arrow {f.src} -> {f.tgt} has a small kink ({math.hypot(x1 - x0, y1 - y0):.0f}px jog); "
                                f"align the two ends (same row/column) or set entry_dx/exit_dx=0")
            t = self.nodes[f.tgt]
            tb = self._bbox(t, g, 3)
            if not (tb[0] <= bx <= tb[2] and tb[1] <= by <= tb[3]):
                E("3-dangling", f"arrow {f.src} -> {f.tgt} does not end on its target")
            skip = {f.src, f.tgt}
            for n in self.nodes.values():
                if n.kind == "boundary" and (n.attached in skip or n.id in skip):
                    skip |= {n.id, n.attached}
            for (x0, y0), (x1, y1) in zip(p, p[1:]):
                for n in self.nodes.values():
                    if n.id not in skip and seg_hits_rect((x0, y0), (x1, y1), nboxes[n.id], 2):
                        E("5-through-shape", f"arrow {f.src} -> {f.tgt} runs through {n.id} ('{n.name}')")
                for lb in labels:
                    if lb["owner"] != f.id and seg_hits_rect((x0, y0), (x1, y1), lb["box"], 1):
                        E("5-through-label", f"arrow {f.src} -> {f.tgt} runs through label '{lb['text']}'")
        return sorted(set(errs)), sorted(set(warns)), pts

    # ---------------------------------------------------------------- SVG
    def to_svg(self):
        g = Geo("svg")
        self._place_pools()
        pts = self._layout(g)
        right = self._pool_right(g, pts)
        out = []
        A = out.append
        note_w = max([max(text_w(t, 13) for t in p.notes) + 30 for p in self.pools if p.notes] or [0])
        W = max(right.values()) + note_w
        colors_used = {}
        for p in self.pools:
            for i, l in enumerate(p.lanes):
                if any(n.pool is p and n.lane == i and n.kind == "task" for n in self.nodes.values()):
                    colors_used.setdefault(l.color, [])
                    if l.name and l.name not in colors_used[l.color]:
                        colors_used[l.color].append(l.name)
        legend_lines = 1 + len(self.legend_notes)
        H = self.pools[-1].bottom + 40 + 22 * legend_lines
        MX, MY = 40, 24
        if any((sec["pool"] or self.pools[0]) is self.pools[0] for sec in self.sections):
            MY = 52                       # room for section titles above the top pool
        PW, PH = W + 2 * MX, H + MY
        A(f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 {PW:.0f} {PH:.0f}" '
          f'preserveAspectRatio="xMidYMid meet" role="img" font-family="Segoe UI, Arial, sans-serif">')
        A(f'<title>{escape(self.title)}</title>')
        if self.description:
            A(f'<desc>{escape(self.description)}</desc>')
        A(f'<defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{LINE}"/></marker>'
          f'<marker id="ma" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M1,1 L9,5 L1,9 z" fill="#FFFFFF" stroke="{MUTED}" stroke-width="1"/></marker>'
          f'<marker id="mc" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="8" markerHeight="8"><circle cx="5" cy="5" r="3.5" fill="#FFFFFF" stroke="{MUTED}" stroke-width="1"/></marker>')
        A('<style>.th{font-size:14px;font-weight:600}.ts{font-size:12px}.tm{font-size:12px;font-style:italic}'
          '.ev{font-size:13px;font-weight:600}.ln{font-size:15px;font-weight:600;fill:#2C2C2A}'
          '.pl{font-size:16px;font-weight:600;fill:#2C2C2A}.nt{font-size:13px}.sec{font-size:15px;font-weight:700;fill:#2C2C2A}</style></defs>')
        A(f'<rect width="{PW:.0f}" height="{PH:.0f}" fill="#FFFFFF"/>')
        A(f'<g transform="translate({MX},{MY})">')
        # section titles, just above their pool
        for sec in self.sections:
            p = sec["pool"] or self.pools[0]
            A(f'<text x="{g.cx(sec["col"]) - 15:.1f}" y="{p.top - 14}" class="sec">{escape(sec["text"])}</text>')
        # pools and lanes
        for p in self.pools:
            r = right[p.id]
            for i, l in enumerate(p.lanes):
                y = p.lane_top(i)
                A(f'<rect x="{g.pool_w}" y="{y}" width="{r - g.pool_w}" height="{l.h}" fill="#FFFFFF" stroke="#D3D1C7" stroke-width="0.6"/>')
                if l.name and l.sub:
                    A(f'<text x="{g.pool_w + 14}" y="{y + l.h / 2 - 4}" class="ln">{escape(l.name)}</text>')
                    A(f'<text x="{g.pool_w + 14}" y="{y + l.h / 2 + 14}" class="ts" fill="{MUTED}">{escape(l.sub)}</text>')
                elif l.name:
                    A(f'<text x="{g.pool_w + 14}" y="{y + l.h / 2 + 5}" class="ln">{escape(l.name)}</text>')
            A(f'<line x1="{g.content_x()}" y1="{p.top}" x2="{g.content_x()}" y2="{p.bottom}" stroke="#B4B2A9" stroke-width="1"/>')
            h = p.bottom - p.top
            A(f'<rect x="1" y="{p.top}" width="{g.pool_w - 1}" height="{h}" fill="#E8E6DF" stroke="{MUTED}" stroke-width="1.2"/>')
            cy = p.top + h / 2
            A(f'<text x="{g.pool_w / 2 + 6}" y="{cy}" text-anchor="middle" class="pl" transform="rotate(-90 {g.pool_w / 2 + 6} {cy})">{escape(p.title)}</text>')
            A(f'<rect x="1" y="{p.top}" width="{r - 1}" height="{h}" fill="none" stroke="{MUTED}" stroke-width="1.2"/>')
            for i, t in enumerate(p.notes):
                A(f'<text x="{r + 24}" y="{p.top + 34 + 20 * i}" class="nt" fill="{MUTED}">{escape(t)}</text>')
        # flows under the shapes
        def d_of(p, shorten=2):
            p = list(p)
            (ax, ay), (bx, by) = p[-2], p[-1]
            L = math.hypot(bx - ax, by - ay) or 1
            p[-1] = (bx - (bx - ax) / L * shorten, by - (by - ay) / L * shorten)
            return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in p)
        for f in self.flows:
            da = ' stroke-dasharray="5 3"' if f.dashed else ''
            A(f'<path d="{d_of(pts[f.id])}" fill="none" stroke="{LINE}" stroke-width="1.2"{da} marker-end="url(#ar)"/>')
        for m in self.msgs:
            A(f'<path d="{d_of(pts[m.id], 3)}" fill="none" stroke="{MUTED}" stroke-width="1.1" stroke-dasharray="6 4" marker-start="url(#mc)" marker-end="url(#ma)"/>')
        # shapes
        def envelope(x, y, filled=False, s=1.0):
            w, h = 14 * s, 10 * s
            fill, line = (INK, "#FFFFFF") if filled else ("#FFFFFF", INK)
            A(f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{INK}" stroke-width="0.9"/>')
            A(f'<path d="M{x - w / 2:.1f} {y - h / 2:.1f} L{x:.1f} {y + s:.1f} L{x + w / 2:.1f} {y - h / 2:.1f}" fill="none" stroke="{line}" stroke-width="0.9"/>')
        def clock(x, y):
            A(f'<circle cx="{x}" cy="{y}" r="{g.r - 6}" fill="none" stroke="{INK}" stroke-width="0.9"/>')
            A(f'<path d="M{x} {y} V{y - 6} M{x} {y} H{x + 4}" stroke="{INK}" stroke-width="1"/>')
        def bolt(x, y, filled):
            pts = " ".join(f"{x + dx:.1f},{y + dy:.1f}" for dx, dy in ((-6, 6), (-3, -4), (1, 0), (5, -7), (3, 4), (-1, 0)))
            A(f'<polygon class="error-bolt" points="{pts}" fill="{INK if filled else "#FFFFFF"}" stroke="{INK}" '
              f'stroke-width="0.9" stroke-linejoin="round"/>')
        def task_icon(ttype, ox, oy):
            """BPMN task-type marker, drawn in a 10 x 10 px area whose top-left corner is (ox, oy)."""
            st = f'fill="none" stroke="{INK}" stroke-width="0.9" stroke-linecap="round" stroke-linejoin="round"'
            A(f'<g class="icon-{ttype}">')
            if ttype == "user":
                A(f'<circle cx="{ox + 5}" cy="{oy + 2.6}" r="2.2" {st}/>')
                A(f'<path d="M{ox + 1} {oy + 9.6} Q{ox + 1} {oy + 5.6} {ox + 5} {oy + 5.6} Q{ox + 9} {oy + 5.6} {ox + 9} {oy + 9.6} Z" {st}/>')
            elif ttype == "service":
                A(f'<circle cx="{ox + 5}" cy="{oy + 5}" r="3.7" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="1.7 1.35"/>')
                A(f'<circle cx="{ox + 5}" cy="{oy + 5}" r="2.4" fill="#FFFFFF" stroke="{INK}" stroke-width="0.9"/>')
            elif ttype == "manual":
                A(f'<path d="M{ox + 2.5} {oy + 9.5} V{oy + 5} M{ox + 4.3} {oy + 9.5} V{oy + 2.5} M{ox + 6.1} {oy + 9.5} V{oy + 2} '
                  f'M{ox + 7.9} {oy + 9.5} V{oy + 3.5} M{ox + 1.5} {oy + 9.5} H{ox + 8.9}" '
                  f'fill="none" stroke="{INK}" stroke-width="1.3" stroke-linecap="round"/>')
            elif ttype == "script":
                A(f'<path d="M{ox + 2} {oy + 1} H{ox + 8} V{oy + 9} H{ox + 2} Z M{ox + 3.5} {oy + 3.2} H{ox + 6.5} '
                  f'M{ox + 3.5} {oy + 5} H{ox + 6.5} M{ox + 3.5} {oy + 6.8} H{ox + 6.5}" {st}/>')
            else:  # send (filled envelope) / receive (outline envelope)
                envelope(ox + 5, oy + 5, filled=ttype == "send", s=0.72)
            A('</g>')
        for n in self.nodes.values():
            x, y = self._center(n, g)
            if n.kind == "task":
                f_, s_, t1, t2 = COLORS.get(n.pool.lanes[n.lane].color, COLORS["system"])
                A(f'<rect x="{x - g.bw / 2}" y="{y - g.bh / 2}" width="{g.bw}" height="{g.bh}" rx="5" fill="{f_}" stroke="{s_}" stroke-width="1"/>')
                A(f'<text x="{x}" y="{y - g.bh / 2 + 27}" text-anchor="middle" class="th" fill="{t1}">{escape(n.name)}</text>')
                if n.sub:
                    A(f'<text x="{x}" y="{y - g.bh / 2 + 44}" text-anchor="middle" class="ts" fill="{t2}">{escape(n.sub)}</text>')
                if n.ttype in ("user", "service", "manual", "script", "send", "receive"):
                    task_icon(n.ttype, x - g.bw / 2 + 5, y - g.bh / 2 + 4)
                elif n.ttype == "subprocess":
                    by = y + g.bh / 2 - 12
                    A(f'<g class="subprocess-marker"><rect x="{x - 5}" y="{by}" width="10" height="10" fill="#FFFFFF" stroke="{INK}" stroke-width="0.9"/>'
                      f'<path d="M{x - 3} {by + 5} H{x + 3} M{x} {by + 2} V{by + 8}" stroke="{INK}" stroke-width="0.9" fill="none"/></g>')
            elif n.kind == "gateway":
                A(f'<polygon points="{x},{y - g.gh} {x + g.gw},{y} {x},{y + g.gh} {x - g.gw},{y}" fill="#FFFFFF" stroke="{INK}" stroke-width="1.3"/>')
                if n.gtype == "parallel":
                    A(f'<path class="gw-parallel" d="M{x - 13} {y} H{x + 13} M{x} {y - 13} V{y + 13}" fill="none" stroke="{INK}" stroke-width="3"/>')
                elif n.gtype == "inclusive":
                    A(f'<circle class="gw-inclusive" cx="{x}" cy="{y}" r="13" fill="none" stroke="{INK}" stroke-width="2.5"/>')
                else:
                    lines = self._gateway_lines(n.name)
                    ys = [y + 4] if len(lines) == 1 else [y - 3, y + 12]
                    for ln, ly in zip(lines, ys):
                        A(f'<text x="{x}" y="{ly}" text-anchor="middle" class="ts" fill="{TEXT}">{escape(ln)}</text>')
            elif n.kind == "start":
                A(f'<circle cx="{x}" cy="{y}" r="{g.r}" fill="#FFFFFF" stroke="{INK}" stroke-width="1.5"/>')
                if n.event == "message":
                    envelope(x, y)
                elif n.event == "timer":
                    clock(x, y)
            elif n.kind == "end":
                A(f'<circle cx="{x}" cy="{y}" r="{g.r}" fill="#FFFFFF" stroke="{TEXT}" stroke-width="3.5"/>')
                if n.event == "error":
                    bolt(x, y, True)
            else:  # catch / throw / boundary
                A(f'<circle cx="{x}" cy="{y}" r="{g.r}" fill="#FFFFFF" stroke="{INK}" stroke-width="1.3"/>')
                A(f'<circle cx="{x}" cy="{y}" r="{g.r - 3}" fill="none" stroke="{INK}" stroke-width="1"/>')
                if n.event == "message":
                    envelope(x, y, s=0.85)
                elif n.event == "link":
                    fill = INK if n.kind == "throw" else "#FFFFFF"
                    A(f'<path d="M{x - 6} {y - 2.5} H{x + 1} V{y - 6} L{x + 7} {y} L{x + 1} {y + 6} V{y + 2.5} H{x - 6} Z" '
                      f'fill="{fill}" stroke="{INK}" stroke-width="0.9"/>')
                elif n.event == "error":
                    bolt(x, y, False)
                else:
                    clock(x, y)
        # annotations: open bracket with text, dotted line to the step
        for a in self.annotations:
            (x0, y0, x1, y1), lines, ln = self._annot_geom(a, g)
            A(f'<path d="M{ln[0][0]:.1f} {ln[0][1]:.1f} L{ln[1][0]:.1f} {ln[1][1]:.1f}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 3" fill="none"/>')
            A(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="#FFFFFF" stroke="none"/>')
            A(f'<path d="M{x0 + 12:.1f} {y0:.1f} H{x0:.1f} V{y1:.1f} H{x0 + 12:.1f}" stroke="{MUTED}" stroke-width="1.2" fill="none"/>')
            for i, t in enumerate(lines):
                A(f'<text x="{x0 + 7:.1f}" y="{y0 + 17 + 15 * i:.1f}" class="ts" fill="{TEXT}">{escape(t)}</text>')
        # labels
        for n in self.nodes.values():
            for lb in self._node_labels(n, g):
                fill = TEXT if lb.get("cls") == "ev" else MUTED
                A(f'<text x="{lb["x"]:.1f}" y="{lb["y"]:.1f}" text-anchor="{lb["anchor"]}" class="{lb.get("cls", "ts")}" fill="{fill}">{escape(lb["text"])}</text>')
        for f in self.flows + self.msgs:
            lb = self._flow_label(f, pts[f.id], g)
            if lb:
                A(f'<text x="{lb["x"]:.1f}" y="{lb["y"]:.1f}" text-anchor="{lb["anchor"]}" class="{lb["cls"]}" fill="{MUTED}">{escape(lb["text"])}</text>')
        # legend
        ly = self.pools[-1].bottom + 36
        x = 14
        def item(draw, text, width=None):
            nonlocal x
            draw(x)
            A(f'<text x="{x + 20}" y="{ly}" class="ts" fill="{MUTED}">{escape(text)}</text>')
            x += (width or (34 + text_w(text)))
        for c, names in colors_used.items():
            f_, s_, _, _ = COLORS.get(c, COLORS["system"])
            item(lambda x0, f_=f_, s_=s_: A(f'<rect x="{x0}" y="{ly - 11}" width="14" height="14" rx="3" fill="{f_}" stroke="{s_}"/>'),
                 ", ".join(names[:3]) + ("..." if len(names) > 3 else ""))
        x += 10
        kinds = {n.kind for n in self.nodes.values()}
        evs = {n.event for n in self.nodes.values()}
        if "start" in kinds:
            item(lambda x0: A(f'<circle cx="{x0 + 7}" cy="{ly - 4}" r="7" fill="#FFFFFF" stroke="{INK}" stroke-width="1.5"/>'), "Start")
        if "end" in kinds:
            item(lambda x0: A(f'<circle cx="{x0 + 7}" cy="{ly - 4}" r="7" fill="#FFFFFF" stroke="{TEXT}" stroke-width="3"/>'), "End")
        if "timer" in evs:
            item(lambda x0: A(f'<circle cx="{x0 + 7}" cy="{ly - 4}" r="7" fill="#FFFFFF" stroke="{INK}" stroke-width="1.2"/><circle cx="{x0 + 7}" cy="{ly - 4}" r="4.5" fill="none" stroke="{INK}" stroke-width="0.9"/>'), "Timer")
        if "message" in evs:
            item(lambda x0: envelope(x0 + 7, ly - 4), "Message")
        if "link" in evs:
            def lk(x0):
                for dx_, fill in ((-13, INK), (7, "#FFFFFF")):
                    xx, yy = x0 + dx_, ly - 4
                    A(f'<circle cx="{xx}" cy="{yy}" r="7.5" fill="#FFFFFF" stroke="{INK}" stroke-width="1"/>')
                    A(f'<path d="M{xx - 4} {yy - 1.5} H{xx} V{yy - 4} L{xx + 4.5} {yy} L{xx} {yy + 4} V{yy + 1.5} H{xx - 4} Z" fill="{fill}" stroke="{INK}" stroke-width="0.7"/>')
            x += 20
            item(lk, "Go to / continue from (same letter)")
        gtypes = {n.gtype for n in self.nodes.values() if n.kind == "gateway"}
        for gt_, text_ in (("exclusive", "Decision (one path only)"), ("parallel", "All paths at once"),
                           ("inclusive", "One or more paths")):
            if gt_ in gtypes:
                def gw_icon(x0, gt_=gt_):
                    A(f'<polygon points="{x0 + 7},{ly - 12} {x0 + 15},{ly - 4} {x0 + 7},{ly + 4} {x0 - 1},{ly - 4}" fill="#FFFFFF" stroke="{INK}"/>')
                    if gt_ == "parallel":
                        A(f'<path d="M{x0 + 3} {ly - 4} H{x0 + 11} M{x0 + 7} {ly - 8} V{ly}" stroke="{INK}" stroke-width="1.6" fill="none"/>')
                    elif gt_ == "inclusive":
                        A(f'<circle cx="{x0 + 7}" cy="{ly - 4}" r="3.2" fill="none" stroke="{INK}" stroke-width="1.4"/>')
                item(gw_icon, text_)
        if "error" in evs:
            item(lambda x0: (A(f'<circle cx="{x0 + 7}" cy="{ly - 4}" r="7.5" fill="#FFFFFF" stroke="{INK}" stroke-width="1"/>'),
                             bolt(x0 + 7, ly - 4, False)), "Error")
        if self.msgs:
            def mf(x0):
                A(f'<path d="M{x0} {ly - 4} H{x0 + 46}" stroke="{MUTED}" stroke-width="1.1" stroke-dasharray="6 4" marker-start="url(#mc)" marker-end="url(#ma)"/>')
            x += 4
            draw_x = x
            mf(draw_x)
            A(f'<text x="{draw_x + 56}" y="{ly}" class="ts" fill="{MUTED}">Message flow (between pools)</text>')
            x += 56 + text_w("Message flow (between pools)") + 24
        if any(f.dashed for f in self.flows):
            A(f'<text x="{x}" y="{ly}" class="ts" fill="{MUTED}">Dashed arrow = exception or exit path</text>')
        for i, t in enumerate(self.legend_notes):
            A(f'<text x="14" y="{ly + 22 * (i + 1)}" class="ts" fill="{MUTED}">{escape(t)}</text>')
        A('</g></svg>')
        return "\n".join(out), PW, PH

    # ---------------------------------------------------------------- BPMN XML
    def to_bpmn(self):
        g = Geo("bpmn")
        self._place_pools()
        pts = self._layout(g)
        right = self._pool_right(g, pts)
        x = []
        A = x.append
        A('<?xml version="1.0" encoding="UTF-8"?>')
        A('<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
          'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
          'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
          'xmlns:modeler="http://camunda.org/schema/modeler/1.0" id="Definitions_1" '
          'targetNamespace="http://bpmn.io/schema/bpmn" exporter="bpmn_kit" exporterVersion="1.0" '
          'modeler:executionPlatform="Camunda Cloud" modeler:executionPlatformVersion="8.5.0">')
        A('  <bpmn:collaboration id="Collaboration_1">')
        for p in self.pools:
            A(f'    <bpmn:participant id="{p.id}" name="{escape(p.title)}" processRef="{p.id}_Process" />')
        for m in self.msgs:
            nm = f' name="{escape(m.label)}"' if m.label else ""
            A(f'    <bpmn:messageFlow id="{m.id}"{nm} sourceRef="{m.src}" targetRef="{m.tgt}" />')
        A('  </bpmn:collaboration>')
        for p in self.pools:
            pn = [n for n in self.nodes.values() if n.pool is p]
            pf = [f for f in self.flows if self.nodes[f.src].pool is p]
            ins, outs = {}, {}
            for f in pf:
                outs.setdefault(f.src, []).append(f.id)
                ins.setdefault(f.tgt, []).append(f.id)
            A(f'  <bpmn:process id="{p.id}_Process" name="{escape(p.title)}" isExecutable="false">')
            if len(p.lanes) > 1:
                A(f'    <bpmn:laneSet id="{p.id}_LaneSet">')
                for i, l in enumerate(p.lanes):
                    A(f'      <bpmn:lane id="{p.id}_Lane{i}" name="{escape(l.name)}">')
                    for n in pn:
                        if n.lane == i:
                            A(f'        <bpmn:flowNodeRef>{n.id}</bpmn:flowNodeRef>')
                    A('      </bpmn:lane>')
                A('    </bpmn:laneSet>')
            for n in pn:
                tag = {"start": "startEvent", "end": "endEvent", "catch": "intermediateCatchEvent",
                       "throw": "intermediateThrowEvent", "boundary": "boundaryEvent",
                       "gateway": GATEWAY_TAGS[getattr(n, "gtype", "exclusive")]}.get(n.kind) or TASK_TAGS.get(n.ttype, "task")
                attrs = f'id="{n.id}" name="{escape(n.name.replace(chr(10), " "))}"'
                if n.kind == "boundary":
                    attrs += f' attachedToRef="{n.attached}" cancelActivity="true"'
                A(f'    <bpmn:{tag} {attrs}>')
                for fid in ins.get(n.id, []):
                    A(f'      <bpmn:incoming>{fid}</bpmn:incoming>')
                for fid in outs.get(n.id, []):
                    A(f'      <bpmn:outgoing>{fid}</bpmn:outgoing>')
                if n.event == "message":
                    A(f'      <bpmn:messageEventDefinition id="{n.id}_Def" />')
                elif n.event == "error":
                    A(f'      <bpmn:errorEventDefinition id="{n.id}_Def" />')
                elif n.event == "link":
                    A(f'      <bpmn:linkEventDefinition id="{n.id}_Def" name="{escape(n.name)}" />')
                elif n.event == "timer":
                    body = (f'<bpmn:timeDuration xsi:type="bpmn:tFormalExpression">{escape(n.duration)}</bpmn:timeDuration>'
                            if n.duration else "")
                    A(f'      <bpmn:timerEventDefinition id="{n.id}_Def">{body}</bpmn:timerEventDefinition>')
                A(f'    </bpmn:{tag}>')
            for f in pf:
                nm = f' name="{escape(f.label)}"' if f.label else ""
                A(f'    <bpmn:sequenceFlow id="{f.id}"{nm} sourceRef="{f.src}" targetRef="{f.tgt}" />')
            if p.notes:
                A(f'    <bpmn:textAnnotation id="{p.id}_Note"><bpmn:text>{escape(" ".join(p.notes))}</bpmn:text></bpmn:textAnnotation>')
            for i, sec in enumerate(self.sections):
                if (sec["pool"] or self.pools[0]) is p:
                    A(f'    <bpmn:textAnnotation id="{p.id}_Sec{i}"><bpmn:text>{escape(sec["text"])}</bpmn:text></bpmn:textAnnotation>')
            for a in self.annotations:
                if self.nodes[a["node"]].pool is p:
                    A(f'    <bpmn:textAnnotation id="{a["id"]}"><bpmn:text>{escape(a["text"])}</bpmn:text></bpmn:textAnnotation>')
                    A(f'    <bpmn:association id="{a["id"]}_Assoc" associationDirection="None" sourceRef="{a["node"]}" targetRef="{a["id"]}" />')
            A('  </bpmn:process>')

        def bounds(b):
            return f'<dc:Bounds x="{b[0]:.0f}" y="{b[1]:.0f}" width="{b[2]:.0f}" height="{b[3]:.0f}" />'
        def wps(ps):
            return "".join(f'<di:waypoint x="{a:.0f}" y="{b:.0f}" />' for a, b in ps)
        def lbl(box):
            return f'<bpmndi:BPMNLabel>{bounds((box[0], box[1], box[2] - box[0], box[3] - box[1]))}</bpmndi:BPMNLabel>'
        A('  <bpmndi:BPMNDiagram id="Diagram_1">')
        A('    <bpmndi:BPMNPlane id="Plane_1" bpmnElement="Collaboration_1">')
        for p in self.pools:
            w = right[p.id]
            A(f'      <bpmndi:BPMNShape id="{p.id}_di" bpmnElement="{p.id}" isHorizontal="true">{bounds((0, p.top, w, p.bottom - p.top))}</bpmndi:BPMNShape>')
            if len(p.lanes) > 1:
                for i, l in enumerate(p.lanes):
                    A(f'      <bpmndi:BPMNShape id="{p.id}_Lane{i}_di" bpmnElement="{p.id}_Lane{i}" isHorizontal="true">{bounds((g.pool_w, p.lane_top(i), w - g.pool_w, l.h))}</bpmndi:BPMNShape>')
            if p.notes:
                A(f'      <bpmndi:BPMNShape id="{p.id}_Note_di" bpmnElement="{p.id}_Note">{bounds((w + 30, p.top + 20, 340, 20 + 15 * len(p.notes)))}</bpmndi:BPMNShape>')
            for i, sec in enumerate(self.sections):
                if (sec["pool"] or self.pools[0]) is p:
                    A(f'      <bpmndi:BPMNShape id="{p.id}_Sec{i}_di" bpmnElement="{p.id}_Sec{i}">'
                      f'{bounds((g.cx(sec["col"]) - 15, p.top - 42, text_w(sec["text"], 14, True) + 24, 30))}</bpmndi:BPMNShape>')
        for n in self.nodes.values():
            b = self._bbox(n, g)
            extra = ""
            if n.kind == "gateway" and n.gtype == "exclusive":
                extra = ' isMarkerVisible="true"'
            elif n.kind == "task" and n.ttype == "subprocess":
                extra = ' isExpanded="false"'
            labs = self._node_labels(n, g)
            lab = ""
            if labs:
                bx = labs[0]["box"]
                lab = lbl((bx[0], bx[1] - 2, max(bx[2], bx[0] + 60), bx[3] + 4))
            A(f'      <bpmndi:BPMNShape id="{n.id}_di" bpmnElement="{n.id}"{extra}>{bounds((b[0], b[1], b[2] - b[0], b[3] - b[1]))}{lab}</bpmndi:BPMNShape>')
        for f in self.flows + self.msgs:
            lb = self._flow_label(f, pts[f.id], g)
            lab = lbl((lb["box"][0], lb["box"][1] - 2, lb["box"][2] + 6, lb["box"][3] + 2)) if lb else ""
            A(f'      <bpmndi:BPMNEdge id="{f.id}_di" bpmnElement="{f.id}">{wps(pts[f.id])}{lab}</bpmndi:BPMNEdge>')
        for a in self.annotations:
            box, _, ln = self._annot_geom(a, g)
            A(f'      <bpmndi:BPMNShape id="{a["id"]}_di" bpmnElement="{a["id"]}">{bounds((box[0], box[1], box[2] - box[0], box[3] - box[1]))}</bpmndi:BPMNShape>')
            A(f'      <bpmndi:BPMNEdge id="{a["id"]}_Assoc_di" bpmnElement="{a["id"]}_Assoc">{wps([ln[1], ln[0]])}</bpmndi:BPMNEdge>')
        A('    </bpmndi:BPMNPlane>')
        A('  </bpmndi:BPMNDiagram>')
        A('</bpmn:definitions>')
        xml = "\n".join(x)
        # Camunda-layout checks: shapes and label placement differ from the SVG, so re-check them here
        errs = []
        for f in self.flows:
            (ax, ay), (bx, by) = pts[f.id][-2], pts[f.id][-1]
            if math.hypot(bx - ax, by - ay) < 28:
                errs.append(f"[2-arrow-bpmn] arrow {f.src} -> {f.tgt} is cramped in the Camunda layout")
        labels = [lb for n in self.nodes.values() for lb in self._node_labels(n, g)]
        labels += [lb for f in self.flows + self.msgs if (lb := self._flow_label(f, pts[f.id], g))]
        labels += [{"box": self._annot_geom(a, g)[0], "text": "note: " + a["text"][:30], "owner": a["node"]}
                   for a in self.annotations]
        def overlap(a, b):
            return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                if overlap(a["box"], b["box"]):
                    errs.append(f"[4-label-label-bpmn] in Camunda, labels '{a['text']}' and '{b['text']}' overlap")
        for f in self.flows + self.msgs:
            for (x0, y0), (x1, y1) in zip(pts[f.id], pts[f.id][1:]):
                seg = (min(x0, x1) - 0.5, min(y0, y1) - 0.5, max(x0, x1) + 0.5, max(y0, y1) + 0.5)
                for lb in labels:
                    if lb["owner"] not in (f.id,) and overlap(seg, lb["box"]):
                        errs.append(f"[5-through-label-bpmn] in Camunda, arrow {f.src} -> {f.tgt} crosses label '{lb['text']}'")
        return xml, sorted(set(errs))

    # ---------------------------------------------------------------- browser helpers
    @staticmethod
    def find_browser():
        env = os.environ.get("BPMN_BROWSER")
        if env and Path(env).exists():
            return env
        cands = []
        bases = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]
        if os.name == "nt":
            # AI tools start MCP servers with a trimmed environment that has no ProgramFiles: use the standard folders
            drive = os.environ.get("SYSTEMDRIVE", "C:") + "\\"
            bases += [drive + "Program Files (x86)", drive + "Program Files"]
        for base in bases:
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
        for c in cands:
            if c.exists():
                return str(c)
        for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
            w = shutil.which(name)
            if w:
                return w
        return None

    @staticmethod
    def _run_browser(args, timeout=60, attempts=2):
        """Run headless Edge/Chrome. A render now and then hangs, so a hung attempt is killed and retried once."""
        b = Diagram.find_browser()
        if not b:
            raise RuntimeError("No Edge/Chrome found for headless rendering; set BPMN_BROWSER to its path")
        for attempt in range(attempts):
            prof = tempfile.mkdtemp(prefix="bpmnkit-prof-")
            try:
                r = subprocess.run([b, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={prof}"] + args,
                                   capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
                return r.stdout
            except subprocess.TimeoutExpired:
                if attempt == attempts - 1:
                    raise
            finally:
                shutil.rmtree(prof, ignore_errors=True)

    def export_png(self, svg_path, png_path, w, h, scale=2):
        self._run_browser([f"--force-device-scale-factor={scale}", f"--window-size={int(math.ceil(w))},{int(math.ceil(h))}",
                           f"--screenshot={png_path}", Path(svg_path).resolve().as_uri()])
        return Path(png_path).exists()

    def import_check(self, xml, preview_png=None):
        """Load the .bpmn in bpmn-js (the engine inside Camunda Modeler). Returns (ok, message)."""
        if not VIEWER_JS.exists():
            return False, f"viewer missing: {VIEWER_JS}"
        tmp = Path(tempfile.mkdtemp(prefix="bpmnkit-"))
        html = tmp / "view.html"
        html.write_text(
            '<!doctype html><html><head><meta charset="utf-8"><style>html,body,#c{margin:0;width:100%;height:100%;background:#fff}'
            '#log{position:fixed;left:0;bottom:0;font:12px monospace;background:#ffd}</style>'
            f'<script>{VIEWER_JS.read_text(encoding="utf-8")}</script></head><body><div id="c"></div><pre id="log">pending</pre>'
            f'<script>const xml = {json.dumps(xml)};'
            'const v = new BpmnJS({container:"#c"});'
            'v.importXML(xml).then(r=>{v.get("canvas").zoom("fit-viewport");'
            'document.getElementById("log").textContent="RESULT:OK:"+r.warnings.length+":"+r.warnings.map(w=>w.message).join(" | ")+":END";})'
            '.catch(e=>{document.getElementById("log").textContent="RESULT:ERROR:"+e.message+":END";});</script></body></html>',
            encoding="utf-8")
        dom = self._run_browser(["--virtual-time-budget=15000", "--dump-dom", html.as_uri()])
        m = re.search(r"RESULT:(OK|ERROR):(.*?):END", dom, re.S)
        if preview_png:
            self._run_browser(["--virtual-time-budget=15000", "--window-size=2400,1400", f"--screenshot={preview_png}", html.as_uri()])
        shutil.rmtree(tmp, ignore_errors=True)
        if not m:
            return False, "bpmn-js did not report a result (page did not load)"
        if m.group(1) == "ERROR":
            return False, f"import error: {m.group(2)}"
        n, _, rest = m.group(2).partition(":")
        return n == "0", f"imported, {n} warnings" + (f": {rest}" if rest else "")

    # ---------------------------------------------------------------- build
    def build(self, out_dir, name, stage="svg", preview_dir=None):
        """stage 'svg': checks + SVG only. stage 'all': checks + SVG + PNG + .bpmn + Camunda import check."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        errs, warns, _ = self.check()
        svg, w, h = self.to_svg()
        svg_path = out / f"{name}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        print(f"SVG  -> {svg_path}  ({w:.0f} x {h:.0f})")
        result = {"errors": list(errs), "warnings": list(warns), "files": [str(svg_path)]}
        if stage == "all" and not errs:
            xml, berrs = self.to_bpmn()
            result["errors"] += berrs
            bpmn_path = out / f"{name}.bpmn"
            bpmn_path.write_text(xml, encoding="utf-8")
            png_path = out / f"{name}.png"
            self.export_png(svg_path, png_path, w, h)
            prev = Path(preview_dir) / f"{name}.camunda-preview.png" if preview_dir else None
            ok, msg = self.import_check(xml, prev)
            print(f"BPMN -> {bpmn_path}\nPNG  -> {png_path}\nCamunda import check: {msg}")
            if prev:
                print(f"Camunda preview -> {prev}")
            if not ok:
                result["errors"].append(f"[12-import] {msg}")
            result["files"] += [str(bpmn_path), str(png_path)]
        elif stage == "all":
            print("Not exporting PNG/.bpmn: fix the errors first.")
        if stage == "svg" and preview_dir:
            look = Path(preview_dir) / f"{name}.look.png"
            self.export_png(svg_path, look, w, h, scale=1)
            print(f"Look PNG (for your own visual check, not a deliverable) -> {look}")
        print(f"\nCHECKS: {len(result['errors'])} errors, {len(result['warnings'])} warnings")
        for e in result["errors"]:
            print("  ERROR", e)
        for wn in result["warnings"]:
            print("  warn ", wn)
        return result
