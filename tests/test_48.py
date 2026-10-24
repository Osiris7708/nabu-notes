"""v4.8: tabs, snapping inside Nobu, drag-to-open from lists/sidebar, folder name click toggles."""
import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, traceback, json
H = tempfile.mkdtemp(); os.environ['NOBU_HOME'] = H
import nobu_models; nobu_models.missing = lambda n: []
import nobu_audio, nobu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s, a, prompt=None): return []
nobu_transcribe.Detector = lambda c: D()
class E2(nobu_audio.Engine):
    def __init__(s, *a, **k): k['start_stream'] = False; super().__init__(*a, **k)
nobu_audio.Engine = E2
import nobu_main as M, nobu_config as C, nobu_library as lib, nobu_theme as T, nobu_workspace as WS
import tkinter as tk

MENUS = []
def cap_popup(self, x, y, entry=""):
    MENUS.append((self, [self.entrycget(i, "label") if self.type(i) != "separator" else "---"
                         for i in range((self.index("end") or -1) + 1)]))
tk.Menu.tk_popup = cap_popup
INFOS = []
T.info = lambda *a, **k: INFOS.append(a[-1] if a else "")
T.confirm = lambda *a, **k: True
app = M.App(); app._server = M._claim_instance()
OK = []
def check(name, cond, extra=""):
    OK.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
def step(fn):
    ev = threading.Event(); r = {}
    def go():
        try: r['v'] = fn()
        except Exception as e: r['e'] = repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(60); return r.get('v', r.get('e'))
def idle(t=0.3):
    time.sleep(t); step(lambda: app.root.update())
def shot(name, wait=0.5):
    time.sleep(wait); os.makedirs('shots', exist_ok=True)
    _here.shot(name)
def rowpos(tv, iid, fx=None):
    tv.see(iid); tv.update(); bb = tv.bbox(iid)
    return (bb[0] + (int(bb[2] * fx) if fx is not None else min(bb[2] - 10, 150)), bb[1] + bb[3] // 2) if bb else None

def tree_click(iid):
    tv = app.tree; x, y = rowpos(tv, iid)
    tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100); tv.update()

def drag(widget, x0, y0, x2, y2, steps=8, shot_name=None):
    """Real press / motion / release on `widget` (coordinates: x0,y0 local; x2,y2 SCREEN)."""
    rx, ry = widget.winfo_rootx(), widget.winfo_rooty()
    widget.event_generate("<ButtonPress-1>", x=x0, y=y0, rootx=rx + x0, rooty=ry + y0)
    sx, sy = rx + x0, ry + y0
    for k in range(1, steps + 1):
        xs, ys = sx + (x2 - sx) * k // steps, sy + (y2 - sy) * k // steps
        widget.event_generate("<B1-Motion>", x=xs - rx, y=ys - ry, rootx=xs, rooty=ys, state=0x100)
    widget.update()
    snap = app.ws._snap_win
    shown = bool(snap is not None and snap.winfo_ismapped())
    geo = (snap.winfo_rootx(), snap.winfo_width()) if shown else None
    if shot_name:
        widget.update(); _here.shot(shot_name)
    widget.event_generate("<ButtonRelease-1>", x=x2 - rx, y=y2 - ry, rootx=x2, rooty=y2, state=0x100)
    widget.update()
    return shown, geo

def tab_of(path):
    for p in app.ws.panes:
        for ed in p.eds:
            if ed.path == path:
                return p, ed, p.tabw[ed][1]
    return None, None, None
def layout():
    return [[lib.title(e.path) for e in p.eds] for p in app.ws.panes]
def area():
    a = app.ws.area; return a.winfo_rootx(), a.winfo_rooty(), a.winfo_width(), a.winfo_height()

def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1700x980+0+0')); idle(0.5)
        book = lib.create_project('The Hollow Crown'); ch = lib.create_folder(book, 'Characters')
        other = lib.create_project('Ashfall Campaign')
        n = {}
        for name, folder in (("One", book), ("Two", book), ("Three", book), ("Villains", ch),
                             ("S1", other), ("S2", other), ("S3", other)):
            n[name] = lib.create_note(folder, name)
        step(app.refresh_library)
        # ===== folder names: click opens, click again closes
        step(lambda: tree_click(book))
        a = step(lambda: bool(app.tree.item(book, "open"))); v = step(lambda: app.view is app.projview)
        time.sleep(0.3); step(lambda: tree_click(book)); b = step(lambda: bool(app.tree.item(book, "open")))
        time.sleep(0.3); step(lambda: tree_click(book)); c = step(lambda: bool(app.tree.item(book, "open")))
        check("folder name: click opens (and shows it), click closes, click opens", (a, v, b, c) == (True, True, False, True),
              (a, v, b, c))
        # ===== tabs
        for k in ("One", "Two", "Three"):
            step(lambda k=k: tree_click(n[k])); time.sleep(0.25)
        check("opening notes makes tabs in one page", step(layout) == [["One", "Two", "Three"]], step(layout))
        check("the last opened is shown", step(lambda: app.editor.path) == n["Three"])
        step(lambda: (lambda p, e, l: (l.event_generate("<ButtonPress-1>", x=5, y=5),
                                       l.event_generate("<ButtonRelease-1>", x=5, y=5)))(*tab_of(n["One"])))
        check("clicking a tab shows it", step(lambda: app.editor.path) == n["One"])
        step(lambda: app.editor.text.event_generate("<Control-w>"))
        check("Ctrl+W closes the tab", step(layout) == [["Two", "Three"]], step(layout))
        step(lambda: tree_click(n["One"]))
        check("re-opening adds it back as a tab (next to the current one)", step(layout) == [["Two", "One", "Three"]], step(layout))
        shot("48_tabs", 0.6)
        # ===== drag a tab to the RIGHT part of the page: split
        def drag_tab(path, xs, ys, shot_name=None):
            p, ed, lbl = tab_of(path); return drag(lbl, 8, 8, xs, ys, shot_name=shot_name)
        A = step(area)
        shown, geo = step(lambda: drag_tab(n["Two"], A[0] + A[2] - 60, A[1] + A[3] // 2, "48_drag_shadow"))
        idle(0.4)
        check("dragging a tab to the right part: blue shadow on the right half while dragging",
              shown and geo and geo[0] >= A[0] + A[2] // 2 - 20, (shown, geo, A))
        check("...and it snaps to the right on release", step(layout) == [["One", "Three"], ["Two"]], step(layout))
        shot("48_split", 0.8)
        # drag a tab onto the LEFT part of the left page
        A = step(area)
        step(lambda: drag_tab(n["One"], A[0] + 40, A[1] + A[3] // 2)); idle(0.4)
        check("tab to the left part of a page: new page on the left", step(layout) == [["One"], ["Three"], ["Two"]], step(layout))
        # drag a tab onto the middle of another page: becomes a tab there
        def mid_of(i):
            b = app.ws.panes[i].body; return b.winfo_rootx() + b.winfo_width() // 2, b.winfo_rooty() + b.winfo_height() // 2
        x, y = step(lambda: mid_of(2))
        step(lambda: drag_tab(n["One"], x, y)); idle(0.4)
        check("tab onto the middle of another page joins it", step(layout) == [["Three"], ["Two", "One"]], step(layout))
        # a single tab dropped onto its own page does nothing
        x, y = step(lambda: mid_of(0))
        step(lambda: drag_tab(n["Three"], x + 10, y)); idle(0.3)
        check("a lone tab dropped on its own page changes nothing", step(layout) == [["Three"], ["Two", "One"]], step(layout))
        # inside the window it never pops out; well outside it does
        A = step(area)
        rx1 = step(lambda: app.root.winfo_rootx() + app.root.winfo_width())
        step(lambda: drag_tab(n["One"], rx1 + 20, A[1] + 300)); idle(0.3)
        check("just past the window edge: snaps right, no pop-out", step(lambda: len(app.ws.popouts)) == 0 and
              step(layout)[-1] == ["One"], step(layout))
        step(lambda: drag_tab(n["One"], rx1 + 250, A[1] + 300)); idle(0.6)
        check("well outside the window: its own window", step(lambda: len(app.ws.popouts)) == 1 and
              step(lambda: app.ws.popouts[0].ed.path) == n["One"], step(layout))
        # the pop-out's name dragged onto the right part of the page comes back there
        def drag_popout_name(xs, ys):
            po = app.ws.popouts[0]; return drag(po.ed.title, 5, 5, xs, ys)
        A = step(area)
        step(lambda: drag_popout_name(A[0] + A[2] - 50, A[1] + A[3] // 2)); idle(0.6)
        check("pop-out dragged onto the right part docks on the right", step(lambda: len(app.ws.popouts)) == 0 and
              step(layout)[-1] == ["One"], step(layout))
        # ===== notes not opened yet: drag from a folder list
        step(lambda: app.show_project(other)); idle(0.3)
        def list_drag(path, xs, ys, shot_name=None):
            tv = app.projview._tv; x, y = rowpos(tv, path, 0.5); return drag(tv, x, y, xs, ys, shot_name=shot_name)
        c = step(lambda: (app.content.winfo_rootx(), app.content.winfo_rooty(), app.content.winfo_width(), app.content.winfo_height()))
        shown, geo = step(lambda: list_drag(n["S1"], c[0] + c[2] - 40, c[1] + c[3] // 2, "48_list_drag"))
        idle(0.5)
        check("dragging an unopened note from a folder list: shadow on the right while dragging",
              shown and geo and geo[0] >= c[0] + c[2] // 2 - 20, (shown, geo))
        check("...opens it on the right when let go", step(lambda: app.view is app.ws.frame) and step(layout)[-1] == ["S1"],
              step(layout))
        step(lambda: app.show_project(other)); idle(0.3)
        c = step(lambda: (app.content.winfo_rootx(), app.content.winfo_rooty(), app.content.winfo_width(), app.content.winfo_height()))
        step(lambda: list_drag(n["S2"], c[0] + 60, c[1] + c[3] // 2)); idle(0.5)
        check("...or on the left", step(layout)[0] == ["S2"], step(layout))
        step(lambda: app.show_project(other)); idle(0.3)
        before = step(layout)
        step(lambda: list_drag(n["S3"], c[0] + c[2] // 2, c[1] + c[3] // 2)); idle(0.5)
        after = step(layout)
        check("...or in the middle: a tab of the page you were in",
              sum(len(x) for x in after) == sum(len(x) for x in before) + 1 and len(after) == len(before), (before, after))
        step(lambda: app.show_project(other)); idle(0.3)
        rx1 = step(lambda: app.root.winfo_rootx() + app.root.winfo_width())
        step(lambda: app.ws.close_editor(app.ws.editors_for(n["S3"])[0]))
        step(lambda: app.show_project(other)); idle(0.3)
        step(lambda: list_drag(n["S3"], rx1 + 300, c[1] + 300)); idle(0.6)
        check("...or well outside the window: its own window", step(lambda: [po.ed.path for po in app.ws.popouts]) == [n["S3"]])
        check("...and the folder list stays on screen", step(lambda: app.view is app.projview))
        step(lambda: app.ws.close_popout(app.ws.popouts[0]))
        # a folder row dragged onto the page area opens that folder
        step(lambda: app.show_project(book)); idle(0.3)
        c = step(lambda: (app.content.winfo_rootx(), app.content.winfo_rooty(), app.content.winfo_width(), app.content.winfo_height()))
        def folder_drag():
            tv = app.projview._tv; x, y = rowpos(tv, ch, 0.5)
            return drag(tv, x, y, c[0] + c[2] // 2, c[1] + c[3] - 60)
        step(folder_drag); idle(0.4)
        check("a folder dragged onto the page area opens it", step(lambda: app.view is app.projview and app.current_project == ch))
        # from the sidebar onto the page (notes open): snaps right
        step(lambda: app.show_workspace())
        idle(0.3)
        def side_drag():
            tv = app.tree; app._tree_open(ch, True); x, y = rowpos(tv, n["Villains"])
            A = area(); return drag(tv, x, y, A[0] + A[2] - 50, A[1] + A[3] // 2)
        step(side_drag); idle(0.5)
        check("a note dragged from the sidebar to the right part opens on the right", step(layout)[-1] == ["Villains"], step(layout))
        # ===== join into one page
        step(app.ws.close_others); idle(0.3)
        lay = step(layout)
        check("Join into one page keeps every note as a tab", len(lay) == 1 and len(lay[0]) >= 6, lay)
        # ===== tab limit
        many = [lib.create_note(other, "Extra %d" % i) for i in range(10)]
        for p in many:
            step(lambda p=p: app.open_note(p))
        check("at most %d tabs per page (oldest closes, saved)" % WS.MAX_TABS, len(step(layout)[0]) == WS.MAX_TABS, step(layout))
        # ===== close everything
        def close_all():
            for ed in list(app.ws.editors()):
                app.ws.close_editor(ed)
            return app.view is not app.ws.frame, app.editor is app.ws.blank
        check("closing every tab goes back to the folder; no note is 'active'", step(close_all) == (True, True))
        INFOS.clear(); step(lambda: app.start_in_note("edit"))
        check("dictation with nothing open just says 'Open a note first'", INFOS and "Open a note first" in INFOS[-1], INFOS)
        # ===== dictation still lands in the right note
        step(lambda: app.open_note(n["One"])); step(lambda: app.open_note(n["Two"], side=True))
        def dictate():
            e1 = app.ws.editors_for(n["One"])[0]; e2 = app.ws.editors_for(n["Two"])[0]
            app.ws._activate(e1); e1.text.mark_set("insert", "end-1c")
            app._engine_event("recording_started", {"mode": "edit"})
            app.ws._activate(e2)
            app.transcriber.submit = lambda *a, **k: None
            app._engine_event("recording_finished", {"mode": "edit", "path": "x.wav"})
            app._tx_event("done", {"mode": "edit", "note": n["One"], "paragraphs": ["Dictated words."]})
            return "Dictated words." in e1.text.get("1.0", "end"), "Dictated" in e2.text.get("1.0", "end")
        check("dictation goes into the note it was started in", step(dictate) == (True, False))
    except Exception:
        traceback.print_exc()
    lg = open(os.path.join(H, "logs", "nobu.log"), encoding="utf-8").read()
    bad = [l for l in lg.splitlines() if ("Error" in l or " ERROR " in l) and not any(
        k in l for k in ("tkinterdnd2", "pystray", "tray unavailable", "sounddevice", "could not list microphones"))]
    check("no errors in the log", not bad, "\n".join(bad[:8]))
    if bad:
        i = lg.find(bad[0]); print(lg[max(0, i - 2500): i + 200])
    print("RESULT %d/%d passed" % (sum(OK), len(OK)))
    os._exit(0)
threading.Thread(target=go, daemon=True).start(); app.run()
