"""v4.7.1 bug hunt: drive the app with real (synthesized) mouse/keyboard events."""
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
import nabu_main as M, nabu_config as C, nabu_library as lib, nabu_theme as T, nabu_workspace as WS
import tkinter as tk

MENUS = []
def cap_popup(self, x, y, entry=""):
    labels = []
    for i in range((self.index("end") or -1) + 1):
        try:
            labels.append(self.entrycget(i, "label"))
        except tk.TclError:
            labels.append("---")
    MENUS.append((self, labels))
tk.Menu.tk_popup = cap_popup
ASK = []
T.ask_string = lambda *a, **k: ASK.pop(0) if ASK else None
T.confirm = lambda *a, **k: True
INFOS = []
T.info = lambda *a, **k: INFOS.append(a[-1] if a else "")

app = M.App(); app._server = M._claim_instance()
OK = []
def check(name, cond, extra=""):
    OK.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, extra if not cond or extra else "")
def step(fn):
    ev = threading.Event(); r = {}
    def go():
        try: r['v'] = fn()
        except Exception as e: r['e'] = repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(60); return r.get('v', r.get('e'))
def idle(t=0.25): time.sleep(t); step(lambda: app.root.update())

def rowpos(tv, iid, fx=None):
    tv.see(iid); tv.update(); bb = tv.bbox(iid)
    if not bb: return None
    x = bb[0] + (int(bb[2] * fx) if fx is not None else min(bb[2] - 10, 150))
    return x, bb[1] + bb[3] // 2
def click(w, x, y, state=0, button=1, release=True, dx=0):
    w.event_generate("<ButtonPress-%d>" % button, x=x, y=y, state=state, warp=False)
    if dx:
        w.event_generate("<B1-Motion>", x=x + dx, y=y, state=state | 0x100)
    if release:
        w.event_generate("<ButtonRelease-%d>" % button, x=x + dx, y=y, state=state | (0x100 if button == 1 else 0x400))
    w.update()
def tree_click(iid, state=0, fx=None, dx=0):
    tv = app.tree; x, y = rowpos(tv, iid, fx); click(tv, x, y, state, dx=dx)
def tree_dbl(iid, fx=None):
    tv = app.tree; x, y = rowpos(tv, iid, fx)
    for _ in range(2):
        tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100)
    tv.update()
def tri(iid):
    tv = app.tree; tv.see(iid); tv.update(); bb = tv.bbox(iid)
    x, y = bb[0] + 6, bb[1] + bb[3] // 2
    tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100); tv.update()
    return bool(tv.item(iid, "open"))
class Ev:
    def __init__(s, **k): s.state = 0; s.x = s.y = 0; s.__dict__.update(k)

def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1600x950+0+0')); idle(0.5)
        book = lib.create_project('The Hollow Crown'); ch = lib.create_folder(book, 'Characters')
        other = lib.create_project('Ashfall Campaign')
        n1 = lib.create_note(book, 'Chapter One'); n2 = lib.create_note(book, 'Chapter Two')
        n3 = lib.create_note(ch, 'Villain notes'); n4 = lib.create_note(other, 'Session 1')
        n5 = lib.create_note(other, 'Session 2')
        step(app.refresh_library)
        # ===== sidebar, real events
        step(lambda: tree_click(book))
        check("click on a book's name opens & shows it", step(lambda: bool(app.tree.item(book, "open"))) and
              step(lambda: app.view is app.projview and app.current_project == book))
        time.sleep(0.3); step(lambda: tree_click(book))
        check("clicking the open book's name closes it", not step(lambda: bool(app.tree.item(book, "open"))))
        time.sleep(0.3); step(lambda: tree_click(book))
        time.sleep(0.3)
        a = step(lambda: tri(book)); time.sleep(0.3); b = step(lambda: tri(book))
        check("triangle: close, then a click 0.3 s later opens again", a is False and b is True, (a, b))
        time.sleep(0.3)
        a = step(lambda: tri(book)); b = step(lambda: tri(book))    # within ~ms: a bounce
        check("triangle: a bounce (<0.2 s) counts once", a is False and b is False, (a, b))
        time.sleep(0.3); step(lambda: tri(book))
        def dbl_tri():
            tv = app.tree; tv.update(); bb = tv.bbox(book); x, y = bb[0] + 6, bb[1] + bb[3] // 2
            tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100)
            time.sleep(0.25)
            tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100)
            tv.update(); return bool(tv.item(book, "open"))
        before = step(lambda: bool(app.tree.item(book, "open")))
        after = step(dbl_tri)
        check("triangle: two clicks 0.25 s apart (a Windows 'double-click') toggle twice", before == after, (before, after))
        step(lambda: app._tree_open(book, True))
        step(lambda: tree_click(n1))
        check("click a note opens it", step(lambda: app.editor.path) == n1)
        step(lambda: tree_click(n2, state=0x1))
        check("shift-click selects without opening", step(lambda: len(app.tree.selection())) == 2 and step(lambda: app.editor.path) == n1,
              step(lambda: app.tree.selection()))
        step(lambda: tree_click(n2, state=0x4))
        check("ctrl-click toggles out of the selection", step(lambda: app.tree.selection()) == (n1,), step(lambda: app.tree.selection()))
        def rc(iid):
            tv = app.tree; x, y = rowpos(tv, iid); MENUS.clear()
            tv.event_generate("<ButtonPress-3>", x=x, y=y); tv.update(); return MENUS[-1][1] if MENUS else None
        view0 = step(lambda: app.view)
        labels = step(lambda: rc(n5)) if step(lambda: app.tree.exists(n5)) else None
        if labels is None:
            step(lambda: app._tree_open(other, True)); labels = step(lambda: rc(n5))
        check("right-click a note: menu, selects it, opens nothing", labels and "Open side by side" in labels and
              step(lambda: app.view) is view0 and step(lambda: app.tree.selection()) == (n5,), labels)
        step(lambda: tree_click(n4, state=0x4))
        labels = step(lambda: rc(n4))
        check("right-click on a 2-item selection: bulk menu", labels and labels[0].startswith("Selected: 2"), labels)
        # shaky click (8 px) is still a click
        step(lambda: app.show_home())
        step(lambda: tree_click(n2, dx=8))
        check("shaky click (8 px) still opens", step(lambda: app.editor.path) == n2 and step(lambda: app.view is app.ws.frame))
        # drag a note into another folder with the mouse -> moves; open editor follows
        def drag_into(src, dst):
            tv = app.tree; x, y = rowpos(tv, src); x2, y2 = rowpos(tv, dst, 0.4)
            rx, ry = tv.winfo_rootx(), tv.winfo_rooty()
            tv.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx + x, rooty=ry + y)
            for k in range(1, 7):
                xi, yi = x + (x2 - x) * k // 6, y + (y2 - y) * k // 6
                tv.event_generate("<B1-Motion>", x=xi, y=yi, rootx=rx + xi, rooty=ry + yi, state=0x100)
            tv.event_generate("<ButtonRelease-1>", x=x2, y=y2, rootx=rx + x2, rooty=ry + y2, state=0x100)
            tv.update()
        step(lambda: drag_into(n2, ch)); idle(0.4)
        moved = os.path.join(ch, 'Chapter Two.nabu')
        check("mouse-drag a note into a sub-folder", os.path.exists(moved) and not os.path.exists(n2))
        check("its open page follows the move", step(lambda: app.editor.path) == moved, step(lambda: app.editor.path))
        n2 = moved
        # ===== nav
        step(lambda: app.open_note(n4))
        def nav_click(iid):
            tv = app.nav; tv.update(); bb = tv.bbox(iid); x, y = bb[0] + 40, bb[1] + bb[3] // 2
            tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100); tv.update()
        step(lambda: app._select_nav("inbox"))
        step(lambda: nav_click("inbox"))
        check("Unassigned click works when already highlighted", step(lambda: app.view is app.inbox))
        step(lambda: nav_click("home")); check("Home click", step(lambda: app.view is app.home))
        step(lambda: nav_click("trash")); check("Trash click", step(lambda: app.view is app.trashview))
        # ===== new typed note + list double-click / Enter / middle
        step(app.show_inbox)
        ASK.append('Draft: "The Lantern" / Part 2?')
        step(lambda: app.new_note())
        np_ = step(lambda: app.editor.path)
        check("Ctrl+N style new note from Unassigned lands in Unassigned with its symbols",
              np_ and lib.is_inbox(os.path.dirname(np_)) and lib.title(np_) == 'Draft: "The Lantern" / Part 2?', np_)
        step(lambda: app.editor.text.insert("end", "\nTyped words."))
        step(app.show_inbox)
        check("leaving saves the typing", "Typed words" in open(np_, encoding="utf-8").read())
        def list_dbl(f, iid):
            tv = f._tv; x, y = rowpos(tv, iid, 0.5)
            for _ in range(2):
                tv.event_generate("<ButtonPress-1>", x=x, y=y); tv.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100)
            tv.update()
        step(lambda: list_dbl(app.inbox, np_))
        check("double-click in Unassigned opens the note", step(lambda: app.editor.path) == np_ and step(lambda: app.view is app.ws.frame))
        step(lambda: app.show_project(other))
        def list_enter():
            tv = app.projview._tv; tv.selection_set(n5); tv.focus(n5); tv.focus_set(); tv.event_generate("<Return>"); tv.update()
        step(list_enter)
        check("Enter in a folder list opens the note", step(lambda: app.editor.path) == n5)
        step(lambda: app.show_project(other))
        def list_mid():
            tv = app.projview._tv; x, y = rowpos(tv, n4, 0.5); tv.event_generate("<ButtonPress-2>", x=x, y=y); tv.update()
        step(list_mid)
        check("middle-click opens side by side", step(lambda: [lib.title(p.cur.path) for p in app.ws.panes])[-1] == "Session 1",
              step(lambda: [[e.path for e in p.eds] for p in app.ws.panes]))
        # (tabs, snapping and pop-outs are tested in test_48.py)
        step(lambda: [app.ws.close_editor(e) for e in list(app.ws.editors())])
        # deleting the book closes its open notes (tabs, pages and own windows)
        step(lambda: app.open_note(n1)); step(lambda: app.open_note(n3, side=True))
        step(lambda: app.ws.pop_out(app.ws.editors_for(n3)[0])); idle(0.4)
        step(lambda: app._trash_mixed([book])); idle(0.3)
        check("deleting a book closes its notes everywhere", step(lambda: len(app.ws.popouts)) == 0 and
              not step(lambda: [e.path for e in app.ws.editors()]), step(lambda: [e.path for e in app.ws.editors()]))
        # ===== trash: right-click only
        step(app.show_trash)
        btns = step(lambda: [w.cget("text") for w in app.trashview.winfo_children()[2].winfo_children()])
        check("Trash has only the Empty trash button", btns == ["Empty trash"], btns)
        def trash_rc():
            tv = app.trashview._tv; kids = tv.get_children(); x, y = rowpos(tv, kids[0], 0.5)
            MENUS.clear(); tv.event_generate("<ButtonPress-3>", x=x, y=y); tv.update(); return MENUS[-1]
        m, labels = step(trash_rc)
        check("right-click in Trash: Restore / Delete permanently", labels[0].startswith("Restore") and
              any(l.startswith("Delete permanently") for l in labels), labels)
        step(lambda: m.invoke(0)); idle(0.3)
        check("Restore from the right-click menu works", os.path.isdir(book) and os.path.exists(n1))
        step(app.refresh_library)
        # ===== title with symbols edited on the page renames the note
        step(lambda: app.open_note(n1))
        def retitle():
            ed = app.editor; line, txt = ed.title_line(); t = ed.text
            t.delete(line, line + " lineend"); t.insert(line, 'Chapter "One": Ash/Ember', ("st:title",))
            ed._mark_changed(); ed._idle_work(); return ed.path
        newp = step(retitle); idle(0.3)
        check("title on the page with quotes & / renames the note", lib.title(newp) == 'Chapter "One": Ash/Ember', newp)
        check("sidebar shows the new title", step(lambda: app.tree.item(newp, "text")).strip() == 'Chapter "One": Ash/Ember'
              if step(lambda: app.tree.exists(newp)) else False)
        n1 = newp
        # ===== dictation lands in the right note even after clicking into another one
        step(lambda: app.open_note(n4, side=True))
        def start_dict():
            ed1 = [p.cur for p in app.ws.panes if p.cur.path == n1][0]
            app.ws._activate(ed1); ed1.text.mark_set("insert", "end-1c")
            app._engine_event("recording_started", {"mode": "edit"})
            other = [p.cur for p in app.ws.panes if p.cur.path == n4][0]
            app.ws._activate(other)                   # user clicks into the other note meanwhile
            app._engine_event("recording_finished", {"mode": "edit", "path": "x.wav"})
            app._tx_event("done", {"mode": "edit", "note": n1, "paragraphs": ["Dictated sentence."]})
            return ed1.text.get("1.0", "end"), other.text.get("1.0", "end")
        app.transcriber.submit = lambda *a, **k: None
        t1, t2 = step(start_dict)
        check("dictation goes into the note it was started in", "Dictated sentence." in t1 and "Dictated" not in t2)
        # ===== import default folder
        import nabu_share
        got = {}
        nabu_share.import_dialog = lambda app_, folder=None: got.update(folder=folder)
        step(app.show_home); step(lambda: app.import_dialog())
        check("gear > Import from Home goes to Unassigned", got.get("folder") == C.INBOX_DIR)
        step(lambda: app.show_project(other)); step(lambda: app.import_dialog())
        check("Import while looking at a folder goes there", got.get("folder") == other)
        # ===== settings: new checkbox saved
        step(app.open_settings)
        def toggle_orig():
            st = app.settings_win; st.orig_sound.set(False); st.save()
        step(toggle_orig)
        check("Settings: 'natural sound' option is saved", json.load(open(C.CONFIG_PATH)).get("transcribe_original") is False)
        # ===== cache on disk
        step(app._save_cache); time.sleep(0.6)
        check("note summaries cached on disk", os.path.exists(os.path.join(H, "cache", "noteinfo.json")))
        check("Home shows recent notes", step(lambda: (app.show_home(), len(app.recent.winfo_children()))[1]) >= 3)
    except Exception:
        traceback.print_exc()
    try:
        lg = open(os.path.join(H, "logs", "nabu.log"), encoding="utf-8").read()
        errs = [l for l in lg.splitlines() if (" ERROR " in l or "Error" in l) and "tkinterdnd2" not in l and "pystray" not in l
                and "tray unavailable" not in l]
        print("UI ERRORS IN LOG:", len(errs))
        for e in errs[:5]:
            i = lg.find(e); print(lg[max(0, i - 1500): i + 300]); print("-----")
    except Exception as e:
        print("no log", e)
    print("RESULT %d/%d passed" % (sum(OK), len(OK)))
    os._exit(0)
threading.Thread(target=go, daemon=True).start(); app.run()
