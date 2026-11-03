"""Export / share, import, and the font browser windows."""
import logging
import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

import nabu_fonts as F
import nabu_library as lib
import nabu_rich as R
import nabu_theme as T
from nabu_config import INBOX_DIR

log = logging.getLogger("nabu.share")


def _reveal(path):
    try:
        if os.name == "nt":
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            from nabu_editor import open_path
            open_path(os.path.dirname(path))
    except Exception:
        log.exception("reveal failed")


# ====================================================================== export
class ExportDialog:
    def __init__(self, app, paths=None, folder=None):
        import nabu_export as E
        self.app, self.E = app, E
        self.root = app.root
        paths = [p for p in (paths or []) if p and os.path.isfile(p)]
        self.folder = folder
        if not folder and len(paths) == 1:
            d = os.path.dirname(paths[0])
            if not lib.is_inbox(d):
                self.folder = d
        self.sel_paths = paths
        app.ws.save_all()
        w = self.win = T.toplevel(self.root, "Export / share")
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        self.body = f
        ttk.Label(f, text="Export / share", style="H2.TLabel").pack(anchor="w")
        ttk.Label(f, text="Makes a copy you can send to other people. Formatting, fonts and pictures come along.",
                  style="Muted.TLabel", wraplength=560).pack(anchor="w", pady=(2, 12))

        # what
        ttk.Label(f, text="WHAT TO EXPORT", style="Section.TLabel").pack(anchor="w")
        self.scope = tk.StringVar()
        if paths:
            label = ("This note: “%s”" % lib.title(paths[0])) if len(paths) == 1 else \
                "The %d selected notes" % len(paths)
            ttk.Radiobutton(f, text=label, value="sel", variable=self.scope).pack(anchor="w", pady=1)
            self.scope.set("sel")
        self.folder_notes = lib.all_notes(self.folder) if self.folder and os.path.isdir(self.folder) else []
        if self.folder and os.path.isdir(self.folder):
            n = len(self.folder_notes)
            ttk.Radiobutton(f, text="Everything in “%s”  (%d note%s, including sub-folders)"
                            % (lib.crumbs(self.folder), n, "" if n == 1 else "s"),
                            value="folder", variable=self.scope).pack(anchor="w", pady=1)
            if not paths:
                self.scope.set("folder")

        # format
        ttk.Label(f, text="FORMAT", style="Section.TLabel").pack(anchor="w", pady=(14, 2))
        self.fmt = tk.StringVar(value=app.cfg.get("export_format") or "docx")
        for key, label, desc in E.FORMATS:
            row = ttk.Frame(f)
            row.pack(fill="x", pady=2)
            ttk.Radiobutton(row, text=label, value=key, variable=self.fmt, command=self._sync).pack(anchor="w")
            ttk.Label(row, text=desc, style="Muted.TLabel", wraplength=520).pack(anchor="w", padx=(24, 0))
        self.web_kind = tk.StringVar(value="html")
        self.web_row = ttk.Frame(f)
        ttk.Radiobutton(self.web_row, text="Web page (keeps formatting)", value="html",
                        variable=self.web_kind, command=self._sync).pack(side="left", padx=(24, 10))
        ttk.Radiobutton(self.web_row, text="Plain text (words only)", value="txt",
                        variable=self.web_kind, command=self._sync).pack(side="left")

        # options
        ttk.Label(f, text="OPTIONS", style="Section.TLabel").pack(anchor="w", pady=(14, 2))
        cfg = app.cfg
        self.o_pages = tk.BooleanVar(value=cfg.get("export_page_numbers", True) is not False)
        self.o_newpage = tk.BooleanVar(value=True)
        self.o_titles = tk.BooleanVar(value=True)
        self.o_embed = tk.BooleanVar(value=True)
        self.o_meta = tk.BooleanVar(value=False)
        self.cb_pages = ttk.Checkbutton(f, text="Page numbers at the bottom", variable=self.o_pages)
        self.cb_embed = ttk.Checkbutton(f, text="Put the fonts inside the file, so it looks the same on their computer",
                                        variable=self.o_embed)
        self.cb_newpage = ttk.Checkbutton(f, text="Start each note on a new page / chapter", variable=self.o_newpage)
        self.cb_titles = ttk.Checkbutton(f, text="Use each note's name as a chapter heading", variable=self.o_titles)
        self.cb_meta = ttk.Checkbutton(f, text="Include Nabu's grey dates and “Play recording” links",
                                       variable=self.o_meta)
        for cb in (self.cb_pages, self.cb_embed, self.cb_newpage, self.cb_titles, self.cb_meta):
            cb.pack(anchor="w", pady=1)
        self.warn = ttk.Label(f, text="", style="Muted.TLabel", wraplength=560, foreground=T.AMBER)
        self.warn.pack(anchor="w", pady=(8, 0))

        bar = ttk.Frame(w, padding=(18, 0, 18, 16))
        bar.pack(side="bottom", fill="x", before=f)
        self.go = ttk.Button(bar, text="Export…", style="Accent.TButton", command=self._export)
        self.go.pack(side="right")
        ttk.Button(bar, text="Cancel", command=w.destroy).pack(side="right", padx=8)
        self.prog = ttk.Label(bar, text="", style="Muted.TLabel")
        self.prog.pack(side="left")
        self.scope.trace_add("write", lambda *a: self._sync())
        self._sync()
        T.fit(w)
        w.grab_set()

    def _paths(self):
        return self.folder_notes if self.scope.get() == "folder" else self.sel_paths

    def _sync(self):
        fmt = self.fmt.get()
        multi = len(self._paths()) > 1
        if fmt == "html":
            if not self.web_row.winfo_ismapped():
                self.web_row.pack(anchor="w", before=self.cb_pages)
        else:
            self.web_row.pack_forget()
        for cb, on in ((self.cb_pages, fmt in ("docx", "pdf")), (self.cb_embed, fmt == "docx"),
                       (self.cb_newpage, multi and fmt != "epub"), (self.cb_titles, multi)):
            cb.state(["!disabled"] if on else ["disabled"])
        warn = ""
        uses_fonts = fmt in ("docx", "epub") or (fmt == "html" and self.web_kind.get() == "html")
        blocked = [x for x in (self.app.body_family, self.app.heading_family) if F.licence_blocks_embedding(x)]
        if blocked and uses_fonts:
            warn = ("“%s” is a personal-use font, so it can't be packed into the file. People who don't have it "
                    "will see a similar standard font for those headings. (PDF keeps it exactly.)" % blocked[0])
        self.warn.config(text=warn)

    def _export(self):
        paths = self._paths()
        if not paths:
            T.info(self.win, "Export", "There are no notes to export here yet.")
            return
        fmt = self.fmt.get()
        if fmt == "html":
            fmt = self.web_kind.get()
        ext = "." + fmt
        if len(paths) == 1 and self.scope.get() == "sel":
            name = lib.title(paths[0])
        elif self.scope.get() == "folder":
            name = lib.folder_name(self.folder)
        else:
            name = "Nabu Notes"
        last_dir = self.app.cfg.get("export_dir") or os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")
        out = filedialog.asksaveasfilename(parent=self.win, title="Save the exported file", initialdir=last_dir,
                                           initialfile=lib.safe_name(name) + ext, defaultextension=ext,
                                           filetypes=[(ext.upper()[1:] + " file", "*" + ext), ("All files", "*.*")])
        if not out:
            return
        self.app.cfg.update(export_dir=os.path.dirname(out), export_format=self.fmt.get(),
                            export_page_numbers=bool(self.o_pages.get()))
        opts = {"page_numbers": self.o_pages.get(), "page_per_note": self.o_newpage.get(),
                "chapter_titles": self.o_titles.get(), "embed_fonts": self.o_embed.get(),
                "keep_meta": self.o_meta.get(),
                "title": name if self.scope.get() == "folder" or len(paths) > 1 else lib.title(paths[0])}
        ctx = R.Ctx(self.app.body_family, self.app.heading_family, float(self.app.cfg["font_size"]))
        self.go.state(["disabled"])
        self.prog.config(text="Exporting…")
        res = {}

        def work():
            try:
                res["path"] = self.E.export(paths, fmt, out, ctx, opts)
            except Exception as e:
                log.exception("export failed")
                res["err"] = e
            self.root.after(0, done)

        def done():
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            if "err" in res:
                T.info(self.root, "Export failed", "Sorry, the export didn't work:\n\n%s\n\nDetails are in the log." % res["err"])
                return
            self.app.set_status("Exported to %s" % out)
            if T.confirm(self.root, "Exported", "Saved “%s”.\n\n%s" % (os.path.basename(out), os.path.dirname(out)),
                         yes="Show in folder", no="Close"):
                _reveal(out)
        threading.Thread(target=work, daemon=True).start()


# ====================================================================== import
def import_dialog(app, folder=None):
    import nabu_importers as I
    folder = folder or app.current_project or INBOX_DIR
    files = filedialog.askopenfilenames(parent=app.root, title="Choose documents to import into “%s”" % (
        "Unassigned" if lib.is_inbox(folder) else lib.crumbs(folder)), filetypes=I.FILETYPES)
    if files:
        import_files(app, list(files), folder, ask=True)


def import_files(app, files, folder, ask=True):
    import nabu_importers as I
    files = [f for f in files if f.lower().endswith(I.EXTS)]
    if not files:
        T.info(app.root, "Import", "Nabu can import Word (.docx), OpenDocument (.odt), PDF, web pages, Markdown, "
               "rich text (.rtf) and text files.")
        return
    keep = app.cfg.get("import_keep_fonts", True) is not False
    if ask and any(f.lower().endswith((".docx", ".odt", ".html", ".htm")) for f in files):
        w = T.toplevel(app.root, "Import")
        fr = ttk.Frame(w, padding=18)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="Import %d document%s into “%s”" % (
            len(files), "" if len(files) == 1 else "s", "Unassigned" if lib.is_inbox(folder) else lib.crumbs(folder)),
            style="H2.TLabel").pack(anchor="w")
        v = tk.StringVar(value="keep" if keep else "mine")
        ttk.Radiobutton(fr, text="Keep the document's own fonts and sizes (looks exactly like it did)", value="keep",
                        variable=v).pack(anchor="w", pady=(10, 2))
        ttk.Radiobutton(fr, text="Use my Nabu fonts (keep bold, italics, headings, colours, pictures)", value="mine",
                        variable=v).pack(anchor="w")
        res = {"go": False}
        bar = ttk.Frame(w, padding=(18, 0, 18, 16))
        bar.pack(side="bottom", fill="x", before=fr)
        ttk.Button(bar, text="Import", style="Accent.TButton",
                   command=lambda: (res.update(go=True), w.destroy())).pack(side="right")
        ttk.Button(bar, text="Cancel", command=w.destroy).pack(side="right", padx=8)
        T.fit(w)
        w.grab_set()
        w.wait_window()
        if not res["go"]:
            return
        keep = v.get() == "keep"
        app.cfg.update(import_keep_fonts=keep)
    ctx = R.Ctx(app.body_family, app.heading_family, float(app.cfg["font_size"]))
    made, failed = [], []
    app.set_status("Importing…")
    app.root.update_idletasks()
    for src in files:
        try:
            made.append(I.import_file(src, folder, keep_fonts=keep, ctx=ctx))
        except Exception as e:
            log.exception("import failed: %s", src)
            failed.append("%s (%s)" % (os.path.basename(src), e))
    app.refresh_library()
    if made:
        app.set_status("Imported %d document%s into %s." % (len(made), "" if len(made) == 1 else "s",
                                                             "Unassigned" if lib.is_inbox(folder) else lib.crumbs(folder)))
    if failed:
        T.info(app.root, "Import", "These could not be imported:\n\n" + "\n".join(failed[:10]))
    if len(made) == 1:
        app.open_note(made[0])
    elif made and lib.is_inbox(folder):
        app.show_inbox()
    elif made:
        app.show_project(folder)


# ====================================================================== font browser
class FontBrowser:
    SAMPLE = "The dragon's ember crown lay in the ruins of Kaelmor."

    def __init__(self, app):
        self.app, self.root = app, app.root
        w = self.win = T.toplevel(self.root, "Fonts", int(980 * T.ui_scale(self.root)), int(640 * T.ui_scale(self.root)))
        top = ttk.Frame(w, padding=(16, 14, 16, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Fonts", style="H2.TLabel").pack(side="left")
        ttk.Label(top, text="   Preview:", style="Muted.TLabel").pack(side="left")
        self.sample = tk.StringVar(value=self.SAMPLE)
        e = ttk.Entry(top, textvariable=self.sample, width=50)
        e.pack(side="left", padx=6, fill="x", expand=True)
        e.bind("<KeyRelease>", lambda ev: self._refresh_job())
        self.size = tk.IntVar(value=20)
        sp = ttk.Spinbox(top, from_=8, to=72, textvariable=self.size, width=4, command=self._refresh)
        sp.pack(side="left")
        sp.bind("<KeyRelease>", lambda ev: self._refresh_job())

        bottom = ttk.Frame(w, padding=(16, 6, 16, 14))
        bottom.pack(side="bottom", fill="x")
        self.chosen = ttk.Label(bottom, text="Click a font to choose it.", style="Muted.TLabel")
        self.chosen.pack(side="top", anchor="w", pady=(0, 6))
        b = ttk.Frame(bottom)
        b.pack(fill="x")
        ttk.Button(b, text="Use for the selected text", style="Accent.TButton", command=self._use_sel).pack(side="left")
        ttk.Button(b, text="Make it my note text font", command=lambda: self._set_cfg("font_family")).pack(side="left", padx=6)
        ttk.Button(b, text="Make it my heading font", command=lambda: self._set_cfg("heading_font")).pack(side="left")
        ttk.Button(b, text="Make it my interface font", command=lambda: self._set_cfg("ui_font")).pack(side="left", padx=6)
        ttk.Button(b, text="Close", command=w.destroy).pack(side="right")
        b2 = ttk.Frame(bottom)
        b2.pack(fill="x", pady=(8, 0))
        ttk.Button(b2, text="+  Add fonts\u2026", style="Accent.TButton", command=self._add_fonts).pack(side="left")
        ttk.Button(b2, text="Open my fonts folder", command=self._open_user_fonts).pack(side="left", padx=6)
        self.inst = tk.BooleanVar(value=app.cfg.get("install_fonts", True) is not False)
        ttk.Checkbutton(b2, text="Install Nabu's fonts into Windows too (so Word and other apps have them)",
                        variable=self.inst, command=self._toggle_install).pack(side="left", padx=12)

        mid = ttk.Frame(w, padding=(16, 0))
        mid.pack(fill="both", expand=True)
        self.cats = ttk.Treeview(mid, show="tree", selectmode="browse")
        self.cats.column("#0", width=int(210 * T.ui_scale(self.root)))
        self.cats.pack(side="left", fill="y")
        self.groups = F.by_category(self.root)
        for key, label in F.CATEGORIES:
            n = len(self.groups.get(key, []))
            if n:
                self.cats.insert("", "end", iid=key, text="  %s  (%d)" % (label, n))
        self.cats.bind("<<TreeviewSelect>>", lambda e: self._refresh())
        box = tk.Frame(mid, bg=T.EDITOR)
        box.pack(side="left", fill="both", expand=True, padx=(10, 0))
        sb = ttk.Scrollbar(box, orient="vertical")
        sb.pack(side="right", fill="y")
        self.list = tk.Text(box, bg=T.EDITOR, fg=T.FG, relief="flat", bd=0, highlightthickness=0, wrap="word",
                            cursor="hand2", padx=14, pady=10, yscrollcommand=sb.set)
        self.list.pack(fill="both", expand=True)
        sb.configure(command=self.list.yview)
        self.list.bind("<Key>", lambda e: "break")
        self.list.tag_configure("name", foreground=T.MUTED, font=T.UI_FONT)
        self.list.tag_configure("pick", background=T.SELECT)
        self.fonts = []
        self.family = None
        first = next((k for k, _ in F.CATEGORIES if self.groups.get(k)), None)
        if first:
            self.cats.selection_set(first)
        self._job = None
        self._refresh()
        T.fit(w)

    def _refresh_job(self):
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(300, self._refresh)

    def _refresh(self):
        self._job = None
        sel = self.cats.selection()
        cat = sel[0] if sel else None
        t = self.list
        t.delete("1.0", "end")
        self.fonts = []
        try:
            size = max(8, min(72, int(self.size.get())))
        except (tk.TclError, ValueError):
            size = 20
        for fam in self.groups.get(cat, [])[:400]:
            f = tkfont.Font(family=fam, size=size)
            self.fonts.append(f)
            tag, click = "fam:" + fam, "click:" + fam
            t.tag_configure(tag, font=f, spacing3=10)
            t.tag_bind(click, "<Button-1>", lambda e, fam=fam: self._pick(fam))
            t.insert("end", fam + "\n", ("name", click))
            t.insert("end", (self.sample.get() or fam) + "\n", (tag, click))
        if cat == "yours" and not self.groups.get("yours"):
            t.insert("end", "Put .ttf or .otf files in the “fonts” folder inside Nabu Notes, then restart Nabu.", "name")

    def _pick(self, fam):
        self.family = fam
        t = self.list
        t.tag_remove("pick", "1.0", "end")
        r = t.tag_ranges("click:" + fam)
        if r:
            t.tag_add("pick", r[0], r[-1])
        lic = " (personal-use licence: fine in your notes and PDFs, not packed into Word files/e-books)" \
            if F.licence_blocks_embedding(fam) else ""
        self.chosen.config(text="Chosen: %s%s" % (fam, lic))

    def _use_sel(self):
        if not self.family:
            self.chosen.config(text="Click a font in the list first.")
            return
        ed = self.app.editor
        if not ed.path:
            self.app.set_status("Open a note first, then select the words to change.")
            return
        ed.set_char("ff", self.family)
        ed._sync_ribbon()
        self.app.set_status("Font set to %s." % self.family)

    def _set_cfg(self, key):
        if not self.family:
            self.chosen.config(text="Click a font in the list first.")
            return
        self.app.cfg.update(**{key: self.family})
        self.app.apply_fonts()
        self.app.set_status("%s is now %s." % ({"font_family": "Note text font", "heading_font": "Heading font",
                                                "ui_font": "Interface font"}[key], self.family))

    def _add_fonts(self):
        files = filedialog.askopenfilenames(
            parent=self.win, title="Choose font files to add",
            filetypes=[("Fonts", "*.ttf *.otf *.zip"), ("All files", "*.*")])
        if not files:
            return
        added, already, problems = F.add_user_fonts(list(files),
                                                     install=self.app.cfg.get("install_fonts", True) is not False)
        self.groups = F.by_category(self.root)
        for k, label in F.CATEGORIES:
            n = len(self.groups.get(k, []))
            if n and not self.cats.exists(k):
                self.cats.insert("", 0 if k == "yours" else "end", iid=k, text="  %s  (%d)" % (label, n))
            elif self.cats.exists(k):
                self.cats.item(k, text="  %s  (%d)" % (label, n))
        if self.cats.exists("yours"):
            self.cats.selection_set("yours")
        self._refresh()
        for ed in self.app.ws.editors():
            try:
                ed._fill_fonts()
            except Exception:
                pass
        parts = []
        if added:
            parts.append("Added: %s.\n\nThey're ready to use now - pick them in the font list or here "
                         "(\u201cYour fonts\u201d)." % ", ".join(added))
        if already:
            parts.append("Already in your fonts (nothing to do): %s." % ", ".join(already))
        msg = "\n\n".join(parts) or "No new fonts were added."
        if problems:
            msg += "\n\nCouldn't add:\n" + "\n".join(problems[:8])
        T.info(self.win, "Fonts", msg)

    def _open_user_fonts(self):
        os.makedirs(F.USER_FONTS, exist_ok=True)
        from nabu_editor import open_path
        open_path(F.USER_FONTS)

    def _toggle_install(self):
        on = bool(self.inst.get())
        self.app.cfg.update(install_fonts=on)
        if on:
            self.app.install_fonts_background(force=True)
