"""Pictures placed anywhere on the page, with the text flowing round them (like Word's text wrapping).

A floating picture is pinned to a paragraph by an invisible mark: it moves with that paragraph when text is
added above. Its "float" settings (saved in the note):
    wrap   square      text beside it ............ "text": "largest" (the side with more room) | "right" | "left"
           topbottom   text above and below it only
           front       over the text; the text takes no notice of it
    x, y   where it sits, in page pixels (96 to the inch): from the left edge of the text, and from the top
           of its paragraph

How the text flows round it: Tk can only give a whole line of text (a paragraph) one pair of margins, so
where the text passes the top or bottom of a picture Nobu adds an invisible line break - a "\\n" tagged
"softnl". Those are never saved, copied or exported, and they are all worked out again (reflow) right after
every change, so the text moves smoothly as you type, drag or resize. The lines beside a picture get a
"W|..." tag whose margins (and spacing) keep them clear of it.
"""
import logging
import tkinter as tk

import nobu_rich as R
import nobu_theme as T

log = logging.getLogger("nobu.float")

WRAPS = ("square", "topbottom", "front")
GAP = 12            # page pixels between a picture and the text round it
MIN_TEXT = 72       # page pixels: a gap narrower than an inch beside a picture is left empty
TEXT_W = R.TEXT_W_PX      # page pixels: the width of the text (6.5")


class FloatLayer:
    def __init__(self, editor):
        self.ed = editor
        self.t = editor.text
        self._counter = 0
        self._job = None
        self.flowing = False          # (reflow is changing the text: not an edit)
        self._wtags = set()           # margin tags made so far
        self.stale = True             # the text changed since Tk last measured its lines ("sync" needed)
        self.mods = 0                 # counts reflow's own changes (a line measured before one is out of date)
        self.all_dirty = True         # everything must flow again (a picture was added, moved, resized...)
        self.touched = []             # where the text was edited since the last reflow
        self.n_soft = 0               # invisible breaks made by the last reflow (an edit that removed one: reflow)
        self._width = 0               # the page's width at the last reflow
        self.t.bind("<Configure>", self._resized, add="+")
        self.t.bind("<Map>", lambda e: self.schedule() if self.all_dirty and self.names() else None, add="+")
        self.recs = {}                # line number -> {"lm", "rm", "push"} while flowing

    def _resized(self, e):
        """The page got wider or narrower (zooming does this a moment after the fonts change): flow again."""
        if e.width != self._width:
            self._width = e.width
            if self.names():
                self.schedule()

    # ------------------------------------------------------------ the floating pictures
    def names(self):
        return [n for n, i in self.ed.images.items() if i.get("float")]

    def is_float(self, name):
        return bool(self.ed.images.get(name, {}).get("float"))

    def add(self, rel, width, height, opts, index, gravity="right"):
        """A floating picture pinned at index. opts: wrap / text / x / y (see the top of this file)."""
        ed = self.ed
        self._counter += 1
        name = "nobufl%d" % self._counter
        while name in ed.images:
            self._counter += 1
            name = "nobufl%d" % self._counter
        photo, width, height = ed._make_photo(rel, width, height)
        f = {"wrap": opts.get("wrap", "square"), "text": opts.get("text", "largest"),
             "x": max(0, int(round(opts.get("x", 0)))), "y": max(0, int(round(opts.get("y", 0))))}
        if f["wrap"] not in WRAPS:
            f["wrap"] = "square"
        lab = tk.Label(self.t, image=photo, bd=0, highlightthickness=0, bg=T.PAPER, cursor="fleur")
        self.t.mark_set(name, index)
        self.t.mark_gravity(name, gravity)
        ed.images[name] = {"rel": rel, "w": width, "h": height, "photo": photo, "float": f, "label": lab,
                           "_doc_top": None, "_px": 0, "_py": 0}
        if ed.pictool:
            ed.pictool.bind_float(name, lab)
        self.schedule()
        return name

    def remove(self, name):
        info = self.ed.images.pop(name, None)
        if not info:
            return
        try:
            info["label"].destroy()
        except tk.TclError:
            pass
        for m in (name, "nobufe_" + name):
            try:
                self.t.mark_unset(m)
            except tk.TclError:
                pass
        self.schedule()

    def clear(self):
        for n in self.names():
            info = self.ed.images.pop(n)
            try:
                info["label"].destroy()
                self.t.mark_unset(n)
                self.t.mark_unset("nobufe_" + n)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ measuring
    def par_start(self, idx):
        """Where the paragraph holding idx starts (skipping back over invisible line breaks)."""
        t = self.t
        s = t.index("%s linestart" % idx)
        while s != "1.0" and "softnl" in t.tag_names("%s -1c" % s):
            s = t.index("%s -1c linestart" % s)
        return s

    def ydoc(self, idx):
        """Pixels from the top of the note to the display line holding idx. (Line heights are brought up to
        date with "sync" first: asking Tk's "count -update" straight after changing margins and spacing
        can crash Tk itself.)"""
        t = self.t
        try:
            self._sync()
            v = t.count("1.0", idx, "ypixels")
        except tk.TclError:
            return 0
        if isinstance(v, tuple):
            v = v[0]
        return int(v or 0)

    def view_offset(self):
        """Pixels of the note scrolled off the top of the window (in the Text's own coordinates)."""
        t = self.t
        try:
            idx = t.index("@0,0")
            dl = t.dlineinfo(idx)
            if not dl:
                return 0
            return self.ydoc(t.index("%s display linestart" % idx)) - dl[1]
        except tk.TclError:
            return 0

    def _sync(self):
        """Bring Tk's line heights up to date - only after something changed (it takes a few ms each time)."""
        if self.stale:
            self.t.tk.call(self.t._w, "sync")
            self.stale = False

    def place_all(self):
        """Put each picture where it belongs on screen (after scrolling, zooming or reflowing)."""
        ed, t = self.ed, self.t
        names = self.names()
        if not names or self.flowing:        # (while reflowing, once at the end is enough)
            return
        k = ed.img_scale()
        off = self.view_offset()
        ix, iy = ed._text_inset()
        for n in names:
            info = ed.images[n]
            if info["_doc_top"] is None:
                try:
                    info["_doc_top"] = self.ydoc(self.par_start(t.index(n))) + info["float"]["y"] * k
                except tk.TclError:
                    continue
            px = int(round(info["float"]["x"] * k))
            py = int(round(info["_doc_top"] - off - iy))
            info["_px"], info["_py"] = px, py
            info["label"].place(x=px, y=py)
        if ed.pictool and ed.pictool.sel in names:
            ed.pictool.sync()

    def par_at(self, y):
        """The paragraph at y pixels from the top of the note."""
        t = self.t
        wy = y - self.view_offset()
        if 0 <= wy < t.winfo_height():
            ix, _iy = self.ed._text_inset()
            return self.par_start(t.index("@%d,%d" % (ix + 2, int(wy))))
        lo, hi = 1, int(t.index("end-1c").split(".")[0])
        while lo < hi:                          # (off screen: find the line by its height from the top)
            mid = (lo + hi + 1) // 2
            if self.ydoc("%d.0" % mid) <= y:
                lo = mid
            else:
                hi = mid - 1
        return self.par_start("%d.0" % lo)

    def move_to(self, name, x, doc_top=None, dy=0, width=None, place=True):
        """Move a floating picture: x in page pixels from the left of the text, and either doc_top (pixels
        from the top of the note) or dy (page pixels down). It is pinned to the paragraph it ends up beside."""
        ed, t = self.ed, self.t
        info = ed.images.get(name)
        if not info:
            return
        f = info["float"]
        k = ed.img_scale()
        w = width if width is not None else info["photo"].width() / k
        f["x"] = int(round(max(0, min(TEXT_W - w, x))))
        if doc_top is None:
            cur = info["_doc_top"]
            if cur is None:
                cur = self.ydoc(self.par_start(t.index(name))) + f["y"] * k
            doc_top = cur + dy * k
        doc_top = max(0, doc_top)
        p = self.par_at(doc_top)
        ptop = self.ydoc(p)
        f["y"] = int(round(max(0, (doc_top - ptop) / k)))
        t.mark_set(name, p)
        info["_doc_top"] = ptop + f["y"] * k
        if place:
            self.place_all()
        self.schedule()

    SPOTS = (("tl", "Top left"), ("tr", "Top right"), ("ml", "Middle left"), ("mr", "Middle right"),
             ("bl", "Bottom left"), ("br", "Bottom right"))

    def page_box(self, y):
        """(top, bottom) in pixels from the top of the note, of the text area of the page holding y."""
        ed = self.ed
        tops = [ed.px(0.88)]               # (page 1's text starts below its top margin)
        for m in ed.page_marks:
            try:
                tops.append(self.ydoc(m))
            except tk.TclError:
                pass
        n = max(0, sum(1 for top in tops if top <= y) - 1)
        top = tops[n]
        bottom = tops[n + 1] if n + 1 < len(tops) else top + ed.px(9.0) - (ed.px(0.88) if n == 0 else 0)
        return top, bottom

    def place_on_page(self, name, spot):
        """Put a floating picture in a corner or at the middle of a side of the page it is on:
        spot = tl / tr / ml / mr / bl / br (top / middle / bottom, left / right)."""
        ed, t = self.ed, self.t
        info = ed.images.get(name)
        if not info:
            return
        k = ed.img_scale()
        w, h = info["w"], info["photo"].height()        # (its exact width in page pixels, not the screen's)
        cur = info["_doc_top"]
        if cur is None:
            cur = self.ydoc(self.par_start(t.index(name))) + info["float"]["y"] * k
        page = self.page_box(cur)[0]
        for _ in range(3):              # (moving it re-wraps the text above, which shifts the page: settle)
            top, bottom = self.page_box(page)
            y = max(top, {"t": top, "m": top + (bottom - top - h) / 2.0, "b": bottom - h}[spot[0]])
            self.move_to(name, 0 if spot[1] == "l" else TEXT_W - w, doc_top=y, width=w)
            self.reflow()
            if abs(self.ydoc(self.par_start(t.index(name))) + info["float"]["y"] * k - y) < 2:
                break
            page = top

    # ------------------------------------------------------------ reflow
    def schedule(self, ms=None):
        """Flow the text round every picture again, right after this event."""
        self.all_dirty = True
        self.stale = True
        if self._job is None:
            self._job = T.later(self.t, ms, self.reflow)

    def edited(self, idx):
        """The text was edited at idx: flow again only if that's next to a picture (otherwise the pictures
        just move with their paragraphs)."""
        self.touched.append(idx)
        self.stale = True
        if self._job is None:
            self._job = T.later(self.t, None, self.reflow, True)

    def _span(self, n):
        """The stretch of text a picture's wrapping affects: (its paragraph's start, end of its last line)."""
        t = self.t
        a = self.par_start(t.index(n))
        e = "nobufe_" + n
        b = t.index("%s lineend +1c" % (t.index(e) if e in t.mark_names() else a))
        return a, b

    def _to_flow(self, names):
        """Which pictures need their text flowed again: all of them after a change to a picture (or an edit
        that removed an invisible break), else just those next to where the text was edited."""
        t = self.t
        if self.all_dirty or len(t.tag_ranges("softnl")) // 2 != self.n_soft:
            return names, None
        try:
            spans = {n: self._span(n) for n in names}
        except tk.TclError:
            return names, None
        hit = [n for n in names if any(t.compare(spans[n][0], "<=", i) and t.compare(i, "<=", spans[n][1])
                                       for i in self.touched)]
        grew = True
        while hit and grew:                  # (pictures whose stretches overlap go together)
            grew = False
            for n in names:
                if n not in hit and any(t.compare(spans[n][0], "<", spans[h][1]) and t.compare(spans[h][0], "<", spans[n][1])
                                        for h in hit):
                    hit.append(n)
                    grew = True
        return hit, [spans[n] for n in hit]

    def reflow(self, typed=False):
        """Take out the invisible line breaks and margins, then flow the text round the pictures again.
        typed: only text was edited - then only the pictures next to the edit flow again (typing away from
        every picture just moves them along with their paragraphs). Anything else flows them all."""
        self._job = None
        if not typed:
            self.all_dirty = True
        ed, t = self.ed, self.t
        names = self.names()
        if not names and not t.tag_ranges("softnl") and not self._wtags:
            self.touched = []
            return
        if not t.winfo_ismapped() or t.winfo_width() < ed.px(2.0):
            self.all_dirty = True              # (a tab that isn't showing: flow it when it's shown - _resized)
            return
        todo, spans = self._to_flow(names)
        self.touched = []
        for n in names:
            ed.images[n]["_doc_top"] = None              # (worked out again by place_all)
        if not todo and spans is not None:
            self.place_all()
            return
        self.all_dirty = False
        self.flowing = True
        self.stale = True

        def inside(a, b):
            return spans is None or any(t.compare(a, ">=", s0) and t.compare(b, "<=", s1) for s0, s1 in spans)
        try:
            rs = t.tag_ranges("softnl")
            pars = []
            for k in range(len(rs) - 2, -1, -2):
                if not inside(rs[k], rs[k + 1]):
                    continue
                t.mark_set("nobu_par%d" % k, self.par_start(rs[k]))
                pars.append("nobu_par%d" % k)
                t.delete(rs[k], rs[k + 1])
            for m in pars:                     # each paragraph keeps its first line's formatting throughout
                p = t.index(m)
                t.mark_unset(m)
                want = [tg for tg in t.tag_names(p) if R.is_par_tag(tg)]
                end = t.index("%s lineend +1c" % p)
                mixed = False
                for tg in t.tag_names():
                    if R.is_par_tag(tg) and tg not in want and t.tag_nextrange(tg, p, end):
                        t.tag_remove(tg, p, end)
                        mixed = True
                for tg in want:
                    t.tag_add(tg, p, end)
                if mixed:
                    ed._restyle(p, p)
            if spans is not None:              # (the stretches may have moved: measure them again)
                spans = [self._span(n) for n in todo]
            for tg in self._wtags:             # (only where each one is: a long stretch would make Tk measure
                r = t.tag_ranges(tg)           # every line in between again - slow in a long note)
                for k in range(0, len(r), 2):
                    if inside(r[k], r[k + 1]):
                        t.tag_remove(tg, r[k], r[k + 1])
            self.recs = {}
            if todo:
                self._flow(todo)
            self._room_below(names)
            self.n_soft = len(t.tag_ranges("softnl")) // 2
            t.edit_modified(False)
        except tk.TclError:
            log.exception("reflow failed")
        finally:
            self.flowing = False
        self.place_all()

    def _room_below(self, names):
        """A picture hanging below the end of the note: make the page long enough to show all of it."""
        ed, t = self.ed, self.t
        base = ed.px(0.88)
        extra = 0
        if names:
            k = ed.img_scale()
            last = t.index("end -1c linestart")
            for n in names:
                ps = self.par_start(t.index(n))
                if t.compare(ps, "<", "%s -30 lines" % last):
                    continue                    # (far from the end: can't hang below it)
                info = ed.images[n]
                below = self.yrel(ps, "end") - base     # paragraph top -> end of the text
                extra = max(extra, int(info["float"]["y"] * k + info["photo"].height() - below))
        if int(t.tag_cget("docend", "spacing3") or 0) != base + extra:     # (only when it changes: it
            t.tag_configure("docend", spacing3=base + extra)                # makes Tk re-measure everything)
            self.stale = True

    def yrel(self, a, b):
        """Pixels from display line a down to display line b (both near each other: quick)."""
        t = self.t
        try:
            self._sync()
            v = t.count(a, b, "ypixels")
        except tk.TclError:
            return 0
        if isinstance(v, tuple):
            v = v[0]
        return int(v or 0)

    def _flow(self, names):
        """Go down the display lines next to each picture, giving each the margins it needs. Lines far from
        any picture are skipped, and everything is measured from the picture's own paragraph (never from the
        top of the note), so this stays quick even in a 60,000-word note."""
        ed, t = self.ed, self.t
        k = ed.img_scale()
        gap = GAP * k
        text_w = TEXT_W * k
        pending = sorted(names, key=lambda n: self._key(t.index(n)))
        active = []
        s = self.par_start(t.index(pending[0]))
        top = 0                        # pixels from the top of the first picture's paragraph (or the next one's)
        prev = None                    # (start, top) of the display line above
        guard = 0
        while guard < 20000 and (pending or active):
            guard += 1
            # pictures pinned at or above this line join in (their paragraph won't move any more)
            while pending and t.compare(self.par_start(t.index(pending[0])), "<=", s):
                n = pending.pop(0)
                f = ed.images[n]["float"]
                if f["wrap"] == "front":
                    continue
                ps = self.par_start(t.index(n))
                ptop = top if t.compare(ps, "==", s) else top - self.yrel(ps, s)
                ph = ed.images[n]["photo"]
                x0, x1 = f["x"] * k, f["x"] * k + ph.width()
                side = f["text"]
                if side not in ("left", "right"):
                    side = "right" if text_w - x1 >= x0 else "left"
                y = ptop + f["y"] * k
                active.append({"name": n, "y0": y - gap, "y1": y + ph.height() + gap,
                               "x0": x0 - gap, "x1": x1 + gap, "push": f["wrap"] == "topbottom", "side": side})
            nxt = t.index("%s +1 display lines display linestart" % s)
            last = t.compare(nxt, "<=", s) or t.compare(nxt, ">=", "end-1c")
            h = self.yrel(s, "end" if last else nxt)
            seen = self.mods
            bottom = top + h
            for a in active:
                if a["y1"] <= top:             # (this picture's stretch of text ends here)
                    t.mark_set("nobufe_" + a["name"], s)
            active = [a for a in active if a["y1"] > top]
            if not active:
                self._split_if_needed(s, None)
                if not pending:
                    break
                s = self.par_start(t.index(pending[0]))     # (straight on to the next picture's paragraph)
                top, prev = 0, None
                continue
            sig = self._signature(s, top, bottom, active, text_w, k)
            s2 = self._split_if_needed(s, sig)
            if s2 != s:                        # (the line above lost its paragraph spacing: re-measure)
                s = s2
                if prev:
                    top = prev[1] + self.yrel(prev[0], s)
            if sig and sig[0] == "push" and not self._pushed(s):
                self._set_rec(s, push=max(0, int(sig[1] - top)))
                continue                       # (look at the same line again, now below the picture)
            if last:
                for a in active:
                    t.mark_set("nobufe_" + a["name"], "end -1c")
                if pending:
                    s = self.par_start(t.index(pending[0]))
                    top, prev = 0, None
                    continue
                break
            if self.mods != seen:              # (this line changed since it was measured: measure it again)
                nxt = t.index("%s +1 display lines display linestart" % s)
                h = self.yrel(s, nxt)
            prev = (s, top)
            top += h
            s = nxt

    @staticmethod
    def _key(idx):
        a, b = idx.split(".")
        return int(a), int(b)

    def _signature(self, s, top, bottom, active, text_w, k):
        """What this display line needs: None (nothing), ("push", y) (move below a picture),
        or (left margin, right margin) to keep clear of pictures beside it."""
        t = self.t
        over = [a for a in active if bottom > a["y0"] and top < a["y1"]]
        if not over:
            return None
        if any(kk == "window" for kk, _v, _i in t.dump(s, "%s display lineend" % s, window=True)):
            return None                        # (a table can't be narrowed; it stays as it is)
        if self._pushed(s):
            return None
        lm = max([a["x1"] for a in over if a["side"] == "right"] or [0])
        rm = max([text_w - a["x0"] for a in over if a["side"] == "left"] or [0])
        if any(a["push"] for a in over) or text_w - lm - rm < MIN_TEXT * k:
            return ("push", max(a["y1"] for a in over))
        return (int(lm), int(max(0, rm)))

    def _pushed(self, s):
        t = self.t
        if t.compare(s, "!=", "%s linestart" % s):
            return False
        return bool(self.recs.get(int(s.split(".")[0]), {}).get("push"))

    def _split_if_needed(self, s, sig):
        """Make s the start of its own line (with an invisible break) when it needs different margins
        from the display line before it, or has to move below a picture. Returns where s is now."""
        t = self.t
        want = self._rec_for(sig)
        if t.compare(s, "==", "%s linestart" % s):
            self._set_rec(s, **want)
            return s
        ln = int(s.split(".")[0])
        cur = self.recs.get(ln, {})
        push = bool(sig) and sig[0] == "push"
        if not push and (cur.get("lm", 0), cur.get("rm", 0)) == (want.get("lm", 0), want.get("rm", 0)):
            return s                           # (same margins as the lines above it in this paragraph)
        tags = tuple(tg for tg in t.tag_names(s) if tg.startswith("P|") or (":" in tg and tg.split(":")[0] in (
            "st", "al", "ls", "sb", "sa", "ind", "fi", "li")))
        t.insert(s, "\n", tags + ("softnl",))
        self.stale = True
        self.mods += 1
        self._apply(ln)                        # (the line before now ends with an invisible break)
        s = t.index("%s +1c" % s)
        self._set_rec(s, **want)
        return s

    @staticmethod
    def _rec_for(sig):
        if not sig:
            return {}
        if sig[0] == "push":
            return {}
        return {"lm": sig[0], "rm": sig[1]}

    def _set_rec(self, s, **rec):
        ln = int(self.t.index(s).split(".")[0])
        cur = self.recs.setdefault(ln, {})
        cur.update(rec)
        self._apply(ln)

    def _apply(self, ln):
        """Give text line ln the margins and spacing it needs (or none, if it's just a normal paragraph)."""
        ed, t = self.ed, self.t
        s = "%d.0" % ln
        ptag = next((tg for tg in t.tag_names(s) if tg.startswith("P|")), None)
        if ptag is None or ptag not in ed._ptags:
            return
        base = ed._par_options(ed._ptags[ptag])
        cont = ln > 1 and "softnl" in t.tag_names("%s -1c" % s)
        soft_end = "softnl" in t.tag_names("%d.end" % ln)
        rec = self.recs.get(ln, {})
        for tg in t.tag_names(s):
            if tg.startswith("W|"):
                t.tag_remove(tg, s, "%s lineend +1c" % s)
                self.stale = True
                self.mods += 1
        if not (cont or soft_end or rec.get("lm") or rec.get("rm") or rec.get("push")):
            return
        lm1 = base["lmargin2"] if cont else base["lmargin1"]
        lm2 = base["lmargin2"]
        ex = rec.get("lm", 0)
        lm1, lm2 = max(lm1, ex), max(lm2, ex)
        rm = max(base["rmargin"], rec.get("rm", 0))
        s1 = (0 if cont else base["spacing1"]) + rec.get("push", 0)
        if ln == 1:                            # (the first line also carries the page's top margin)
            s1 += ed.px(0.88)
        s3 = 0 if soft_end else base["spacing3"]
        if t.compare("%d.0" % ln, "==", "end -1c linestart"):     # (... and the last, the bottom margin)
            s3 = max(s3, int(t.tag_cget("docend", "spacing3") or 0))
        name = "W|%d|%d|%d|%d|%d" % (lm1, lm2, rm, s1, s3)
        if name not in self._wtags:
            self._wtags.add(name)
            t.tag_configure(name, lmargin1=lm1, lmargin2=lm2, rmargin=rm, spacing1=s1, spacing3=s3)
            # (a new tag starts above all the others; raising it later would make Tk re-measure every line)
        t.tag_add(name, s, "%s lineend +1c" % s)
        self.stale = True
        self.mods += 1

    # ------------------------------------------------------------ text without the invisible breaks
    def plain(self, a, b):
        """The text between a and b as written (invisible line breaks left out)."""
        out, skip = [], False
        for k, v, _i in self.t.dump(a, b, text=True, tag=True):
            if k == "tagon" and v == "softnl":
                skip = True
            elif k == "tagoff" and v == "softnl":
                skip = False
            elif k == "text" and not skip:
                out.append(v)
        return "".join(out)
