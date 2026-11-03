"""v4.7: new note in Unassigned, double/right-click open, multi-select, lazy tree, import doesn't expand,
symbols in titles, side by side + pop-out + dock, big-library speed."""
import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, traceback, json
H = tempfile.mkdtemp(); os.environ['NABU_HOME'] = H
import nabu_models; nabu_models.missing = lambda n: []
import nabu_audio, nabu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s, a, prompt=None): return []
nabu_transcribe.Detector = lambda c: D()
class E2(nabu_audio.Engine):
    def __init__(s, *a, **k): k['start_stream'] = False; super().__init__(*a, **k)
nabu_audio.Engine = E2
import nabu_main as M, nabu_config as C, nabu_library as lib, nabu_theme as T
import tkinter as tk

MENUS = []
_orig_popup = tk.Menu.tk_popup
def cap_popup(self, x, y, entry=""):
    labels = []
    for i in range((self.index("end") or -1) + 1):
        try:
            labels.append(self.entrycget(i, "label"))
        except tk.TclError:
            labels.append("---")
    MENUS.append((self, labels))
tk.Menu.tk_popup = cap_popup

T.ask_string = lambda *a, **k: ASK.pop(0) if ASK else None
ASK = []
app = M.App(); app._server = M._claim_instance()
OK = []
def check(name, cond, extra=""):
    OK.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, extra)
def step(fn):
    ev = threading.Event(); r = {}
    def go():
        try: r['v'] = fn()
        except Exception as e: r['e'] = repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(60); return r.get('v', r.get('e'))
def shot(name, wait=0.6):
    time.sleep(wait)
    os.makedirs('shots', exist_ok=True)
    _here.shot(name)
class Ev:
    def __init__(s, **k):
        s.state = 0; s.x = s.y = s.x_root = s.y_root = 0
        s.__dict__.update(k)
def row_xy(tv, iid, frac_x=None):
    bb = tv.bbox(iid)
    x = bb[0] + (bb[2] * frac_x if frac_x is not None else bb[2] - 20)
    return int(x), bb[1] + bb[3] // 2

def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1600x950+0+0'))
        # ---------------- titles with any characters
        book = lib.create_project('The Hollow Crown'); ch = lib.create_folder(book, 'Characters')
        other = lib.create_project('Ashfall Campaign')
        weird = 'He said "run" / now: why?'
        p = lib.create_note(book, weird)
        check("symbol title round-trips", lib.title(p) == weird, repr(lib.title(p)))
        p2 = lib.rename_note(p, 'Act 1 <dawn> | "Embers"...')
        check("rename keeps symbols", lib.title(p2) == 'Act 1 <dawn> | "Embers"...', repr(lib.title(p2)))
        check("rename to same title is a no-op", lib.rename_note(p2, 'Act 1 <dawn> | "Embers"...') == p2)
        n1 = lib.create_note(book, 'Chapter One'); n2 = lib.create_note(book, 'Chapter Two')
        n3 = lib.create_note(ch, 'Villain notes'); n4 = lib.create_note(other, 'Session 1')
        step(app.refresh_library)
        # ---------------- lazy tree: closed folders are not filled
        check("closed folder not filled", step(lambda: app.tree.get_children(book)) == ("lazy:" + book,),
              step(lambda: app.tree.get_children(book)))
        # ---------------- click a folder name: opens it and shows it; double-click doesn't close it
        def click_name(iid):
            tv = app.tree; tv.update()
            x, y = row_xy(tv, iid)
            app._tree_press(Ev(x=x, y=y, x_root=tv.winfo_rootx() + x, y_root=tv.winfo_rooty() + y))
            app._tree_release(Ev(x=x, y=y, x_root=tv.winfo_rootx() + x, y_root=tv.winfo_rooty() + y))
            return bool(tv.item(iid, "open")) if os.path.isdir(iid) else None
        check("click folder name opens it", step(lambda: click_name(book)) is True)
        check("shows the folder", step(lambda: app.view is app.projview and app.current_project == book))
        def dbl(iid):
            tv = app.tree; x, y = row_xy(tv, iid); click_name(iid); app._tree_double(Ev(x=x, y=y)); return bool(tv.item(iid, "open"))
        def tri(iid):
            tv = app.tree; tv.update(); bb = tv.bbox(iid)
            app._tree_press(Ev(x=bb[0] + 8, y=bb[1] + bb[3] // 2)); return bool(tv.item(iid, "open"))
        time.sleep(0.3)
        check("click on the open folder's name closes it", step(lambda: click_name(book)) is False)
        time.sleep(0.3)
        check("...and again opens it", step(lambda: click_name(book)) is True)
        time.sleep(0.3)
        st1 = step(lambda: tri(book)); st2 = step(lambda: tri(book))
        check("triangle click closes; an instant 2nd click is a bounce", st1 is False and st2 is False, (st1, st2))
        time.sleep(0.3)
        check("triangle click after a pause opens again", step(lambda: tri(book)) is True)
        # nav: clicking Unassigned works even if it already looks selected
        def nav_click(iid):
            tv = app.nav; tv.update(); bb = tv.bbox(iid); x, y = bb[0] + 40, bb[1] + bb[3] // 2
            tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y)
            tv.update()
            return app.view is app.inbox
        step(lambda: app._select_nav("inbox")); step(lambda: app.open_note(n1))
        check("click on already-selected Unassigned goes there", step(lambda: nav_click("inbox")))
        # ---------------- New note in Unassigned (typed, no speaking)
        btns = step(lambda: [w.cget("text") for w in app.inbox.winfo_children()[2].winfo_children()])
        check("Unassigned has + New note, no Open button", "+  New note" in btns and "Open" not in btns, btns)
        ASK.append('Typed idea: "the lantern"')
        step(lambda: [w for w in app.inbox.winfo_children()[2].winfo_children() if w.cget("text") == "+  New note"][0].invoke())
        newp = step(lambda: app.editor.path)
        check("new typed note created in Unassigned & opened", newp and lib.is_inbox(os.path.dirname(newp))
              and lib.title(newp) == 'Typed idea: "the lantern"', newp)
        step(lambda: app.editor.text.insert("end", "Typing without speaking works."))
        step(app.show_inbox)
        # double-click a row opens exactly that row
        def dbl_list():
            tv = app.inbox._tv; tv.update(); x, y = row_xy(tv, newp, 0.5)
            app.ws.close_others(); app._list_double(app.inbox, Ev(x=x, y=y)); return app.editor.path
        check("double-click a list row opens it", step(dbl_list) == newp)
        # right-click menu offers Open / Open side by side
        step(app.show_inbox)
        def rc_list():
            tv = app.inbox._tv; tv.update(); x, y = row_xy(tv, newp, 0.5)
            MENUS.clear(); app._list_menu(app.inbox, Ev(x=x, y=y)); return MENUS[-1][1]
        labels = step(rc_list)
        check("right-click: Open + Open side by side", "Open" in labels and "Open side by side" in labels, labels[:5])
        # ---------------- shift-click multi select + bulk colour from the right-click menu
        step(app.refresh_library); step(lambda: app._tree_open(book, True)); step(lambda: app._tree_open(other, True))
        def multi():
            tv = app.tree; tv.update()
            tv.selection_set((n1, n2, n4))
            x, y = row_xy(tv, n2); MENUS.clear(); app._on_tree_right(Ev(x=x, y=y)); return MENUS[-1]
        menu, labels = step(multi)
        check("bulk menu for 3 items", any("Colour label (all 3)" in l for l in labels), labels[:4])
        def apply_colour():
            for i, l in enumerate(labels):
                if l.startswith("Colour label"):
                    sub = menu.nametowidget(menu.entrycget(i, "menu")); sub.invoke(0); return True
        step(apply_colour)
        cols = [lib.note_info(x)["color"] for x in (n1, n2, n4)]
        check("colour applied to all selected", len(set(cols)) == 1 and cols[0], cols)
        # ---------------- import into Unassigned doesn't expand Books & campaigns
        step(lambda: app.open_note(n3))           # reveals Characters
        step(lambda: app._tree_open(book, False)); step(lambda: app.show_inbox())
        src = os.path.join(H, "imported idea.txt"); open(src, "w").write("A loose idea from a file.\n")
        import nabu_share
        step(lambda: nabu_share.import_files(app, [src], C.INBOX_DIR, ask=False))
        check("import into Unassigned leaves the book closed", not step(lambda: app.tree.item(book, "open")))
        # ---------------- side by side, sash, pop-out, dock
        step(lambda: [app.ws.close_editor(e) for e in list(app.ws.editors())])
        step(lambda: app.open_note(n1)); step(lambda: app.open_note(n2, side=True)); step(lambda: app.open_note(n4, side=True))
        check("3 notes side by side", step(lambda: len(app.ws.panes)) == 3)
        check("opening an open note doesn't duplicate", (step(lambda: app.open_note(n2, side=True)) and step(lambda: len(app.ws.panes))) == 3)
        time.sleep(0.8)
        ws_ = [step(lambda i=i: app.ws.panes[i].box.winfo_width()) for i in range(3)]
        check("even widths", max(ws_) - min(ws_) <= 3, ws_)
        shot("47_side_by_side", 1.0)
        def drag_sash():
            s0 = app.ws.sashes[0]; a = app.ws.area
            app.ws._drag_sash(Ev(x_root=a.winfo_rootx() + int(a.winfo_width() * 0.5)), 0); a.update()
            return [p.box.winfo_width() for p in app.ws.panes]
        w2 = step(drag_sash)
        # (at 125% display scaling each page has a bigger minimum width, so the bar may stop sooner than on
        # Linux: check that it moved and that the two pages beside it traded the width)
        grew, shrank = w2[0] - ws_[0], ws_[1] - w2[1]
        check("dragging the grab bar resizes", grew >= 20 and abs(grew - shrank) <= 4 and abs(w2[2] - ws_[2]) <= 4,
              (ws_, w2))
        step(app.ws.even)
        # pop out by dragging the name out of the window
        def drag_out():
            ed = app.ws.panes[2].cur
            x, y = ed.title.winfo_rootx() + 5, ed.title.winfo_rooty() + 5
            app.ws._tab_press(Ev(x_root=x, y_root=y), ed)
            app.ws._tab_motion(Ev(x_root=x + 40, y_root=y + 40), ed)
            far = (app.root.winfo_rootx() + app.root.winfo_width() + 300, app.root.winfo_rooty() + 200)
            app.ws._tab_release(Ev(x_root=far[0], y_root=far[1]), ed)
        step(drag_out); time.sleep(0.5)
        check("dragged out -> own window", step(lambda: len(app.ws.popouts)) == 1 and step(lambda: len(app.ws.panes)) == 2)
        po_path = step(lambda: app.ws.popouts[0].ed.path)
        check("pop-out shows the note", po_path == n4, po_path)
        step(lambda: app.ws.popouts[0].win.geometry("700x700+900+100")); shot("47_popout", 1.0)
        # rename while popped out -> its window follows
        ASK.append('Session 1 / "The Ambush"')
        step(lambda: app.rename_note(n4))
        n4b = step(lambda: app.ws.popouts[0].ed.path)
        check("rename follows into pop-out", lib.title(n4b) == 'Session 1 / "The Ambush"', n4b)
        # dock back
        step(lambda: app.ws.dock(app.ws.popouts[0]))
        check("docked back (as a tab)", step(lambda: len(app.ws.popouts)) == 0 and step(lambda: bool(app.ws.editors_for(n4b))))
        # trash a note open side by side -> its page closes
        np_ = step(lambda: len(app.ws.panes))
        step(lambda: app.trash_notes([n2]))
        check("deleting closes it", not step(lambda: app.ws.editors_for(n2)),
              step(lambda: [[e.path for e in p.eds] for p in app.ws.panes]))
        step(app.ws.close_others)
        check("join into one page", step(lambda: len(app.ws.panes)) == 1)
        # ---------------- big library: speed
        big = lib.create_project('Big Saga')
        import nabu_doc as nd
        t0 = time.time()
        for i in range(3000):
            d = nd.empty_doc(); d["items"] = [{"t": "Note %d\n" % i, "g": ["st:title"]}, {"t": "Some words for the preview of note %d.\n" % i, "g": []}]
            nd.save_doc(os.path.join(big, "Note %04d.nabu" % i), d)
        for i in range(1500):
            d = nd.empty_doc(); d["items"] = [{"t": "Idea %d words words\n" % i, "g": []}]
            nd.save_doc(os.path.join(C.INBOX_DIR, "2026-10-%02d 10.%02d – idea %d.nabu" % (1 + i % 28, i % 60, i)), d)
        print("made 4500 notes in %.1fs" % (time.time() - t0))
        lib._info_cache.clear(); lib._cache_state["loaded"] = True
        t = time.time(); step(app.refresh_library); tr = time.time() - t
        check("sidebar refresh with 4500 notes is quick", tr < 0.5, "%.3fs" % tr)
        t = time.time(); step(app.show_inbox); ti = time.time() - t
        check("Unassigned (1500) shows quickly (first rows)", ti < 1.5, "%.3fs" % ti)
        while step(lambda: len(app.inbox._tv.get_children())) < 1502: time.sleep(0.1)
        print("   all inbox rows in %.2fs" % (time.time() - t))
        t = time.time(); step(lambda: app._tree_open(big, True)); tb = time.time() - t
        check("opening a 3000-note folder in the sidebar", tb < 3.0, "%.3fs" % tb)
        step(lambda: app.ws.save_all()); lib.save_cache()
        lib._info_cache.clear(); lib._cache_state["loaded"] = False
        t = time.time(); step(lambda: app.show_project(big)); tp = time.time() - t
        while step(lambda: len(app.projview._tv.get_children())) < 3000: time.sleep(0.1)
        tp2 = time.time() - t
        check("3000-note folder list after restart (cache on disk)", tp < 1.0, "first rows %.3fs, all %.2fs" % (tp, tp2))
        t = time.time(); step(app.show_home); check("Home is quick", time.time() - t < 0.5, "%.3fs" % (time.time() - t))
        step(app.show_inbox); shot("47_inbox", 0.8)
    except Exception:
        traceback.print_exc()
    try:
        lg = open(os.path.join(H, "logs", "nabu.log"), encoding="utf-8").read()
        errs = [l for l in lg.splitlines() if " ERROR " in l or "Traceback" in l or "Error:" in l]
        print("LOG ERRORS:", len(errs)); print("\n".join(errs[:15]))
        if errs: print(lg[lg.find(errs[0]) : lg.find(errs[0]) + 2500])
    except Exception as e:
        print("no log", e)
    print("RESULT %d/%d passed" % (sum(OK), len(OK)))
    os._exit(0)
threading.Thread(target=go, daemon=True).start(); app.run()
