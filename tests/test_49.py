"""v4.9: even side-by-side pages, compact toolbar + More tools, right-click tools, no flicker,
drop highlight colour, 40 colour labels."""
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
import nobu_main as M, nobu_config as C, nobu_library as lib, nobu_theme as T
import tkinter as tk

MENUS = []
def cap_popup(self, x, y, entry=""):
    MENUS.append(self)
tk.Menu.tk_popup = cap_popup
def labels(m):
    out = []
    for i in range((m.index("end") or -1) + 1):
        out.append("---" if m.type(i) == "separator" else m.entrycget(i, "label"))
    return out
COUNT = {"deiconify": 0, "withdraw": 0}
_dei, _wd = tk.Wm.wm_deiconify, tk.Wm.wm_withdraw
def dei(self): COUNT["deiconify"] += 1; return _dei(self)
def wd(self): COUNT["withdraw"] += 1; return _wd(self)
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
def rowpos(tv, iid, fx=0.5):
    tv.see(iid); tv.update(); bb = tv.bbox(iid); return bb[0] + int(bb[2] * fx), bb[1] + bb[3] // 2

def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1700x980+0+0')); idle(0.5)
        book = lib.create_project('The Hollow Crown')
        a = lib.create_note(book, 'Chapter One')
        b = lib.create_note(C.INBOX_DIR, 'A loose idea with a much longer title than the other one')
        step(lambda: app.open_note(a)); step(lambda: app.open_note(b, side=True)); idle(0.8)
        # ===== even pages
        def tops():
            return [(p.cur.desk.winfo_rooty(), p.cur.ribbon.winfo_height(), p.cur.head.winfo_height(),
                     p.cur.rib_box.winfo_height(), p.cur.banner.winfo_ismapped(), p.cur.action.winfo_ismapped(),
                     p.cur.rib_box.winfo_rooty(), p.cur.head.winfo_rooty(), p.box.winfo_rooty(), p.tabbar.winfo_height())
                    for p in app.ws.panes]
        t = step(tops)
        if len(set(x[:3] for x in t)) != 1:
            print("MISALIGNED first look", t)
            idle(2.0); t = step(tops); print("after 2 s", t)
            step(lambda: app.root.geometry('1700x981+0+0')); idle(1.0); print("after a resize", step(tops))
            def detail():
                ed = app.ws.panes[0].cur
                return (ed.frame.winfo_height(), ed.frame.winfo_reqheight(), ed.rib_box.winfo_reqheight(),
                        ed.ribbon.winfo_reqheight(), ed.ribbon.winfo_manager(), ed.rib_box.pack_slaves(),
                        ed.frame.pack_slaves(), app.ws.panes[0].body.winfo_height())
            print("detail", step(detail))
            def probe():
                ed = app.ws.panes[0].cur
                out = {"propagate": ed.rib_box.pack_propagate(), "info": ed.ribbon.pack_info(),
                       "rib_mapped": ed.ribbon.winfo_ismapped(), "box_mapped": ed.rib_box.winfo_ismapped(),
                       "rib_geom": (ed.ribbon.winfo_x(), ed.ribbon.winfo_y(), ed.ribbon.winfo_width(), ed.ribbon.winfo_height())}
                ed.rib_box.update_idletasks()
                out["after_idle"] = ed.rib_box.winfo_reqheight()
                ed.ribbon.pack_forget(); ed.ribbon.pack(side="top", fill="x", padx=16, pady=(4, 0)); ed.rib_box.update_idletasks()
                out["after_repack"] = ed.rib_box.winfo_reqheight()
                return out
            print("probe", step(probe))
        check("side-by-side pages line up (same page top, toolbar and header height)", len(set(x[:3] for x in t)) == 1, t)
        step(lambda: (setattr(app.ws, "fracs", [0.68, 0.32]), app.ws._layout())); idle(0.8)
        t = step(tops)
        check("...even when one page is wide and one narrow", len(set(x[0] for x in t)) == 1, t)
        step(app.ws.even); idle(0.5)
        # ===== compact toolbar
        def rib_state():
            out = []
            for p in app.ws.panes:
                ed = p.cur
                vis = [bool(g.winfo_ismapped()) for g in ed._groups]
                out.append((ed.ribbon_compact(), vis, ed._g_more.winfo_ismapped()))
            return out
        st = step(rib_state)
        check("side by side: compact toolbar = style/font/size + bold/italic/underline + More tools",
              all(c and v[:2] == [True, True] and not any(v[2:]) and mo for c, v, mo in st), st)
        shot("49_side_by_side", 0.6)
        def more_labels():
            ed = app.ws.panes[0].cur; MENUS.clear(); ed._more_tools(ed._more_btn2); return labels(MENUS[-1])
        ml = step(more_labels)
        want = ["Text colour", "Highlight", "Align", "Insert", "Find & replace", "Next spelling mistake", "Thesaurus"]
        check("More tools holds everything else", all(any(l.startswith(w) for l in ml) for w in want) and
              any("Dictate here" in l for l in ml), ml)
        def toggle():
            p = app.ws.panes[0]; app.ws.toggle_ribbon(p.cur); p.cur.ribbon.update()
            full = not p.cur.ribbon_compact() and all(g.winfo_ismapped() for g in p.cur._groups)
            app.ws.toggle_ribbon(p.cur); return full, p.cur.ribbon_compact()
        check("☰ switches to all tools and back", step(toggle) == (True, True))
        step(app.ws.close_others); idle(0.4)
        check("back to one page: all tools", step(lambda: not app.ws.panes[0].cur.ribbon_compact()))
        # ===== right-click on the page
        def rclick():
            ed = app.editor; MENUS.clear()
            ed.text.event_generate("<Button-3>", x=200, y=40, rootx=ed.text.winfo_rootx() + 200,
                                   rooty=ed.text.winfo_rooty() + 40)
            return labels(MENUS[-1])
        rl = step(rclick)
        check("right-click on the page: picture, find, spelling, thesaurus",
              all(any(l.startswith(w) for l in rl) for w in ("Insert picture", "Find & replace", "Next spelling", "Thesaurus")), rl)
        # ===== no flicker: drag a note from a list over the same spot many times
        step(lambda: app.open_note(b, side=True)); step(lambda: app.show_project(book)); idle(0.4)
        tk.Wm.wm_deiconify, tk.Wm.wm_withdraw = dei, wd
        def list_drag_hover():
            tv = app.projview._tv; x, y = rowpos(tv, a)
            rx, ry = tv.winfo_rootx(), tv.winfo_rooty()
            c = app.content; cx, cy, cw, ch = c.winfo_rootx(), c.winfo_rooty(), c.winfo_width(), c.winfo_height()
            tv.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx + x, rooty=ry + y)
            COUNT.update(deiconify=0, withdraw=0)
            tx, ty = cx + cw - 80, cy + ch // 2
            tv.event_generate("<B1-Motion>", x=tx - rx, y=ty - ry, rootx=tx, rooty=ty, state=0x100)
            snap0 = app.ws._snap_win
            for k in range(40):                       # wiggle inside the right-hand zone
                xx, yy = tx - (k % 7) * 9, ty + (k % 5) * 13
                tv.event_generate("<B1-Motion>", x=xx - rx, y=yy - ry, rootx=xx, rooty=yy, state=0x100)
            tv.update()
            counts = dict(COUNT)
            same_win = app.ws._snap_win is snap0
            bg = app.ws._snap_win.cget("bg")
            tv.event_generate("<ButtonRelease-1>", x=tx - rx, y=ty - ry, rootx=tx, rooty=ty, state=0x100)
            tv.update()
            return counts, same_win, bg
        counts, same_win, bg = step(list_drag_hover)
        tk.Wm.wm_deiconify, tk.Wm.wm_withdraw = _dei, _wd
        check("no flicker: 40 mouse moves in one spot = the highlight shown once, never hidden",
              counts["deiconify"] <= 2 and counts["withdraw"] == 0 and same_win, counts)
        check("highlight uses the accent colour by default", bg.lower() == T.ACCENT.lower(), bg)
        # ===== drop highlight colour from My colours
        step(app.open_settings)
        import nobu_ui
        def theme_editor():
            te = nobu_ui.ThemeEditor(app.root, app, app.settings_win)
            te.drop_col = "#ff3366"; te.drop_alpha.set(0.5); te._drop_changed()
            te.win.update(); return te
        te = step(theme_editor)
        shot("49_my_colours", 0.6)
        cfg = json.load(open(C.CONFIG_PATH))
        check("My colours: drop highlight colour & strength saved at once", cfg.get("drop_color") == "#ff3366" and
              abs(cfg.get("drop_alpha", 0) - 0.5) < 0.01, (cfg.get("drop_color"), cfg.get("drop_alpha")))
        step(lambda: (te.win.destroy(), app.settings_win.cancel()))
        step(lambda: app.show_project(book)); idle(0.3)
        def drag_again():
            tv = app.projview._tv; x, y = rowpos(tv, a); rx, ry = tv.winfo_rootx(), tv.winfo_rooty()
            c = app.content; tx, ty = c.winfo_rootx() + c.winfo_width() - 80, c.winfo_rooty() + c.winfo_height() // 2
            tv.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx + x, rooty=ry + y)
            for k in range(1, 5):
                tv.event_generate("<B1-Motion>", x=x + (tx - rx - x) * k // 4, y=y, rootx=rx + x + (tx - rx - x) * k // 4,
                                  rooty=ty, state=0x100)
            tv.update(); w = app.ws._snap_win
            res = (w.cget("bg"), app.ws._snap_look[1])
            tv.event_generate("<ButtonRelease-1>", x=x, y=y, rootx=rx + x, rooty=ry + y, state=0x100); tv.update()
            return res
        bg, al = step(drag_again)
        check("the new colour and strength are used straight away", bg.lower() == "#ff3366" and abs(al - 0.5) < 0.02, (bg, al))
        # ===== 40 colour labels in columns
        def colour_menu():
            m = app._color_menu(app.root, [a])
            n = m.index("end") + 1
            cols = sum(1 for i in range(n) if m.type(i) != "separator" and int(m.entrycget(i, "columnbreak") or 0))
            return n, cols, labels(m)
        n, cols, lab = step(colour_menu)
        check("40 preset colours (+ custom / none) in 9 columns", n == 42 and cols == 8, (n, cols))
        def pick():
            m = app._color_menu(app.root, [a]); m.invoke(lab.index("■  Lagoon")); return lib.note_info(a)["color"]
        check("picking one of the new colours works", step(pick) == "#2fa9b5")
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
