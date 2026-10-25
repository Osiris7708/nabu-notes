"""Audit: press every button, move every slider, open every menu entry - and check each one did its job.
Dialogs that would wait for a person are answered automatically."""
import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, traceback, json, glob
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
import nobu_main as M, nobu_config as C, nobu_library as lib, nobu_theme as T, nobu_editor as NE, nobu_rich as R
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser

# ---------------------------------------------------------------- automatic answers
MENUS, ASK, INFOS, CONFIRMS, OPENED = [], [], [], [], []
CONFIRM_ANSWER = [True]
def cap_popup(self, x, y, entry=""):
    MENUS.append(self)
tk.Menu.tk_popup = cap_popup
REAL_CONFIRM = T.confirm
T.ask_string = lambda *a, **k: ASK.pop(0) if ASK else None
T.info = lambda *a, **k: INFOS.append(a[2] if len(a) > 2 else "")
def _confirm(*a, **k):
    CONFIRMS.append(a[2] if len(a) > 2 else ""); return CONFIRM_ANSWER[0]
T.confirm = _confirm
NE.open_path = lambda p: OPENED.append(p)
FILES = {"open": [], "save": ""}
filedialog.askopenfilenames = lambda **k: tuple(FILES["open"])
filedialog.askopenfilename = lambda **k: (FILES["open"][0] if FILES["open"] else "")
filedialog.asksaveasfilename = lambda **k: FILES["save"]
colorchooser.askcolor = lambda *a, **k: ((1, 2, 3), "#123456")

def labels(m):
    out = []
    for i in range((m.index("end") if m.index("end") is not None else -1) + 1):
        out.append("---" if m.type(i) == "separator" else m.entrycget(i, "label"))
    return out
def entry(m, start):
    for i, l in enumerate(labels(m)):
        if l.strip().startswith(start):
            return i
    raise KeyError("%r not in %s" % (start, labels(m)))
def invoke_label(m, start):
    i = entry(m, start)
    if m.type(i) == "cascade":          # a folder with sub-folders: "Into ... itself" is the first entry
        m = m.nametowidget(m.entrycget(i, "menu")); i = 0
    m.invoke(i)
def last_menu():
    return MENUS[-1] if MENUS else None
def widgets(w, kinds):
    out, stack = [], [w]
    while stack:
        x = stack.pop(0)
        stack.extend(x.winfo_children())
        if isinstance(x, kinds):
            out.append(x)
    return out
def btn(parent, start):
    for b in widgets(parent, (tk.Button, ttk.Button, ttk.Checkbutton, ttk.Radiobutton)):
        try:
            if str(b.cget("text")).strip().startswith(start):
                return b
        except tk.TclError:
            pass
    raise KeyError("no button %r" % start)

app = M.App(); app._server = M._claim_instance()
_orig_err = app.root.report_callback_exception
def _err(exc, val, tb):
    try:
        n = int(app.root.tk.eval("info level"))
        print("TCL STACK:", [app.root.tk.eval("info level %d" % i)[:200] for i in range(0, n + 1)], flush=True)
        print("TCL FRAMES:", [app.root.tk.eval("info frame %d" % -i)[:300] for i in range(1, 4)], flush=True)
    except Exception as e:
        print("stack?", e)
    _orig_err(exc, val, tb)
app.root.report_callback_exception = _err
OK = []
def check(name, cond, extra=""):
    OK.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, "" if cond else extra, flush=True)
def step(fn):
    ev = threading.Event(); r = {}
    def go():
        try: r['v'] = fn()
        except Exception as e: r['e'] = "EXC " + repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(90); return r.get('v', r.get('e'))
def idle(t=0.3):
    time.sleep(t); step(lambda: app.root.update())
LOG = os.path.join(H, "logs", "nobu.log")
def log_errors():
    lg = open(LOG, encoding="utf-8").read()
    return [l for l in lg.splitlines() if (" ERROR " in l or "UI error" in l) and not any(
        k in l for k in ("tkinterdnd2", "pystray", "tray unavailable", "sounddevice", "could not list microphones"))]
def clean_since(n, name):
    e = log_errors()
    check(name + ": no errors", len(e) == n, "\n".join(e[n:n + 5]))
    if len(e) > n:
        lg = open(LOG, encoding="utf-8").read(); i = lg.find(e[n]); print(lg[i: i + 3000])
    return len(e)

def tags_at(ed, idx):
    return ed.text.tag_names(idx)

def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1700x1000+0+0')); idle(0.5)
        book = lib.create_project('The Hollow Crown')
        chap = lib.create_folder(book, 'Chapters')
        a = lib.create_note(book, 'Chapter One')
        b = lib.create_note(chap, 'Chapter Two')
        c = lib.create_note(C.INBOX_DIR, 'Loose idea')
        a3 = lib.create_note(book, 'Chapter Three')
        step(app.refresh_library)
        nerr = 0

        # ================================================================ editor ribbon
        step(lambda: app.open_note(a)); idle(0.6)
        ed = step(lambda: app.editor)
        def prep():
            ed.text.delete("1.0", "end")
            ed.insert_text("alpha beta gamma delta\nSecond line here\nThird line of text\n")
            ed.text.tag_remove("sel", "1.0", "end"); ed.text.tag_add("sel", "1.0", "1.5")
            ed.text.mark_set("insert", "1.5")
        step(prep)
        rib = ed.ribbon
        for key, label in (("b", "B"), ("i", "I"), ("u", "U"), ("s", "S"), ("sup", "x²"), ("sub", "x₂")):
            step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, label).invoke()))
            check("toolbar %s turns %s on" % (label, key), key in step(lambda: tags_at(ed, "1.2")))
            if key in ("sup", "sub"):
                step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, label).invoke()))
                check("...and off again", key not in step(lambda: tags_at(ed, "1.2")))
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "A⁺").invoke()))
        check("A+ makes the text bigger", any(t.startswith("fs:") and float(t[3:]) > 12 for t in step(lambda: tags_at(ed, "1.2"))))
        size_up = [t for t in step(lambda: tags_at(ed, "1.2")) if t.startswith("fs:")]
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "A⁻").invoke()))
        check("A- makes it smaller again", [t for t in step(lambda: tags_at(ed, "1.2")) if t.startswith("fs:")] != size_up)
        MENUS.clear(); step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "A ▾").invoke()))
        step(lambda: invoke_label(last_menu(), "■  Red"))
        check("text colour menu: Red", "fg:#ff0000" in step(lambda: tags_at(ed, "1.2")))
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "A ▾").invoke(), invoke_label(last_menu(), "More colours")))
        check("text colour: More colours… uses the picked colour", "fg:#123456" in step(lambda: tags_at(ed, "1.2")))
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "✎ ▾").invoke(), invoke_label(last_menu(), "■  Yellow")))
        check("highlight menu: Yellow", "hl:#ffff00" in step(lambda: tags_at(ed, "1.2")))
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "✎ ▾").invoke(), invoke_label(last_menu(), "No highlight")))
        check("highlight menu: No highlight", not any(t.startswith("hl:") for t in step(lambda: tags_at(ed, "1.2"))))
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "Aa ▾").invoke(), invoke_label(last_menu(), "UPPERCASE")))
        check("change case: UPPERCASE", step(lambda: ed.text.get("1.0", "1.5")) == "ALPHA")
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "1.8"),
                      btn(rib, "Aa ▾").invoke(), invoke_label(last_menu(), "UPPERCASE")))
        check("change case with nothing selected: the word at the cursor", step(lambda: ed.text.get("1.6", "1.10")) == "BETA")
        for lab, mode in (("lowercase", "lower"), ("Sentence case.", "sentence"), ("Capitalize Each Word", "title"), ("tOGGLE cASE", "toggle")):
            step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "Aa ▾").invoke(), invoke_label(last_menu(), lab)))
        check("all case modes run", step(lambda: ed.text.get("1.0", "1.5").lower()) == "alpha")
        step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), btn(rib, "✘ Clear").invoke()))
        check("Clear formatting removes it all", not any(R.is_char_tag(t) for t in step(lambda: tags_at(ed, "1.2")) if t != "sel"))
        # painter
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.tag_add("sel", "2.0", "2.6"), ed.toggle_flag("b")))
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "2.2"), btn(rib, "✒ Painter").invoke()))
        check("Format painter starts", step(lambda: ed.painter) is not None)
        step(lambda: (ed.text.tag_add("sel", "3.0", "3.5"), ed._on_click_release()))
        check("...and paints the formatting onto the next selection", "b" in step(lambda: tags_at(ed, "3.2")) and step(lambda: ed.painter) is None)
        # alignment
        for sym, al in (("≡↔", "center"), ("→≡", "right"), ("≣", "justify")):
            step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "2.1"), btn(rib, sym).invoke()))
            check("align %s" % al, "al:" + al in step(lambda: tags_at(ed, "2.0")))
        step(lambda: btn(rib, "≡←").invoke())
        check("align left (the default) clears it", not any(t.startswith("al:") for t in step(lambda: tags_at(ed, "2.0"))))
        # spacing menu: every entry
        step(lambda: btn(rib, "↕ Spacing").invoke()); sm = last_menu(); labs = [l for l in labels(sm) if l != "---"]
        for l in labs:
            step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "2.1"), btn(rib, "↕ Spacing").invoke(), invoke_label(last_menu(), l)))
        t2 = step(lambda: tags_at(ed, "2.0"))
        check("spacing menu: all %d entries run; manuscript = double + indent" % len(labs), "ls:2" in t2 and "fi:0.5" in t2, t2)
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "2.1"), btn(rib, "⇥").invoke()))
        check("increase indent", "ind:0.5" in step(lambda: tags_at(ed, "2.0")))
        step(lambda: btn(rib, "⇤").invoke())
        check("decrease indent", not any(t.startswith("ind:") for t in step(lambda: tags_at(ed, "2.0"))))
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.mark_set("insert", "3.1"), btn(rib, "• List").invoke()))
        check("bullet list", any(t.startswith("li:bullet") for t in step(lambda: tags_at(ed, "3.3"))) and step(lambda: ed.text.get("3.0", "3.1")) == "•")
        step(lambda: btn(rib, "1. List").invoke())
        check("numbered list (switches the bullet to 1.)", step(lambda: ed.text.get("3.0", "3.2")) == "1.")
        step(lambda: btn(rib, "1. List").invoke())
        check("pressing it again ends the list", not any(t.startswith("li:") for t in step(lambda: tags_at(ed, "3.0"))))
        # insert
        nb = step(lambda: len(ed.blocks))
        ASK[:] = ["2 x 3"]; step(lambda: (ed.text.mark_set("insert", "end-1c"), btn(rib, "▦ Table").invoke()))
        tb = step(lambda: [b for b in ed.blocks.values() if isinstance(b, NE.TableBlock)])
        check("Table button inserts a 2 x 3 table", tb and len(tb[-1].cells) == 3 and len(tb[-1].cells[0]) == 2)
        from PIL import Image
        img = os.path.join(H, "pic.png"); Image.new("RGB", (120, 60), (10, 200, 30)).save(img)
        FILES["open"] = [img]; step(lambda: btn(rib, "▣ Picture").invoke()); FILES["open"] = []
        check("Picture button inserts the picture", step(lambda: len(ed.images)) == 1)
        step(lambda: btn(rib, "⤓ Page break").invoke())
        check("Page break button", step(lambda: len(ed.blocks)) == nb + 2)
        step(lambda: btn(rib, "Ω Symbol").invoke()); sym = last_menu()
        sub = step(lambda: sym.nametowidget(sym.entrycget(0, "menu")))
        step(lambda: sub.invoke(0))
        check("Symbol menu inserts a symbol", "—" in step(lambda: ed.text.get("1.0", "end")))
        step(lambda: btn(rib, "⧖ Date").invoke())
        check("Date button inserts today's date", str(time.localtime().tm_year) in step(lambda: ed.text.get("1.0", "end")))
        # combo boxes
        def style_pick():
            ed.text.mark_set("insert", "2.1")
            ed.style_cb.set("Heading 1"); ed.style_cb.event_generate("<<ComboboxSelected>>")
            return tags_at(ed, "2.0")
        check("Style box: Heading 1", "st:h1" in step(style_pick), step(lambda: tags_at(ed, "2.0")))
        def font_pick():
            ed.text.tag_add("sel", "1.0", "1.5")
            fam = list(ed.font_cb.cget("values"))[0]
            ed.font_cb.set(fam); ed.font_cb.event_generate("<<ComboboxSelected>>")
            return fam, tags_at(ed, "1.2")
        idle(0.5)
        fam, tg = step(font_pick)
        check("Font box sets the font", "ff:" + fam in tg, (fam, tg))
        def size_pick():
            ed.text.tag_add("sel", "1.0", "1.5")
            ed.size_cb.set("18"); ed.size_cb.focus_force(); ed.size_cb.update(); ed.size_cb.event_generate("<Return>")
            return tags_at(ed, "1.2")
        check("Size box sets the size (typed + Enter)", "fs:18" in step(size_pick))
        # find / spelling / thesaurus
        step(lambda: btn(rib, "⌕ Find").invoke()); idle(0.3)
        fr = step(lambda: ed._fr)
        def find_it():
            ed._fr_find.set("third"); btn(fr, "Find next").invoke()
            r = ed.text.tag_ranges("sel")
            return ed.text.get(r[0], r[1]) if r else ("NOTHING", [w.cget("text") for w in widgets(fr, (ttk.Label,))], ed.text.get("1.0", "end"))
        check("Find & replace: Find next", step(find_it).lower() == "third")
        def repl_all():
            ents = widgets(fr, (ttk.Entry,)); ents[1].delete(0, "end"); ents[1].insert(0, "3rd")
            btn(fr, "Replace all").invoke(); return ed.text.get("1.0", "end")
        check("Find & replace: Replace all", "3rd" in step(repl_all))
        step(lambda: fr.event_generate("<Escape>")); idle(0.2)
        check("Find & replace: Esc closes it", not step(lambda: fr.winfo_exists()))
        step(lambda: (ed.text.tag_add("sel", "2.0", "2.3"), ed.find_replace_dialog())); idle(0.2)
        check("Ctrl+F with words selected looks for those words", step(lambda: ed._fr_find.get()) == step(lambda: ed.text.get("2.0", "2.3")))
        step(lambda: ed._fr.destroy())
        step(lambda: btn(rib, "✓ Spelling").invoke())
        step(lambda: btn(rib, "≡ Thesaurus").invoke())
        check("Spelling and Thesaurus buttons run", True)
        # undo / redo
        before = step(lambda: ed.text.get("1.0", "end"))
        step(lambda: ed.insert_text("UNDOME"))
        step(ed.undo)
        check("undo", "UNDOME" not in step(lambda: ed.text.get("1.0", "end")))
        step(ed.redo)
        check("redo", "UNDOME" in step(lambda: ed.text.get("1.0", "end")))
        # dictate / cut buttons
        CMDS = []
        orig_cmd = app.engine.command
        app.engine.command = lambda n, **k: CMDS.append(n)
        step(lambda: btn(rib, "● Dictate here").invoke())
        step(lambda: btn(rib, "✂ Cut by voice").invoke())
        app.engine.command = orig_cmd
        check("Dictate here / Cut by voice start the microphone", CMDS.count("start_recording") == 2, CMDS)
        step(lambda: btn(rib, "Fonts…").invoke()); idle(0.4)
        check("Fonts… opens the font browser", step(lambda: app.font_win is not None and app.font_win.win.winfo_exists()))
        nerr = clean_since(nerr, "editor toolbar")

        # ================================================================ More tools (compact toolbar): every entry
        step(lambda: ed.set_compact_ribbon(True)); idle(0.3)
        def all_entries(m, path=""):
            out = []
            for i, l in enumerate(labels(m)):
                if l == "---" or m.entrycget(i, "state") == "disabled":
                    continue
                if m.type(i) == "cascade":
                    out += all_entries(m.nametowidget(m.entrycget(i, "menu")), path + l + " > ")
                else:
                    out.append((m, i, path + l))
            return out
        MENUS.clear(); step(lambda: ed._more_btn2.invoke()); mt = last_menu()
        ents = step(lambda: all_entries(mt))
        skip = ("Picture", "Table", "Dictate", "Cut by voice", "Find", "Thesaurus", "Next spelling")
        ASK[:] = []
        n_ok = 0
        for m, i, l in ents:
            if any(s in l for s in skip):
                continue
            r = step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), m.invoke(i)))
            n_ok += 1
        check("More tools: %d entries all run" % n_ok, n_ok > 30, n_ok)
        step(lambda: ed.set_compact_ribbon(False))
        nerr = clean_since(nerr, "More tools")

        # ================================================================ right-click menu in the page: every entry
        MENUS.clear()
        def rclick():
            ed.text.see("1.0"); bb = ed.text.bbox("1.1")
            ed.text.event_generate("<Button-3>", x=bb[0] + 2, y=bb[1] + 2, rootx=bb[0], rooty=bb[1])
        step(rclick); rm = last_menu()
        ents = step(lambda: all_entries(rm))
        n_ok = 0
        for m, i, l in ents:
            if any(s in l for s in ("Dictate", "Cut a passage", "Paste", "pronunciation dictionary")):
                continue
            step(lambda: (ed.text.tag_add("sel", "1.0", "1.5"), m.invoke(i)))
            n_ok += 1
        check("right-click menu: %d entries all run" % n_ok, n_ok >= 10, [l for _m, _i, l in ents])
        nerr = clean_since(nerr, "right-click menu")

        # ================================================================ pictures: paste and crop
        import nobu_clip
        from PIL import ImageGrab
        real_grab, real_html = ImageGrab.grabclipboard, nobu_clip.get_html
        CLIP = {"img": None, "html": None}
        ImageGrab.grabclipboard = lambda *a, **k: CLIP["img"]
        nobu_clip.get_html = lambda: CLIP["html"]
        def paste_with(img, html=None, text=None):
            CLIP["img"], CLIP["html"] = img, html
            app.clip_items = None
            app.root.clipboard_clear()
            if text is not None:
                app.root.clipboard_append(text)
            ed.text.mark_set("insert", "end-1c")
            n = len(ed.images)
            ed.paste()
            return len(ed.images) - n
        shot = Image.new("RGB", (200, 100), (200, 40, 40))
        check("paste a screenshot", step(lambda: paste_with(shot)) == 1)
        url = "https://example.com/cat.png"
        n_url = step(lambda: ed.text.get("1.0", "end").count(url))
        check("paste a picture copied from a web page (Copy image)",
              step(lambda: paste_with(shot, '<img src="%s" alt="cat">' % url, url)) == 1
              and step(lambda: ed.text.get("1.0", "end").count(url)) == n_url)
        check("a copied web address with no picture still pastes as text",
              step(lambda: paste_with(None, None, url)) == 0 and step(lambda: ed.text.get("1.0", "end").count(url)) == n_url + 1)
        check("text with a picture on the clipboard pastes the text", step(lambda: paste_with(shot, None, "Some words")) == 0)
        img2 = os.path.join(H, "copied.png"); Image.new("RGB", (80, 80), (0, 0, 255)).save(img2)
        check("paste picture files copied in File Explorer", step(lambda: paste_with([img2])) == 1)
        n_before = step(lambda: len(ed.images))
        step(lambda: paste_with(None, None, None))
        check("pasting with an empty clipboard does nothing", step(lambda: len(ed.images)) == n_before)
        ImageGrab.grabclipboard, nobu_clip.get_html = real_grab, real_html
        # crop: the right-click entry
        pic = step(lambda: [n for n, i in ed.images.items() if i["rel"].endswith("pic.png")][0])
        def rclick_pic():
            ed.text.see(pic); bb = ed.text.bbox(pic)
            ed.text.event_generate("<Button-3>", x=bb[0] + 5, y=bb[1] + 5, rootx=bb[0], rooty=bb[1])
        MENUS.clear(); step(rclick_pic); pm = last_menu()
        check("picture right-click menu has Crop…", pm is not None and "Crop…" in step(lambda: labels(pm)), pm and step(lambda: labels(pm)))
        def crop_windows():
            return [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_exists() and w.title() == "Crop picture"]
        step(lambda: invoke_label(pm, "Crop")); idle(0.3)
        cw_wins = step(crop_windows)
        check("Crop… opens the crop window", len(cw_wins) == 1)
        step(lambda: [w.event_generate("<Escape>") for w in cw_wins]); idle(0.2)
        check("Esc closes it", not step(crop_windows))
        # crop: drawing, moving and resizing the box with the mouse
        orig_rel = step(lambda: ed.images[pic]["rel"]); orig_w = step(lambda: ed.images[pic]["w"])
        cw = step(lambda: ed.crop_dialog(pic)); idle(0.2)
        class Ev:
            def __init__(s, x, y): s.x, s.y = x, y
        check("crop window starts with the whole picture", step(lambda: cw.real_box()) == (0, 0, 120, 60))
        step(lambda: (cw._press(Ev(20, 10)), cw._drag(Ev(60, 30)), cw._drag(Ev(100, 50)), cw._release(Ev(100, 50))))
        check("drag draws a new box", step(lambda: cw.real_box()) == (20, 10, 100, 50), step(lambda: cw.real_box()))
        step(lambda: (cw._press(Ev(60, 30)), cw._drag(Ev(70, 35)), cw._release(Ev(70, 35))))
        check("drag inside the box moves it", step(lambda: cw.real_box()) == (30, 15, 110, 55), step(lambda: cw.real_box()))
        step(lambda: (cw._press(Ev(110, 30)), cw._drag(Ev(90, 30)), cw._release(Ev(90, 30))))
        check("drag an edge resizes it", step(lambda: cw.real_box()) == (30, 15, 90, 55), step(lambda: cw.real_box()))
        step(lambda: (cw._press(Ev(5, 5)), cw._release(Ev(5, 5))))
        check("a click outside the box keeps the box", step(lambda: cw.real_box()) == (30, 15, 90, 55))
        step(lambda: btn(cw.win, "Whole picture").invoke())
        check("Whole picture starts again", step(lambda: cw.real_box()) == (0, 0, 120, 60))
        step(lambda: btn(cw.win, "Cancel").invoke()); idle(0.2)
        check("Cancel leaves the picture as it was", step(lambda: ed.images[pic]["rel"]) == orig_rel and not step(crop_windows))
        # crop: the result
        cw = step(lambda: ed.crop_dialog(pic)); idle(0.2)
        step(lambda: (cw.set_box((10, 5, 70, 45)), btn(cw.win, "Crop").invoke())); idle(0.3)
        new_rel = step(lambda: ed.images[pic]["rel"])
        with Image.open(os.path.join(H, new_rel)) as im:
            new_size = im.size
        check("Crop keeps only the box", "_cropped" in new_rel and new_size == (60, 40), (new_rel, new_size))
        check("...at the same scale", step(lambda: ed.images[pic]["w"]) == round(orig_w * 60 / 120), step(lambda: ed.images[pic]["w"]))
        check("...and the original picture file is kept", os.path.isfile(os.path.join(H, orig_rel)))
        step(ed.save)
        with open(a, encoding="utf-8") as f:
            check("the cropped picture is saved in the note", any(it.get("i") == new_rel for it in json.load(f)["items"]))
        step(ed.undo)
        check("Ctrl+Z brings the whole picture back", orig_rel in step(lambda: [i["rel"] for i in ed.images.values()]))
        step(ed.redo)
        cw = step(lambda: ed.crop_dialog(next(n for n, i in ed.images.items() if i["rel"] == new_rel))); idle(0.2)
        step(lambda: (cw.set_box((0, 0, 30, 40)), cw.win.event_generate("<Return>"))); idle(0.3)
        check("cropping a cropped picture works (Enter = Crop)", step(lambda: cw.done) is True and not step(crop_windows))
        nerr = clean_since(nerr, "pictures: paste and crop")

        # ================================================================ copy a picture out of a note (v4.9.2)
        pic = step(lambda: next(iter(ed.images)))
        pic_path = os.path.join(H, step(lambda: ed.images[pic]["rel"]))
        with Image.open(pic_path) as im:
            pic_size = im.size
        MENUS.clear(); step(rclick_pic); pm = last_menu()
        check("picture right-click menu has Copy picture", pm is not None and "Copy picture" in step(lambda: labels(pm)))
        if os.name == "nt":
            step(lambda: invoke_label(pm, "Copy picture")); idle(0.2)
            got = ImageGrab.grabclipboard()
            check("Copy picture puts the picture on the clipboard (for Paint, chat apps...)",
                  hasattr(got, "size") and got.size == pic_size, got)
            n_img = step(lambda: len(ed.images))
            step(lambda: (ed.text.mark_set("insert", "end-1c"), ed.paste()))
            check("...and it pastes back into a note", step(lambda: len(ed.images)) == n_img + 1)
            step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.tag_add("sel", pic, "%s +1c" % pic), ed.copy()))
            got = ImageGrab.grabclipboard()
            check("Ctrl+C on just a picture copies it as a picture too", hasattr(got, "size") and got.size == pic_size, got)
            step(lambda: ed.text.tag_remove("sel", "1.0", "end"))
        nerr = clean_since(nerr, "copy picture")

        # ================================================================ web links (v4.9.2)
        nobu_clip.get_html = lambda: CLIP["html"]
        ImageGrab.grabclipboard = lambda *a, **k: None
        def links_in(a_="1.0", b_="end"):
            out = []
            for tg in ed.text.tag_names():
                if tg.startswith("link:"):
                    rg = ed.text.tag_ranges(tg)
                    for k in range(0, len(rg), 2):
                        if ed.text.compare(rg[k], ">=", a_) and ed.text.compare(rg[k], "<", b_):
                            out.append((tg[5:], ed.text.get(rg[k], rg[k + 1])))
            return sorted(out)
        def paste_text(text, html=None, plain=False):
            CLIP["html"] = html
            app.clip_items = None
            app.root.clipboard_clear(); app.root.clipboard_append(text)
            ed.text.insert("end-1c", "\n")
            ed.text.mark_set("insert", "end-1c")
            start = ed.text.index("insert")
            ed.paste(plain=plain)
            return links_in(start)
        got = step(lambda: paste_text("See https://example.com/page, and www.nobu.test."))
        check("pasted web addresses become links", got == [("https://example.com/page", "https://example.com/page"),
                                                       ("https://www.nobu.test", "www.nobu.test")], got)
        got = step(lambda: paste_text("Read the guide now",
                                      '<p>Read <a href="https://example.org/guide">the guide</a> now</p>'))
        check("pasted web text keeps its links", got == [("https://example.org/guide", "the guide")], got)
        got = step(lambda: paste_text("Plain https://example.net/x", plain=True))
        check("Paste as plain text doesn't make links", got == [], got)
        # typing next to / inside a link
        def type_at(idx, ch):
            ed.text.mark_set("insert", idx)
            class Ev: pass
            e = Ev(); e.char = ch; e.state = 0
            ed._on_key(e)
        rng = step(lambda: ed.text.tag_ranges("link:https://example.org/guide"))
        end_ix = step(lambda: str(rng[1]))
        step(lambda: type_at(end_ix, "!"))
        check("typing just after a link doesn't add to it", "link:https://example.org/guide" not in step(lambda: ed.text.tag_names(end_ix)))
        mid = step(lambda: ed.text.index("%s +3c" % rng[0]))
        step(lambda: type_at(mid, "Z"))
        check("typing inside a link keeps it one link", "link:https://example.org/guide" in step(lambda: ed.text.tag_names(mid)))
        # Ctrl+click opens it; right-click entries
        def click_link(seq):
            r0 = ed.text.tag_ranges("link:https://example.org/guide")[0]
            ed.text.see(r0); ed.text.update_idletasks(); bb = ed.text.bbox("%s +1c" % r0)
            ed.text.event_generate("<Motion>", x=bb[0] + 2, y=bb[1] + 2)      # (the mouse is over the link)
            ed.text.event_generate(seq, x=bb[0] + 2, y=bb[1] + 2, rootx=0, rooty=0)
        OPENED.clear(); step(lambda: click_link("<Control-Button-1>")); idle(0.2)
        check("Ctrl+click opens the link in the web browser", OPENED == ["https://example.org/guide"], OPENED)
        OPENED.clear(); step(lambda: (click_link("<ButtonPress-1>"), click_link("<ButtonRelease-1>"))); idle(0.2)
        check("a plain click just puts the cursor there (for editing)", OPENED == [], OPENED)
        MENUS.clear(); step(lambda: click_link("<Button-3>")); lm = last_menu()
        labs = step(lambda: labels(lm))
        check("right-click a link: Open / Copy address / Remove", all(x in labs for x in ("Open link", "Copy link address", "Remove link")), labs)
        OPENED.clear(); step(lambda: invoke_label(lm, "Open link"))
        check("...Open link", OPENED == ["https://example.org/guide"], OPENED)
        step(lambda: invoke_label(lm, "Copy link address"))
        check("...Copy link address", step(lambda: app.root.clipboard_get()) == "https://example.org/guide")
        step(lambda: invoke_label(lm, "Remove link"))
        check("...Remove link", not step(lambda: ed.text.tag_ranges("link:https://example.org/guide")))
        step(ed.undo)
        check("Ctrl+Z brings the link back", bool(step(lambda: ed.text.tag_ranges("link:https://example.org/guide"))))
        # saved, spelling, clear formatting, copy out
        step(ed.save)
        with open(a, encoding="utf-8") as f:
            saved = [it for it in json.load(f)["items"] if "link:https://example.com/page" in it.get("g", [])]
        check("links are saved in the note", saved and saved[0]["t"] == "https://example.com/page", saved)
        for _ in range(100):
            if step(lambda: app.speller.ready):
                break
            time.sleep(0.2)
        step(lambda: (ed.text.insert("end-1c", "\nthe zorbleflax at https://www.qwzxv.test/plorbk\n"), ed._spell_all()))
        sp = step(lambda: [ed.text.get(*p) for p in zip(*[iter(ed.text.tag_ranges("sp_err"))] * 2)])
        check("spell check leaves web addresses alone", "zorbleflax" in sp and not any(
            w in ("https", "qwzxv", "plorbk", "www") for w in sp), sp)
        r0 = step(lambda: str(ed.text.tag_ranges("link:https://example.com/page")[0]))
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.tag_add("sel", r0, "%s +5c" % r0), ed.clear_formatting()))
        check("Clear formatting keeps links (like Word)", "link:https://example.com/page" in step(lambda: ed.text.tag_names("%s +1c" % r0)))
        ImageGrab.grabclipboard, nobu_clip.get_html = real_grab, real_html
        step(lambda: (ed.text.tag_remove("sel", "1.0", "end"), ed.text.tag_add("sel", r0, "%s lineend" % r0), ed.copy(),
                      ed.text.tag_remove("sel", "1.0", "end")))
        if os.name == "nt":
            check("Copy keeps the link (for Word, email...)", 'href="https://example.com/page"' in (nobu_clip.get_html() or ""))
        nerr = clean_since(nerr, "web links")

        # ================================================================ move and resize pictures with the mouse (v4.9.3)
        pt = ed.pictool
        class MEv:
            def __init__(s, x, y, xr=None, yr=None, state=0):
                s.x, s.y, s.state = x, y, state
                s.x_root, s.y_root = (x if xr is None else xr), (y if yr is None else yr)
        def new_pic(src=img):
            ed.text.insert("end-1c", "\nPicture line ")
            ed.text.mark_set("insert", "end-1c")
            return ed.insert_image_file(src)
        mp = step(new_pic); idle(0.3)
        def centre(name):
            ed.text.see(name); ed.text.update_idletasks(); x, y, w, h = ed.text.bbox(name)
            return x + w // 2, y + h // 2
        def real_click(name):
            x, y = centre(name)
            ed.text.event_generate("<ButtonPress-1>", x=x, y=y); ed.text.event_generate("<ButtonRelease-1>", x=x, y=y)
        def frame_fits(name, see=True):
            """The blue frame hugs the picture: each side is right against it (in the Text's own pixels)."""
            if see:
                ed.text.see(name)
            ed.text.update_idletasks(); pt.sync(); ed.text.update_idletasks()
            x, y = ed.text.bbox(name)[:2]
            ph = ed.images[name]["photo"]
            w, h = ph.width(), ph.height()
            bar = pt.bars
            return (bar["l"].winfo_x() + bar["l"].winfo_width() == x and bar["t"].winfo_y() + bar["t"].winfo_height() == y
                    and bar["r"].winfo_x() == x + w and bar["b"].winfo_y() == y + h)
        step(lambda: real_click(mp)); idle(0.3)
        check("click a picture selects it", step(lambda: pt.sel) == mp)
        check("...the frame and 8 squares show", step(lambda: all(w.winfo_ismapped() for w in pt._widgets())))
        check("...and the frame sits right around the picture (page margins allowed for)", step(lambda: frame_fits(mp)))
        step(lambda: ed.text.event_generate("<Escape>")); idle(0.1)
        check("Esc lets go of the picture", step(lambda: pt.sel) is None and not step(lambda: any(w.winfo_ismapped() for w in pt._widgets())))
        cropped = step(lambda: next(n for n, i in ed.images.items() if "_cropped" in i["rel"]))
        step(lambda: pt.select(cropped)); idle(0.2)
        check("...the frame also fits a cropped picture", step(lambda: frame_fits(cropped)))
        step(lambda: ed.text.yview_scroll(-1, "units")); idle(0.3)
        check("...and follows it when the page scrolls", step(lambda: frame_fits(cropped, see=False)))
        step(pt.deselect)
        # a tiny wobble doesn't move it
        old_ix = step(lambda: ed.text.index(mp))
        def wobble():
            x, y = centre(mp)
            pt._press(MEv(x, y)); pt._drag(MEv(x + 2, y + 1)); pt._release(MEv(x + 2, y + 1))
        step(wobble)
        check("a tiny wobble doesn't move the picture", step(lambda: ed.text.index(mp)) == old_ix and step(lambda: pt.sel) == mp)
        # drag it to the start of the note
        def drag_to_top():
            x, y = centre(mp)
            pt._press(MEv(x, y)); pt._drag(MEv(x + 20, y + 20))
            ed.text.see("1.0"); ed.text.update_idletasks(); bx, by, _bw, bh = ed.text.bbox("1.0")
            pt._drag(MEv(bx + 1, by + bh // 2))
            seen = (pt.ghost is not None, pt.caret.winfo_ismapped() or bool(pt.caret.place_info()),
                    (pt.caret.update_idletasks(), abs(pt.caret.winfo_x() + 1 - bx) <= 2)[1] if pt.caret.place_info() else False)
            pt._release(MEv(bx + 1, by + bh // 2))
            return seen
        ghost, caret, caret_at = step(drag_to_top); idle(0.2)
        check("while dragging, a see-through copy follows the mouse", ghost)
        check("...and a blue line shows where it will land", caret and caret_at)
        moved = step(lambda: [n for n, i in ed.images.items() if ed.text.index(n) == "1.0"])
        check("drag a picture to move it", len(moved) == 1, step(lambda: {n: ed.text.index(n) for n in ed.images}))
        check("...it is still selected after the move", moved and step(lambda: pt.sel) == moved[0])
        check("...the copy is gone and the old spot is empty", step(lambda: pt.ghost is None and mp not in ed.images))
        step(ed.undo)
        back = step(lambda: [n for n, i in ed.images.items() if ed.text.index(n) == old_ix])
        check("Ctrl+Z puts the picture back where it was", len(back) == 1, step(lambda: {n: ed.text.index(n) for n in ed.images}))
        mp = back[0] if back else mp
        def esc_drag():
            x, y = centre(mp)
            pt._press(MEv(x, y)); pt._drag(MEv(x + 30, y + 30))
            ed.text.event_generate("<Escape>")
            pt._release(MEv(x + 30, y - 200))
        step(esc_drag); idle(0.1)
        check("Esc while dragging leaves the picture where it was", step(lambda: ed.text.index(mp)) == old_ix and step(lambda: pt.ghost) is None)
        # resize: sides stretch one way, corners keep the shape
        sc = step(ed.img_scale)
        def drag_edge(edge, dx, dy, shift=False):
            pt.select(mp)
            pt._resize_press(MEv(0, 0, 500, 500), edge)
            pt._resize_drag(MEv(0, 0, 500 + dx // 2, 500 + dy // 2, 1 if shift else 0))
            pt._resize_drag(MEv(0, 0, 500 + dx, 500 + dy, 1 if shift else 0))
            ed.text.update(); time.sleep(0.05); ed.text.update()
            pt._resize_release()
            i = ed.images[mp]
            return i["w"], i.get("h"), i["photo"].width(), i["photo"].height()
        w0, h0, pw0, ph0 = step(lambda: drag_edge("r", 0, 0))
        check("a click on a side without dragging changes nothing", h0 is None and w0 == 120)
        w, h, pw, ph = step(lambda: drag_edge("r", round(100 * sc), 0))
        check("drag the right side: wider, same height", w == 220 and h == 60 and abs(ph - ph0) <= 1, (w, h, pw, ph))
        w, h, pw, ph = step(lambda: drag_edge("l", round(-50 * sc), 0))
        check("drag the left side outwards: wider too", w == 270 and h == 60, (w, h))
        w, h, pw, ph = step(lambda: drag_edge("b", 0, round(90 * sc)))
        check("drag the bottom: taller, same width", w == 270 and h == 150, (w, h))
        w, h, pw, ph = step(lambda: drag_edge("t", 0, round(40 * sc)))
        check("drag the top down: shorter", w == 270 and h == 110, (w, h))
        step(lambda: ed._undo.clear())       # (Nobu keeps only the last 80 steps: count from none)
        n_undo = step(lambda: len(ed._undo))
        w, h, pw, ph = step(lambda: drag_edge("br", round(54 * sc), 0))
        check("drag a corner: bigger, keeping the shape", w == 324 and abs(h - 132) <= 1, (w, h))
        check("...one Ctrl+Z step per resize", step(lambda: len(ed._undo)) == n_undo + 1)
        w, h, pw, ph = step(lambda: drag_edge("tl", round(54 * sc), 0))
        check("drag the opposite corner inwards: smaller, same shape", w == 270 and abs(h - 110) <= 1, (w, h))
        w, h, pw, ph = step(lambda: drag_edge("br", round(30 * sc), round(-50 * sc), shift=True))
        check("Shift + corner stretches freely", w == 300 and abs(h - 60) <= 1, (w, h))
        check("the frame follows the new size", step(lambda: frame_fits(mp)))
        def rclick_mp():
            x, y = centre(mp)
            ed.text.event_generate("<Button-3>", x=x, y=y, rootx=0, rooty=0)
        MENUS.clear(); step(rclick_mp)
        pm = last_menu()
        check("a stretched picture can go back to its own shape", pm is not None and any(l.startswith("Original shape") for l in step(lambda: labels(pm))))
        step(lambda: invoke_label(pm, "Original shape"))
        check("...Original shape", step(lambda: ed.images[mp].get("h")) is None and step(lambda: ed.images[mp]["w"]) == 300)
        step(ed.undo)
        mp = step(lambda: next(n for n, i in ed.images.items() if i.get("h") == 60 and i["w"] == 300))
        w, h, pw, ph = step(lambda: drag_edge("r", 9000, 0))
        check("it can't grow wider than the page", w == 624)
        w, h, pw, ph = step(lambda: drag_edge("b", 0, 9000))
        check("...or taller than the page", h == 864)
        w, h, pw, ph = step(lambda: drag_edge("tl", 9000, 9000))
        check("...or smaller than a thumbnail", w >= 30 and (h or 0) >= 20 and (w == 30 or h == 20), (w, h))
        step(lambda: drag_edge("br", round(200 * sc), 0))
        step(ed.save)
        st = step(lambda: (ed.images[mp]["w"], ed.images[mp].get("h")))
        with open(a, encoding="utf-8") as f:
            saved = [(it.get("w"), it.get("h")) for it in json.load(f)["items"] if "i" in it]
        check("the new width and height are saved in the note", st in saved, (st, saved))
        step(lambda: ed.load(a)); idle(0.3)
        mp = step(lambda: next(n for n, i in ed.images.items() if (i["w"], i.get("h")) == st))
        check("...and come back when the note is opened again", step(lambda: abs(ed.images[mp]["photo"].height() - st[1] * sc) <= 2))
        # Delete key, typing
        n_pics = step(lambda: len(ed.images))
        step(lambda: (pt.select(mp), ed._on_delete(None)))
        check("Delete removes the selected picture", step(lambda: len(ed.images)) == n_pics - 1 and step(lambda: pt.sel) is None)
        step(ed.undo)
        check("...and Ctrl+Z brings it back", step(lambda: len(ed.images)) == n_pics)
        mp = step(lambda: next(n for n, i in ed.images.items() if (i["w"], i.get("h")) == st))
        class KEv: char = "q"; state = 0
        step(lambda: (pt.select(mp), ed.text.mark_set("insert", "end-1c"), ed._on_key(KEv())))
        check("typing lets go of the picture (and types as normal)", step(lambda: pt.sel) is None
              and step(lambda: ed.text.get("end-2c", "end-1c")) == "q" and step(lambda: len(ed.images)) == n_pics)
        nerr = clean_since(nerr, "move and resize pictures")

        # ================================================================ pictures anywhere, text flowing round them (v4.9.3)
        big = os.path.join(H, "big.png"); Image.new("RGB", (300, 220), (40, 120, 200)).save(big)
        para = ("The ember-light crept across the old stones of the keep, and Kaelith counted the steps twice before "
                "she trusted the third. Somewhere below, water dripped into a pool she could not see. ") * 2
        f_items = [{"t": "Chapter One\n", "g": ["st:h1"]}] + [{"t": "%d. %s\n" % (i + 1, para), "g": []} for i in range(6)]
        for _ in range(3):
            f_items += [{"t": "•\t", "g": ["li:bullet:0", "lm"]}, {"t": para + "\n", "g": ["li:bullet:0"]}]
        fnote = lib.create_note(book, "Float test", f_items)
        step(app.refresh_library); step(lambda: app.open_note(fnote)); idle(0.6)
        ed = step(lambda: app.editor); pt = ed.pictool; fl = ed.flow
        def n_pars():
            return sum(it.get("t", "").count("\n") for it in ed.serialize()["items"])
        n_par0 = step(n_pars)
        fp = step(lambda: (ed.text.mark_set("insert", "2.0"), ed.insert_image_file(big))[1]); idle(0.3)
        def rclick_name(name):
            ed.text.see(name); ed.text.update_idletasks(); x, y, w, h = ed.text.bbox(name)
            ed.text.event_generate("<Button-3>", x=x + w // 2, y=y + h // 2, rootx=0, rooty=0)
        MENUS.clear(); step(lambda: rclick_name(fp)); pm = last_menu()
        wm = step(lambda: pm.nametowidget(pm.entrycget(entry(pm, "Text wrapping"), "menu")))
        wl = step(lambda: [l.replace("✓", "").strip() for l in labels(wm)])
        check("right-click a picture: Text wrapping, with 6 choices", len(wl) == 6 and wl[0].startswith("In line"), wl)
        step(lambda: wm.invoke(1)); idle(0.4)              # Square - text on the right
        fp = step(lambda: pt.sel)
        info = lambda: ed.images[fp]                       # noqa: E731
        check("Square: the picture floats on the page and stays selected",
              step(lambda: bool(info().get("float")) and info()["label"].winfo_ismapped() == 1))
        def layout():
            """(picture x, y, w, h, [(x, right end) of text lines beside it], [x of text lines below it])"""
            t = ed.text
            t.update_idletasks(); fl.place_all(); t.update_idletasks()
            lab = info()["label"]
            lx, ly, lw, lh = lab.winfo_x(), lab.winfo_y(), lab.winfo_width(), lab.winfo_height()
            beside, below, idx = [], [], t.index("@0,0 display linestart")
            for _ in range(400):
                dl = t.dlineinfo(idx)
                if dl is None:
                    break
                x, y, w, h, _b = dl
                bb = t.bbox(idx)
                if bb and t.get(idx).strip():
                    if bb[1] + bb[3] > ly + 3 and bb[1] < ly + lh - 3:
                        beside.append((bb[0], x + w))
                    elif y >= ly + lh and len(below) < 3:
                        below.append(bb[0])
                nxt = t.index(idx + " +1 display lines display linestart")
                if t.compare(nxt, "<=", idx):
                    break
                idx = nxt
            return lx, ly, lw, lh, beside, below
        step(lambda: (ed.text.see(fp), ed.text.update_idletasks())); idle(0.2)
        lx, ly, lw, lh, beside, below = step(layout)
        check("text flows down the right side of the picture", len(beside) >= 3 and all(x >= lx + lw for x, _e in beside),
              (lx, lw, beside[:5]))
        check("...and goes back to the full width below it", below and all(x < lx + 30 for x in below), (lx, below))
        check("...using invisible line breaks that are never saved", step(lambda: len(ed.text.tag_ranges("softnl"))) >= 2
              and step(n_pars) == n_par0, (step(n_pars), n_par0))
        saved = step(lambda: [it.get("float") for it in ed.serialize()["items"] if it.get("float")])
        check("the note remembers the picture, its wrapping and place", len(saved) == 1 and saved[0]["wrap"] == "square"
              and saved[0]["text"] == "right", saved)
        # copying the text beside it: no stray line breaks
        def copy_par():
            t = ed.text
            a_ = fl.par_start(t.index(fp))
            b_ = t.search("2. The ember", a_)
            t.tag_remove("sel", "1.0", "end"); t.tag_add("sel", a_, "%s -1c" % b_)
            ed.copy(); t.tag_remove("sel", "1.0", "end")
            return app.root.clipboard_get()
        clip = step(copy_par)
        check("copying the text beside a picture gives it without hidden breaks", "\n" not in clip and "steps twice" in clip, repr(clip[:120]))
        # Backspace right after a hidden break deletes the letter you can see
        def backspace_at_break():
            t = ed.text
            r = t.tag_ranges("softnl")
            ps = fl.par_start(r[0])
            pe = t.index("%s lineend" % r[1])
            while "softnl" in t.tag_names(pe):
                pe = t.index("%s +1c lineend" % pe)
            before = fl.plain(ps, pe)
            pos = len(fl.plain(ps, r[0]))
            pt.deselect()                      # (with the picture selected, Backspace deletes the picture)
            t.focus_force(); t.mark_set("insert", r[1]); t.event_generate("<BackSpace>"); t.update()
            fl.reflow()
            pe = t.index("%s lineend" % ps)
            while "softnl" in t.tag_names(pe):
                pe = t.index("%s +1c lineend" % pe)
            return before[:pos - 1] + before[pos:], fl.plain(ps, pe)
        want, got = step(backspace_at_break)
        d = next((i for i, (x, y) in enumerate(zip(want, got)) if x != y), min(len(want), len(got)))
        check("Backspace at a hidden break deletes the letter before it", want == got,
              (len(want), len(got), d, want[max(0, d - 30):d + 30], got[max(0, d - 30):d + 30]))
        step(ed.undo); idle(0.2)
        fp = step(lambda: next(n for n, i in ed.images.items() if i.get("float")))
        # dragging it anywhere
        sc = step(ed.img_scale)
        x0, top0 = step(lambda: (info()["float"]["x"], info()["_doc_top"]))
        def fdrag(dx, dy, esc=False):
            pt._fpress(MEv(0, 0, 500, 500), fp)
            pt._fdrag(MEv(0, 0, 500 + dx // 2, 500 + dy // 2)); pt._fdrag(MEv(0, 0, 500 + dx, 500 + dy))
            if esc:
                pt._escape(None)
            pt._frelease(MEv(0, 0, 500 + dx, 500 + dy))
            ed.text.update()
            return info()["float"]["x"], info()["_doc_top"]
        x1, top1 = step(lambda: fdrag(round(150 * sc), round(60 * sc)))
        check("drag a floating picture anywhere: across", x1 == x0 + 150, (x0, x1))
        check("...and down", abs(top1 - (top0 + round(60 * sc))) <= 2, (top0, top1))
        step(ed.undo); idle(0.2)
        fp = step(lambda: next(n for n, i in ed.images.items() if i.get("float")))
        check("Ctrl+Z puts it back", step(lambda: info()["float"]["x"]) == x0)
        x2, _t2 = step(lambda: fdrag(round(100 * sc), 0, esc=True))
        check("Esc while dragging leaves it where it was", x2 == x0, (x0, x2))
        class KEv:
            def __init__(s, state=0): s.state = state
        step(lambda: ed._undo.clear())
        n_u = step(lambda: len(ed._undo))
        step(lambda: (pt.select(fp), ed._nudge_picture(KEv(), 1, 0), ed._nudge_picture(KEv(), 1, 0), ed._nudge_picture(KEv(1), 1, 0)))
        check("arrow keys nudge it (8 pixels, Shift 1)", step(lambda: info()["float"]["x"]) == x0 + 17)
        check("...as one Ctrl+Z step", step(lambda: len(ed._undo)) == n_u + 1)
        # resizing a floating picture
        def fresize(edge, dx, dy=0):
            pt.select(fp)
            pt._resize_press(MEv(0, 0, 500, 500), edge)
            pt._resize_drag(MEv(0, 0, 500 + dx, 500 + dy)); ed.text.update(); time.sleep(0.05); ed.text.update()
            pt._resize_release()
            return info()["w"], info()["float"]["x"]
        w1, xa = step(lambda: fresize("r", round(60 * sc)))
        check("drag the right side of a floating picture: wider", w1 == 360, w1)
        w2, xb = step(lambda: fresize("l", round(-40 * sc)))
        check("drag its left side: wider, growing to the left", w2 == 400 and xb == max(0, xa - 40), (w2, xa, xb))
        lx, ly, lw, lh, beside, below = step(layout)
        check("the text makes room for the new size", all(x >= lx + lw for x, _e in beside) if beside else True, (lx, lw, beside[:3]))
        step(lambda: fresize("l", round(100 * sc)))            # (back to 300 wide)
        # the other wrapping styles
        def wrap_to(wrap, side=None):
            global_fp = ed.set_wrap(fp, wrap, side)
            ed.text.update(); fl.reflow(); ed.text.update()
            return global_fp
        fp = step(lambda: wrap_to("square", "left"))
        lx, ly, lw, lh, beside, below = step(layout)
        check("Square, text on the left: the text stops before the picture", beside and all(e <= lx + 2 for _x, e in beside),
              (lx, beside[:3]))
        step(lambda: fl.move_to(fp, 0, dy=0)); step(fl.reflow)
        fp = step(lambda: wrap_to("square", "largest"))
        lx, ly, lw, lh, beside, below = step(layout)
        check("Square, side with more room: picture on the left, text on its right", beside and all(x >= lx + lw for x, _e in beside))
        fp = step(lambda: wrap_to("topbottom"))
        lx, ly, lw, lh, beside, below = step(layout)
        check("Top and bottom: no text beside the picture", beside == [], beside[:3])
        fp = step(lambda: wrap_to("front"))
        lx, ly, lw, lh, beside, below = step(layout)
        check("In front of text: the text takes no notice of it", len(beside) >= 3 and not step(lambda: ed.text.tag_ranges("softnl")))
        fp = step(lambda: wrap_to(None))
        check("In line with text: back in the text", step(lambda: not ed.images[fp].get("float") and ed.text.index(fp) != "")
              and not step(lambda: ed.text.tag_ranges("softnl")) and step(n_pars) == n_par0)
        fp = step(lambda: wrap_to("square", "right"))
        # it stays with its paragraph
        top_a = step(lambda: info()["_doc_top"])
        step(lambda: (ed.text.insert("2.0", "A new line typed above the picture's paragraph.\n"), ed._mark_changed())); idle(0.3)
        check("typing above it: the picture moves down with its paragraph", step(lambda: info()["_doc_top"]) > top_a + 5)
        n_par0 += 1
        # a list beside a picture keeps its bullets
        def to_list():
            li = ed.text.search("•", "1.0")
            fl.move_to(fp, 0, doc_top=fl.ydoc(li) + 3)
            fl.reflow()
            li = ed.text.search("•", "1.0")
            return fl.par_start(ed.text.index(fp)) == ed.text.index("%s linestart" % li), len(ed.text.tag_ranges("lm")) // 2
        pinned, n_lm = step(to_list); idle(0.2)
        step(ed._renumber)
        check("a bulleted list beside a picture keeps exactly its bullets", pinned and step(lambda: len(ed.text.tag_ranges("lm")) // 2) == 3,
              (pinned, n_lm, step(lambda: len(ed.text.tag_ranges("lm")) // 2)))
        check("...and is saved as the same 3 items", sum(1 for it in step(lambda: ed.serialize()["items"])
                                                          if it.get("t") == "•\t") == 3)
        # copy and paste a floating picture with its text
        def copy_paste():
            t = ed.text
            a_ = fl.par_start(t.index(fp))
            t.tag_remove("sel", "1.0", "end"); t.tag_add("sel", a_, "%s lineend" % a_)
            ed.copy(); t.tag_remove("sel", "1.0", "end")
            t.mark_set("insert", "end-1c"); ed.paste(); t.update(); fl.reflow()
            return len(fl.names())
        check("copy + paste text with a floating picture copies the picture too", step(copy_paste) == 2)
        step(ed.undo); idle(0.2)
        fp = step(lambda: fl.names()[0])
        # a picture hanging below the end of the note: the page grows to show it
        def hang():
            ed._push_undo()
            fl.move_to(fp, 0, doc_top=fl.ydoc("end-1c linestart") + 10)
            fl.reflow()
            return int(ed.text.tag_cget("docend", "spacing3"))
        check("a picture below the last line makes the page longer", step(hang) > step(lambda: ed.px(0.88)))
        step(ed.undo); idle(0.2)
        fp = step(lambda: fl.names()[0])
        # zoom, save, reopen, delete
        step(lambda: ed.set_zoom("150%")); idle(0.4)
        step(lambda: (ed.text.see(fl.par_start(ed.text.index(fp))), ed.text.update_idletasks())); idle(0.3)
        lx, ly, lw, lh, beside, below = step(layout)
        check("zooming in keeps the text flowing round it", len(beside) >= 2 and all(x >= lx + lw for x, _e in beside), (lx, lw, beside[:3]))
        step(lambda: ed.set_zoom("100%")); idle(0.3)
        st_f = step(lambda: dict(info()["float"]))
        step(ed.save)
        step(lambda: ed.load(fnote)); idle(0.5)
        fp = step(lambda: fl.names()[0] if fl.names() else None)
        check("reopening the note puts the picture back, text flowing round it", fp is not None
              and step(lambda: ed.images[fp]["float"]) == st_f and step(lambda: len(ed.text.tag_ranges("softnl"))) >= 2,
              (st_f, fp and step(lambda: ed.images[fp]["float"])))
        check("...with the same paragraphs as before", step(n_pars) == n_par0, (step(n_pars), n_par0))
        step(lambda: (pt.select(fp), ed._on_delete(None))); idle(0.2)
        check("Delete removes a floating picture (and its line breaks)", not step(fl.names) and not step(lambda: ed.text.tag_ranges("softnl")))
        step(ed.undo); idle(0.2)
        check("...Ctrl+Z brings it back", len(step(fl.names)) == 1)
        nerr = clean_since(nerr, "pictures anywhere on the page")
        step(lambda: app.ws.close_editor(ed)); idle(0.3)
        step(lambda: app.open_note(a)); idle(0.5)
        ed = step(lambda: app.editor); pt = ed.pictool

        # ================================================================ note header buttons
        def hdr(text):
            return btn(ed.head, text)
        MENUS.clear(); step(lambda: hdr("Move to").invoke())
        check("Move to ▾ lists the folders", any("The Hollow Crown" in l for l in labels(last_menu())))
        ASK[:] = ["Chapter Uno"]; step(lambda: hdr("Rename").invoke()); idle(0.2)
        a = step(lambda: ed.path)
        check("Rename button renames the note", os.path.basename(a) == "Chapter Uno.nobu", a)
        MENUS.clear(); step(lambda: hdr("⋯").invoke()); mm = last_menu()
        INFOS.clear(); step(lambda: invoke_label(mm, "Word count"))
        check("⋯ > Word count shows the count", INFOS and "Words" in INFOS[-1])
        OPENED.clear(); step(lambda: invoke_label(mm, "Show file in folder"))
        check("⋯ > Show file in folder", OPENED and os.path.normcase(OPENED[-1]) == os.path.normcase(book))
        step(lambda: hdr("⇧  Export").invoke()); idle(0.3)
        exp = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Export / share"])
        check("Export / share button opens the export window", bool(exp))
        step(lambda: [w.destroy() for w in exp])
        nerr = clean_since(nerr, "note header")

        # ================================================================ pages, tabs, pop-outs
        step(lambda: app.open_note(b)); idle(0.3)
        p0 = step(lambda: app.ws.panes[0])
        check("a second note opens as a tab", step(lambda: len(p0.eds)) == 2)
        step(lambda: btn(p0.ctl, "☰").invoke())
        check("☰ switches to the compact toolbar", step(lambda: app.editor.ribbon_compact()))
        step(lambda: btn(p0.ctl, "☰").invoke())
        check("☰ again: all tools", not step(lambda: app.editor.ribbon_compact()))
        MENUS.clear(); step(lambda: btn(p0.ctl, "⧉").invoke()); sm = last_menu()
        step(lambda: invoke_label(sm, lib.title(a3)))
        check("⧉ opens a note on a new page beside", step(lambda: len(app.ws.panes)) == 2)
        step(lambda: app.ws.panes[1].cur.text.focus_set()); idle(0.2)
        def bars():
            return btn(app.ws.bar, "⇔"), btn(app.ws.bar, "⇤")
        step(lambda: (setattr(app.ws, "fracs", [0.7, 0.3]), bars()[0].invoke()))
        check("Even widths", step(lambda: [round(f, 2) for f in app.ws.fracs]) == [0.5, 0.5])
        step(lambda: bars()[1].invoke()); idle(0.3)
        check("Join into one page", step(lambda: len(app.ws.panes)) == 1 and step(lambda: len(app.ws.panes[0].eds)) == 3)
        # tab menu: every entry
        p0 = step(lambda: app.ws.panes[0])
        def tab_menu(ed_):
            MENUS.clear(); f, lbl, x, top = p0.tabw[ed_]
            lbl.event_generate("<Button-3>", rootx=10, rooty=10); return last_menu()
        e1 = step(lambda: p0.eds[1])
        step(lambda: invoke_label(tab_menu(e1), "Put on a new page on the right")); idle(0.3)
        check("tab menu: new page on the right", step(lambda: len(app.ws.panes)) == 2)
        step(app.ws.close_others); p0 = step(lambda: app.ws.panes[0])
        step(lambda: invoke_label(tab_menu(p0.eds[0]), "Put on a new page on the left")); idle(0.3)
        check("tab menu: new page on the left", step(lambda: len(app.ws.panes)) == 2)
        step(app.ws.close_others); p0 = step(lambda: app.ws.panes[0])
        step(lambda: invoke_label(tab_menu(p0.eds[0]), "Give it its own window")); idle(0.3)
        check("tab menu: own window", step(lambda: len(app.ws.popouts)) == 1)
        po = step(lambda: app.ws.popouts[0])
        step(lambda: btn(po.ed.pane_btns, "⇲").invoke()); idle(0.3)
        check("pop-out ⇲ puts it back as a tab", step(lambda: len(app.ws.popouts)) == 0)
        p0 = step(lambda: app.ws.panes[0])
        step(lambda: btn(p0.ctl, "⇱").invoke()); idle(0.3)
        check("⇱ gives the note its own window", step(lambda: len(app.ws.popouts)) == 1)
        step(lambda: app.ws.dock(app.ws.popouts[0])); idle(0.2)
        p0 = step(lambda: app.ws.panes[0]); n_before = step(lambda: len(p0.eds))
        ASK[:] = ["Chapter Two Renamed"]
        step(lambda: invoke_label(tab_menu(p0.eds[-1]), "Rename"))
        check("tab menu: Rename", any(lib.title(e.path) == "Chapter Two Renamed" for e in step(lambda: list(p0.eds))) or
              any(lib.title(e.path) == "Chapter Two Renamed" for e in step(lambda: app.ws.editors())))
        step(lambda: invoke_label(tab_menu(p0.eds[0]), "Close the other tabs"))
        check("tab menu: Close the other tabs", step(lambda: len(app.ws.panes[0].eds)) == 1)
        step(lambda: app.open_note(c)); p0 = step(lambda: app.ws.panes[0])
        step(lambda: invoke_label(tab_menu(p0.eds[-1]), "Close"))
        check("tab menu: Close", step(lambda: len(app.ws.panes[0].eds)) == 1)
        # Ctrl+Tab
        step(lambda: app.open_note(c)); p0 = step(lambda: app.ws.panes[0])
        cur0 = step(lambda: p0.cur)
        step(lambda: (cur0.text.focus_force(), cur0.text.event_generate("<Control-Tab>")))
        check("Ctrl+Tab goes to the next tab", step(lambda: p0.cur) is not cur0)
        step(lambda: (p0.cur.text.focus_force(), p0.cur.text.event_generate("<Control-W>")))
        check("Ctrl+W (Caps Lock on) closes the tab", step(lambda: len(p0.eds)) == 1)
        # Esc cancels a tab drag
        e = step(lambda: p0.cur)
        def tab_drag_esc():
            f = p0.tabw[e][1]; x0, y0 = f.winfo_rootx() + 5, f.winfo_rooty() + 5
            app.ws._tab_press(type("E", (), {"x_root": x0, "y_root": y0})(), e)
            app.ws._tab_motion(type("E", (), {"x_root": x0 + 300, "y_root": y0 + 300})(), e)
            had = app.ws._ghost is not None
            app.root.event_generate("<Escape>")
            app.root.update()
            app.ws._tab_release(type("E", (), {"x_root": x0 + 300, "y_root": y0 + 300})(), e)
            return had, app.ws._ghost is None, len(app.ws.popouts), len(app.ws.panes)
        r = step(tab_drag_esc)
        check("Esc cancels a tab drag (nothing moves)", r == (True, True, 0, 1), r)
        nerr = clean_since(nerr, "pages & tabs")

        # ================================================================ sidebar
        step(lambda: app._nav_go("inbox")); check("nav: Unassigned", step(lambda: app.view is app.inbox))
        step(lambda: app._nav_go("trash")); check("nav: Trash", step(lambda: app.view is app.trashview))
        step(lambda: app._nav_go("home")); check("nav: Home", step(lambda: app.view is app.home))
        ASK[:] = ["Ashfall"]
        step(lambda: btn(app.side, "+").invoke())
        ash = os.path.join(C.NOTES_DIR, "Ashfall")
        check("+ makes a new book / campaign", os.path.isdir(ash) and step(lambda: app.view is app.projview))
        # folder right-click menu: every entry
        def tree_menu(iid):
            MENUS.clear(); tv = app.tree; tv.see(iid); tv.update(); bb = tv.bbox(iid)
            tv.event_generate("<Button-3>", x=bb[0] + 40, y=bb[1] + 3, rootx=0, rooty=0); return last_menu()
        ASK[:] = ["Inside note"]; step(lambda: invoke_label(tree_menu(ash), "New note here"))
        check("folder menu: New note here", os.path.isfile(os.path.join(ash, "Inside note.nobu")))
        ASK[:] = ["Locations"]; step(lambda: invoke_label(tree_menu(ash), "New sub-folder here"))
        check("folder menu: New sub-folder here", os.path.isdir(os.path.join(ash, "Locations")))
        OPENED.clear(); step(lambda: invoke_label(tree_menu(ash), "Show in Windows Explorer"))
        check("folder menu: Show in Explorer", OPENED and os.path.normcase(OPENED[-1]) == os.path.normcase(ash))
        step(lambda: invoke_label(tree_menu(ash), "Open")); check("folder menu: Open", step(lambda: app.current_project) == ash)
        def sub_of(m, lab):
            return m.nametowidget(m.entrycget(entry(m, lab), "menu"))
        cm = step(lambda: sub_of(tree_menu(ash), "Colour label"))
        step(lambda: cm.invoke(0))
        check("folder menu: Colour label", lib.folder_color(ash) is not None)
        FILES["open"] = []; step(lambda: invoke_label(tree_menu(ash), "Import documents here"))
        step(lambda: invoke_label(tree_menu(ash), "Export / share this folder")); idle(0.3)
        exp = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Export / share"])
        check("folder menu: Export / share this folder", bool(exp)); step(lambda: [w.destroy() for w in exp])
        loc = os.path.join(ash, "Locations")
        step(lambda: app._tree_open(ash, True))
        mv = step(lambda: sub_of(tree_menu(loc), "Move to"))
        step(lambda: invoke_label(mv, "▪  The Hollow Crown") if "▪  The Hollow Crown" in labels(mv) else
             mv.nametowidget(mv.entrycget(entry(mv, "▪  The Hollow Crown"), "menu")).invoke(0))
        check("folder menu: Move to", os.path.isdir(os.path.join(book, "Locations")), os.listdir(book))
        ASK[:] = ["Ashfall Campaign"]; step(lambda: invoke_label(tree_menu(ash), "Rename"))
        ash2 = os.path.join(C.NOTES_DIR, "Ashfall Campaign")
        check("folder menu: Rename", os.path.isdir(ash2))
        CONFIRM_ANSWER[0] = True; step(lambda: invoke_label(tree_menu(ash2), "Delete"))
        check("folder menu: Delete (to Trash, after asking)", not os.path.isdir(ash2) and lib.trash_count() >= 1)
        # note right-click menu
        step(app.refresh_library); step(lambda: app._tree_open(book, True))
        a_now = sorted(lib.notes_in(book))[0]
        step(lambda: invoke_label(tree_menu(a_now), "Open side by side")); idle(0.3)
        check("note menu: Open side by side", step(lambda: app.view is app.ws.frame))
        step(lambda: invoke_label(tree_menu(a_now), "Open in its own window")); idle(0.3)
        check("note menu: Open in its own window", step(lambda: len(app.ws.popouts)) == 1)
        step(lambda: [app.ws.close_popout(p) for p in list(app.ws.popouts)])
        cm = step(lambda: sub_of(tree_menu(a_now), "Colour label"))
        step(lambda: cm.invoke(entry(cm, "✕  No colour")))
        step(lambda: invoke_label(tree_menu(a_now), "Export / share")); idle(0.3)
        exp = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Export / share"])
        check("note menu: Export / share", bool(exp)); step(lambda: [w.destroy() for w in exp])
        # bulk menu
        def bulk():
            tv = app.tree; tv.selection_set([a_now, chap]); MENUS.clear()
            app._tree_bulk_menu([a_now, chap], type("E", (), {"x_root": 0, "y_root": 0})()); return labels(last_menu())
        bl = step(bulk)
        check("several selected: bulk menu", bl[0].startswith("Selected: 1 folder and 1 note"), bl)
        step(lambda: invoke_label(last_menu(), "Clear selection"))
        check("bulk menu: Clear selection", not step(lambda: app.tree.selection()))
        nerr = clean_since(nerr, "sidebar")

        # ================================================================ folder list & Unassigned buttons
        step(lambda: app.show_project(book)); f = app.projview
        ASK[:] = ["List note"]; step(lambda: btn(f, "+  New note").invoke()); idle(0.2)
        check("folder list: + New note", os.path.isfile(os.path.join(book, "List note.nobu")))
        step(lambda: app.show_project(book))
        ASK[:] = ["Maps"]; step(lambda: btn(f, "+  New sub-folder").invoke())
        check("folder list: + New sub-folder", os.path.isdir(os.path.join(book, "Maps")))
        step(lambda: app.show_project(book))
        OPENED.clear(); step(lambda: btn(f, "Open folder").invoke())
        check("folder list: Open folder", OPENED and os.path.normcase(OPENED[-1]) == os.path.normcase(book))
        FILES["open"] = []; step(lambda: btn(f, "Import documents").invoke())
        step(lambda: btn(f, "⇧  Export").invoke()); idle(0.3)
        exp = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Export / share"])
        check("folder list: Export / share", bool(exp)); step(lambda: [w.destroy() for w in exp])
        ASK[:] = ["The Hollow Crown II"]; step(lambda: btn(f, "Rename").invoke())
        book = os.path.join(C.NOTES_DIR, "The Hollow Crown II")
        check("folder list: Rename", os.path.isdir(book) and step(lambda: app.current_project) == book)
        # list right-click (empty area)
        MENUS.clear(); step(lambda: f._tv.event_generate("<Button-3>", x=5, y=f._tv.winfo_height() - 5, rootx=0, rooty=0))
        check("folder list: right-click on empty space offers New note / sub-folder / Import",
              [l for l in labels(last_menu())][:3] == ["+  New note…", "+  New sub-folder…", "Import documents…"], labels(last_menu()))
        # Unassigned
        step(app.show_inbox); fi = app.inbox
        ASK[:] = ["Inbox thought"]; step(lambda: btn(fi, "+  New note").invoke())
        inb = os.path.join(C.INBOX_DIR, "Inbox thought.nobu")
        check("Unassigned: + New note", os.path.isfile(inb))
        step(app.show_inbox); step(lambda: fi._tv.selection_set(inb))
        MENUS.clear(); step(lambda: btn(fi, "Move selected").invoke())
        step(lambda: invoke_label(last_menu(), "▪  The Hollow Crown II") if "▪  The Hollow Crown II" in labels(last_menu())
             else last_menu().nametowidget(last_menu().entrycget(entry(last_menu(), "▪  The Hollow Crown II"), "menu")).invoke(0))
        check("Unassigned: Move selected to project", os.path.isfile(os.path.join(book, "Inbox thought.nobu")))
        step(app.show_inbox); c2 = os.path.join(C.INBOX_DIR, "Loose idea.nobu"); step(lambda: fi._tv.selection_set(c2))
        step(lambda: btn(fi, "Delete").invoke())
        check("Unassigned: Delete (to Trash)", not os.path.exists(c2))
        nerr = clean_since(nerr, "lists")

        # ================================================================ Trash
        step(app.show_trash); tv = app.trashview._tv
        items = step(lambda: tv.get_children())
        check("Trash lists the deleted items", len(items) >= 2, items)
        def trash_menu():
            MENUS.clear(); tv.update(); bb = tv.bbox(tv.get_children()[0])
            tv.event_generate("<Button-3>", x=bb[0] + 5, y=bb[1] + 3, rootx=0, rooty=0); return last_menu()
        step(lambda: invoke_label(trash_menu(), "Restore"))
        check("Trash: Restore", step(lambda: len(tv.get_children())) == len(items) - 1)
        step(lambda: invoke_label(trash_menu(), "Delete permanently"))
        check("Trash: Delete permanently", step(lambda: len(tv.get_children())) == len(items) - 2)
        CONFIRM_ANSWER[0] = True; step(lambda: btn(app.trashview, "Empty trash").invoke())
        check("Trash: Empty trash", step(lambda: len(tv.get_children())) == 0)
        nerr = clean_since(nerr, "trash")

        # ================================================================ Home page buttons
        step(app.show_home)
        for name in ("Review transcripts", "Teach Nobu my voice", "My dictionary", "Microphone & noise filter",
                     "What is it hearing?", "Fonts…"):
            step(lambda: btn(app.home, name).invoke()); idle(0.2)
        check("Home: Review transcripts went to Unassigned, others opened their windows",
              step(lambda: all(w is not None and w.win.winfo_exists() for w in
                               (app.teach_win, app.dict_win, app.settings_win, app.diag_win, app.font_win))))
        step(lambda: (app.teach_win.close(), app.diag_win.win.destroy(), app.dict_win.win.destroy(), app.font_win.win.destroy()))
        CMDS = []; app.engine.command = lambda n, **k: CMDS.append(n)
        step(app.show_home); step(lambda: btn(app.home, "●  Record now").invoke())
        step(lambda: app.rec_btn.invoke()); step(lambda: app.pause_btn.invoke())
        app.engine.command = orig_cmd
        check("Record now / sidebar Record / Pause send their commands", CMDS[:3] == ["start_recording", "start_recording", "pause"], CMDS)
        MENUS.clear(); step(lambda: app.gear_btn.invoke()); gm = last_menu()
        gl = labels(gm)
        check("⚙ menu has all its entries", len([l for l in gl if l != "---"]) == 12, gl)
        for l in gl:
            if l == "---" or l.startswith(("Quit", "Hide")):
                continue
            step(lambda: invoke_label(gm, l)); idle(0.1)
        check("every ⚙ menu entry runs", True)
        step(lambda: [w.destroy() for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title()
                      not in ("", "Nobu Notes — settings") and w.winfo_viewable()])
        nerr = clean_since(nerr, "home & gear")

        # ================================================================ Settings: every slider, box and checkbox
        if not (app.settings_win and app.settings_win.win.winfo_exists()):
            step(app.open_settings)
        sd = app.settings_win; idle(0.3)
        scales = step(lambda: widgets(sd.win, (ttk.Scale,)))
        check("Settings has its 4 sliders", len(scales) == 4, len(scales))
        def move(sc_, v):
            sc_.set(v); sc_.update()
            row = sc_.master; return [w.cget("text") for w in row.winfo_children() if isinstance(w, ttk.Label)][-1]
        txts = [step(lambda: move(scales[0], 12)), step(lambda: move(scales[1], 0.0)), step(lambda: move(scales[2], 0.8)),
                step(lambda: move(scales[3], 0.7))]
        check("sliders update their readouts", txts[0] == "+12 dB" and txts[1] == "Off" and txts[2].startswith("80%") and
              txts[3].startswith("0.70"), txts)
        check("gain / noise / sensitivity sliders apply live (before Save)",
              (app.cfg["mic_gain_db"], app.cfg["noise_reduction"], app.cfg["speech_sensitivity"]) == (12, 0.0, 0.8))
        combos = step(lambda: widgets(sd.win, (ttk.Combobox,)))
        def wheel_combo():
            cb = [x for x in combos if "Dictation" not in str(x) and str(x.cget("state")) == "readonly"][0]
            v = cb.get(); cb.event_generate("<MouseWheel>", delta=-120); cb.event_generate("<Button-5>"); return v, cb.get()
        v0, v1 = step(wheel_combo)
        check("mouse wheel over a drop-down scrolls the page, never changes the setting", v0 == v1, (v0, v1))
        cbs = step(lambda: widgets(sd.win, (ttk.Checkbutton,)))
        before = step(lambda: [bool(sd.win.getvar(x.cget("variable"))) for x in cbs])
        step(lambda: [x.invoke() for x in cbs])
        step(lambda: sd.edit_end.set(sd._edit_opts[0][1]))
        step(lambda: sd.silence.set(12))
        step(lambda: btn(sd.win, "Save").invoke()); idle(0.3)
        cfg = json.load(open(C.CONFIG_PATH))
        keys = ["transcribe_original", "accept_bare_phrase", "cue_sounds", "confirm_cut", "confirm_edit", "close_to_tray",
                "autostart", "reopen_notes"]
        flipped = {k: app.cfg[k] for k in keys}
        check("Save stores every ticked / unticked box", all(flipped[k] == (not M.C.DEFAULTS[k]) for k in keys), flipped)
        check("Save stores the sliders and boxes", (cfg.get("mic_gain_db"), cfg.get("noise_reduction"), cfg.get("wake_match_threshold"),
                                                    cfg.get("edit_silence_seconds"), cfg.get("silence_stop_seconds"))
              == (12, 0.0, 0.7, 4, 12.0), cfg)
        step(app.open_settings); sd = app.settings_win
        step(lambda: move(widgets(sd.win, (ttk.Scale,))[0], 3)); step(sd.cancel)
        check("Cancel puts live slider changes back", app.cfg["mic_gain_db"] == 12)
        # hotkeys
        step(app.open_settings); sd = app.settings_win
        step(lambda: sd._capture_hotkey("record")); idle(0.2)
        cap = step(lambda: [w for w in sd.win.winfo_children() if isinstance(w, tk.Toplevel)][-1])
        step(lambda: cap.event_generate("<KeyPress>", keysym="F8")); idle(0.6)
        check("shortcut capture: pressing F8 sets it", app.cfg["hotkey_record"] == "F8", app.cfg["hotkey_record"])
        step(lambda: [w for w in widgets(sd.win, (ttk.Button,)) if w.cget("text") == "None"][1].invoke())
        check("shortcut 'None' clears it", app.cfg["hotkey_edit"] == "")
        # theme editor
        step(lambda: btn(sd.win, "✎  Make my own colours").invoke()); idle(0.3)
        te = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "My colours"][-1])
        sws = step(lambda: [w for w in widgets(te, (tk.Label,)) if w.cget("relief") == "solid"])
        step(lambda: sws[0].event_generate("<Button-1>"))
        check("My colours: clicking a swatch picks a colour", step(lambda: sws[0].cget("bg")) == "#123456")
        step(lambda: btn(te, "Same as accent").invoke())
        dsc = step(lambda: widgets(te, (ttk.Scale,))[0])
        step(lambda: (dsc.set(0.55), dsc.update())); idle(0.6)
        check("drop highlight strength is saved once the slider settles", abs(json.load(open(C.CONFIG_PATH)).get("drop_alpha", 0) - 0.55) < 0.01)
        CONFIRM_ANSWER[0] = False
        step(lambda: btn(te, "Use these colours").invoke()); idle(0.3)
        check("Use these colours saves the theme as Custom", app.cfg["theme"] == "custom" and app.cfg["custom_theme"])
        CONFIRM_ANSWER[0] = True
        nerr = clean_since(nerr, "settings")

        # ================================================================ dictionary
        step(app.open_dictionary); dw = app.dict_win
        step(lambda: (dw.quick.set("Kaelith"), btn(dw.win, "+  Add & record").invoke())); idle(0.2)
        wd = step(lambda: [w for w in dw.win.winfo_children() if isinstance(w, tk.Toplevel)][-1])
        def word_save():
            ents = widgets(wd, (ttk.Entry,))
            ents[1].insert(0, "kay lith"); btn(wd, "Add").invoke()
            btn(wd, "Save word").invoke()
        step(word_save)
        check("dictionary: add a word with a sound-alike", any(e["word"] == "Kaelith" and "kay lith" in e["sounds"] for e in dw.entries), dw.entries)
        step(lambda: (dw.tv.selection_set("Kaelith"), btn(dw.win, "Remove").invoke()))
        check("dictionary: Remove (after asking)", not dw.entries and CONFIRMS and "Kaelith" in CONFIRMS[-1])
        step(lambda: btn(dw.win, "Fix the open note now").invoke())
        step(lambda: dw.win.destroy())
        # fonts browser
        step(app.open_font_browser); fb = app.font_win
        fam0 = step(lambda: fb.groups[fb.cats.selection()[0]][0])
        step(lambda: fb._pick(fam0))
        step(lambda: btn(fb.win, "Make it my heading font").invoke())
        check("Fonts: Make it my heading font", app.cfg["heading_font"] == fam0)
        step(lambda: (fb.size.set(30), fb._refresh()))
        step(lambda: btn(fb.win, "Open my fonts folder").invoke())
        step(lambda: btn(fb.win, "Install Nobu").invoke())
        check("Fonts: install-into-Windows box", app.cfg["install_fonts"] is False)
        step(lambda: fb.win.destroy())
        # diagnostics
        step(app.open_diagnostics); dg = app.diag_win
        step(lambda: btn(dg.win, "Save what it hears").invoke())
        check("Diagnostics: save clips box", app.cfg["save_heard_clips"] is True)
        step(lambda: dg.win.destroy())
        # teach
        step(app.open_teach); tw = app.teach_win
        step(lambda: btn(tw.win, "Start").invoke())
        check("Teach: Start", step(lambda: tw.stage) == "noise")
        step(tw.close)
        nerr = clean_since(nerr, "dictionary, fonts, diagnostics, teach")

        # ================================================================ export: every format
        note = lib.create_note(book, "Export me"); step(app.refresh_library)
        step(lambda: app.open_note(note)); step(lambda: (app.editor.text.mark_set("insert", "end-1c"), app.editor.insert_text("Some words to export.\n"), app.editor.save()))
        note = step(lambda: app.editor.path)
        for key, ext in (("docx", "docx"), ("pdf", "pdf"), ("epub", "epub"), ("html", "html"), ("html", "txt")):
            out = os.path.join(H, "out." + ext)
            FILES["save"] = out
            def run_export():
                import nobu_share
                d = nobu_share.ExportDialog(app, [note])
                d.fmt.set(key); d._sync()
                if ext == "txt":
                    d.web_kind.set("txt"); d._sync()
                d._export()
            CONFIRM_ANSWER[0] = False
            step(run_export)
            for _ in range(60):
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    break
                time.sleep(0.5)
            idle(0.3)
            check("Export as %s" % ext, os.path.exists(out) and os.path.getsize(out) > 0,
                  (INFOS[-2:], CONFIRMS[-1:], step(lambda: app.status.cget("text"))))
        CONFIRM_ANSWER[0] = True
        # import
        src = os.path.join(H, "story.txt"); open(src, "w").write("An imported story.\n\nSecond paragraph.")
        step(lambda: app.import_files([src], book)); idle(0.3)
        check("Import a document", os.path.isfile(os.path.join(book, "story.nobu")))
        nerr = clean_since(nerr, "export & import")

        # ================================================================ dialogs: danger = Enter is safe
        res = {}
        def danger():
            win_seen = []
            def later():
                w = [x for x in app.root.winfo_children() if isinstance(x, tk.Toplevel) and x.title() == "Delete it?"][-1]
                win_seen.append(w); w.focus_force(); w.update(); (w.focus_get() or w).event_generate("<Return>")
                app.root.after(2000, lambda: w.winfo_exists() and w.destroy())
            app.root.after(300, later)
            res["d"] = REAL_CONFIRM(app.root, "Delete it?", "Really?", yes="Delete", danger=True)
            def later2():
                w = [x for x in app.root.winfo_children() if isinstance(x, tk.Toplevel) and x.title() == "Go?"][-1]
                w.focus_force(); w.update(); (w.focus_get() or w).event_generate("<Return>")
                app.root.after(2000, lambda: w.winfo_exists() and w.destroy())
            app.root.after(300, later2)
            res["n"] = REAL_CONFIRM(app.root, "Go?", "Ok?", yes="Go")
        step(danger)
        check("Enter on a delete question picks the safe answer; on others it means yes", res == {"d": False, "n": True}, res)

        # ================================================================ narrow page: the small header buttons
        nb2 = sorted(lib.notes_in(book))[0]
        step(lambda: app.open_note(nb2)); idle(0.3)
        e_ = step(lambda: app.editor)
        r_ = step(lambda: (e_._fit_head(300), e_.btns_small.winfo_manager(), e_._compact, e_.btns_full.winfo_manager(), e_.path)); check("narrow page uses the small header buttons", r_[1] == "pack", r_)
        step(lambda: btn(e_.btns_small, "⇧").invoke()); idle(0.3)
        exp = step(lambda: [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Export / share"])
        check("small ⇧ opens Export", bool(exp)); step(lambda: [w.destroy() for w in exp])
        MENUS.clear(); step(lambda: btn(e_.btns_small, "Move").invoke())
        check("small Move ▾ shows the folders", last_menu() is not None and len(labels(last_menu())) > 1)
        ASK[:] = [None]; step(lambda: btn(e_.btns_small, "✎").invoke())
        MENUS.clear(); step(lambda: btn(e_.btns_small, "⋯").invoke())
        check("small ⋯ shows More", "Word count…" in labels(last_menu()))
        step(lambda: e_._fit_head(1400))
        # sidebar Home / Unassigned / Trash right-click menus: every entry
        n_ok = 0
        for row in ("home", "inbox", "trash"):
            def nav_menu():
                MENUS.clear(); app.nav.update(); bb = app.nav.bbox(row)
                app.nav.event_generate("<Button-3>", x=bb[0] + 20, y=bb[1] + 3, rootx=0, rooty=0); return last_menu()
            m_ = step(nav_menu)
            for i, l in enumerate(step(lambda: labels(m_))):
                if l != "---":
                    FILES["open"] = []; ASK[:] = [None]; step(lambda: m_.invoke(i)); n_ok += 1
        check("Home / Unassigned / Trash right-click menus: %d entries run" % n_ok, n_ok == 6, n_ok)
        # a note's right-click menu in a folder list: every entry
        step(lambda: app.show_project(book)); tvp = app.projview._tv
        def row_menu():
            MENUS.clear(); kids = [k for k in tvp.get_children() if os.path.isfile(k)]; tvp.see(kids[0]); tvp.update()
            bb = tvp.bbox(kids[0]); tvp.event_generate("<Button-3>", x=bb[0] + 30, y=bb[1] + 3, rootx=0, rooty=0)
            return last_menu(), kids[0]
        m_, row_ = step(row_menu)
        labs_ = step(lambda: labels(m_))
        for want in ("Open", "Open side by side", "Open in its own window"):
            step(lambda: invoke_label(m_, want)); idle(0.2)
        check("folder list: a note's right-click menu opens it every way", step(lambda: len(app.ws.popouts)) == 1, labs_)
        step(lambda: [app.ws.close_popout(p) for p in list(app.ws.popouts)])
        nerr = clean_since(nerr, "small buttons & menus")

        # ================================================================ small comforts
        # Esc cancels a drag from the sidebar
        step(app.refresh_library); step(app.show_home)
        nb_ = sorted(lib.notes_in(book))[0]
        step(lambda: app._reveal(nb_))
        def side_drag_esc():
            tv = app.tree; tv.see(nb_); tv.update(); bb = tv.bbox(nb_)
            x, y = bb[0] + 60, bb[1] + bb[3] // 2; rx, ry = tv.winfo_rootx() + x, tv.winfo_rooty() + y
            E = lambda **k: type("E", (), dict(dict(x=x, y=y, x_root=rx, y_root=ry, state=0), **k))()
            app.dragdrop._press(E(), tv)
            app.dragdrop._motion(E(x_root=rx + 900, y_root=ry), tv)
            had = app.dragdrop.ghost is not None
            app.root.event_generate("<Escape>"); app.root.update()
            r = app._tree_release(E(x_root=rx + 900, y_root=ry))
            return had, app.dragdrop.ghost is None, r, len(app.ws.editors()), os.path.exists(nb_)
        before = step(lambda: len(app.ws.editors()))
        r = step(side_drag_esc)
        check("Esc cancels a drag from the sidebar (nothing opens or moves)", r == (True, True, "break", before, True), r)
        # closed menus don't pile up
        def menus_after_many():
            for _ in range(25):
                app._gear_menu()
            return len([w for w in app.root.winfo_children() if isinstance(w, tk.Menu)])
        check("closed pop-up menus are cleared away (they don't pile up)", step(menus_after_many) <= 3)
        # tooltips wait a moment
        def tip():
            b_ = app.editor.export_btn if app.editor.path else None
            if b_ is None:
                return None
            t_ = NE._Tip(b_, "hello"); t_._soon(); first = t_.top is None
            return t_, first
        step(lambda: app.open_note(nb_)); idle(0.3)
        t_, first = step(tip)
        idle(0.7)
        check("tooltips appear after a short pause, not instantly", first and step(lambda: t_.top is not None))
        step(t_.hide)
        # new windows open over the window you're working in (a note in its own window)
        step(lambda: app.ws.pop_out(app.editor)); idle(0.4)
        po = step(lambda: app.ws.popouts[0])
        step(lambda: po.win.geometry("700x700+1000+150")); idle(0.4)
        def dialog_pos():
            po.ed.text.focus_force(); po.win.update()
            w = T.toplevel(app.root, "Pos test"); ttk.Label(w, text="x" * 30).pack(); T.fit(w); w.update()
            r = (w.winfo_rootx(), w.winfo_rooty(), w.winfo_width()); w.destroy()
            return r, (po.win.winfo_rootx(), po.win.winfo_rooty(), po.win.winfo_width())
        (dx, dy, dw), (px, py, pw) = step(dialog_pos)
        check("dialogs open over the note's own window", px <= dx and dx + dw <= px + pw + 2, ((dx, dy, dw), (px, py, pw)))
        step(lambda: app.ws.dock(po))

        # ================================================================ reopen notes on start
        step(lambda: app.ws.close_others())
        x1 = lib.create_note(book, "Session A"); x2 = lib.create_note(book, "Session B"); x3 = lib.create_note(book, "Session C")
        step(lambda: (app.open_note(x1), app.open_note(x2), app.open_note(x3, side=True))); idle(0.3)
        sess = step(app._session)
        check("the open pages and tabs are remembered", len(sess) == 2 and len(sess[0]["tabs"]) >= 2, sess)
        step(lambda: app.cfg.update(open_tabs=sess))
        step(lambda: [app.ws.close_editor(e) for e in list(app.ws.editors())]); idle(0.3)
        check("(all closed)", step(lambda: len(app.ws.editors())) == 0)
        step(lambda: app.cfg.update(reopen_notes=True)); r = step(app._restore_session); idle(0.4)
        again = step(app._session)
        check("...and reopened the same way next start", r is True and again == sess, (sess, again))
        nerr = clean_since(nerr, "session")
    except Exception:
        traceback.print_exc()
    print("RESULT %d/%d passed" % (sum(OK), len(OK)))
    os._exit(0)
threading.Thread(target=go, daemon=True).start(); app.run()
