"""Drag & drop inside Nabu: rearrange books, campaigns, sub-folders and notes in the sidebar.

Drag an item (from the sidebar, a folder list or Unassigned) and drop it:
  * onto a folder ............ moves it inside that folder (the folder is highlighted)
  * on the upper/lower edge
    of an item ............... puts it above / below that item (a blue line shows where);
                               folders dropped next to a book/campaign become books/campaigns
  * onto "Unassigned" ........ sends notes back to Unassigned
  * onto "Trash" ............. deletes (to Trash, restorable)
  * onto the page area ........ opens the note there: the left or right part of a page puts it on a
                               new page beside it, the middle (or the tabs) makes it a tab; dropped
                               well outside Nabu's window it opens in its own window. A blue shadow
                               shows where. (A folder dropped there is opened.)
The label that follows the mouse has a second line saying exactly where it will end up ("Goes into:
"Book > Chapters", above "Chapter 3"") or that it can't go there. Files dragged in from Windows
Explorer get the same kind of label (ExplorerHint).
The order you arrange things in is remembered.
"""
import logging
import os
import time
import tkinter as tk

import nabu_library as lib
import nabu_theme as T
from nabu_config import INBOX_DIR, NOTES_DIR

log = logging.getLogger("nabu.drag")


class DragDrop:
    THRESHOLD = 10          # pixels: a slightly shaky click is still a click, not a drag

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.items = []
        self.start = None
        self.dragging = False
        self.ghost = None
        self.line = None
        self.hot = None            # (widget, iid) currently highlighted
        self.target = None
        self.hover = (None, 0.0)
        self.last_xy = (None, None)
        self.ghost_lbl = None
        self.dest_lbl = None       # the ghost's second line: where it will end up
        self.ghost_text = ""
        self._shown = False
        self.cancelled = False     # Esc pressed during this drag: the release does nothing
        self._prev_esc = ""
        # (the sidebar tree calls _press / _motion / _release itself, from its own click handling)
        for w in (app.inbox._tv, app.projview._tv):
            w.bind("<ButtonPress-1>", lambda e, w=w: self._press(e, w), add="+")
            w.bind("<B1-Motion>", lambda e, w=w: self._motion(e, w), add="+")
            w.bind("<ButtonRelease-1>", lambda e, w=w: self._release(e, w), add="+")
        app.tree.tag_configure("dropinto", background=T.ACCENT_DARK, foreground="#ffffff")
        app.nav.tag_configure("dropinto", background=T.ACCENT_DARK, foreground="#ffffff")

    # ------------------------------------------------------------ gesture
    def _press(self, e, w):
        iid = w.identify_row(e.y)
        self.dragging = False
        self.cancelled = False
        self.start = None
        if not iid or iid.startswith(("empty:", "lazy:")) or not os.path.exists(iid) or getattr(e, "state", 0) & 0x5:
            return
        sel = list(w.selection())
        items = sel if iid in sel else [iid]
        self.items = [p for p in items if os.path.exists(p)]
        self.start = (e.x_root, e.y_root)

    def _motion(self, e, w):
        if not self.start:
            return
        if not self.dragging:
            if abs(e.x_root - self.start[0]) + abs(e.y_root - self.start[1]) < self.THRESHOLD:
                return
            self.dragging = True
            self._make_ghost()
        self.ghost.geometry("+%d+%d" % (e.x_root + 14, e.y_root + 10))
        self._autoscroll(e)
        self._show(self._find_target(e.x_root, e.y_root))
        return "break"

    def _release(self, e, w):
        if self.cancelled:
            return "break"
        if not self.dragging:
            self.start = None
            return
        self.last_xy = (e.x_root, e.y_root)
        target = self._find_target(e.x_root, e.y_root)
        self._cleanup()
        if target:
            self.root.after(10, lambda: self._drop(target))
        return "break"

    # ------------------------------------------------------------ visuals
    def _make_ghost(self):
        g = self.ghost = tk.Toplevel(self.root)
        g.overrideredirect(True)
        g.attributes("-topmost", True)
        try:
            g.attributes("-alpha", 0.9)
        except tk.TclError:
            pass
        names = [lib.folder_name(p) if os.path.isdir(p) else lib.title(p) for p in self.items]
        text = names[0] if len(names) == 1 else "%s  (+%d more)" % (names[0], len(names) - 1)
        icon = "▸ " if os.path.isdir(self.items[0]) else ""
        self.ghost_text = icon + text[:60]
        self.ghost_lbl = tk.Label(g, text=self.ghost_text, bg=T.ACCENT_DARK, fg="#ffffff", font=T.UI_FONT,
                                  padx=10, pady=4)
        self.ghost_lbl.pack(fill="x")
        # the second line says exactly where it will end up if let go now
        self.dest_lbl = tk.Label(g, text="", bg=T.PANEL, fg=T.FG, font=T.UI_BOLD, padx=10, pady=3, anchor="w",
                                 justify="left")
        self.dest_lbl.pack(fill="x")
        for w in (self.app.tree, self.app.nav, self.app.inbox._tv, self.app.projview._tv):
            w.configure(cursor="fleur")
        self._prev_esc = self.root.bind("<Escape>")
        self.root.bind("<Escape>", self._cancel)

    def _cancel(self, _e=None):
        """Esc while dragging: put everything back, drop nothing."""
        self._cleanup()
        self.cancelled = True
        self.app.set_status("Drag cancelled.")
        return "break"

    def _cleanup(self):
        if self.ghost:
            self.ghost.destroy()
            self.ghost = None
            self.root.bind("<Escape>", self._prev_esc or "")
            self.app.set_status("")
        self._unhot()
        try:
            self.app.ws.show_drop(None)
        except Exception:
            pass
        self.target = None
        self._shown = False
        for w in (self.app.tree, self.app.nav, self.app.inbox._tv, self.app.projview._tv):
            w.configure(cursor="")
        self.dragging = False
        self.start = None

    def _unhot(self):
        if self.hot:
            w, iid = self.hot
            try:
                tags = [t for t in w.item(iid, "tags") if t != "dropinto"]
                w.item(iid, tags=tags)
            except tk.TclError:
                pass
            self.hot = None
        if self.line:
            self.line.place_forget()

    def _show(self, target):
        if target == self.target and self.ghost is not None and self._shown:
            return                     # same spot as before: change nothing (no flicker)
        self._shown = True
        self._unhot()
        if not target or target[0] != "open":
            try:
                self.app.ws.show_drop(None)
            except Exception:
                pass
        self.target = target
        if self.ghost is not None:
            try:
                text = self.ghost_text
                if target and target[0] == "open":
                    if all(os.path.isdir(p) for p in self.items):
                        text = "\u2192  Open folder:  " + text
                    else:
                        text = self.app.ws.describe(target[1], text)
                elif target and target[0] in ("place", "folder"):
                    text = "\u21b3  Move:  " + text
                elif target and target[0] == "inbox":
                    text = "\u2709  Back to Unassigned:  " + text
                elif target and target[0] == "trash":
                    text = "\u267b  Delete:  " + text
                self.ghost_lbl.configure(text=text)
                dest, ok = self.dest_text(target)
                self.dest_lbl.configure(text=dest, fg=T.FG if ok else T.FAINT)
                self.app.set_status(dest if ok else "")
            except Exception:
                log.exception("drag label")
        if not target:
            return
        kind = target[0]
        if kind == "place":
            _, iid, where = target
            tv = self.app.tree
            if where == "into":
                self._hot(tv, iid)
            else:
                bb = tv.bbox(iid)
                if bb:
                    if not self.line:
                        self.line = tk.Frame(tv, height=3, bg=T.ACCENT)
                    y = bb[1] - 1 if where == "above" else bb[1] + bb[3] - 2
                    self.line.place(x=bb[0] + 4, y=y, width=max(40, tv.winfo_width() - bb[0] - 8), height=3)
                    self.line.lift()
        elif kind in ("inbox", "trash"):
            self._hot(self.app.nav, kind)
        elif kind == "open":
            self.app.ws.show_drop(target[1], above=self.ghost)
        elif kind == "folder" and target[2] is not None:
            self._hot(*target[2])

    def dest_text(self, target):
        """(words saying where the dragged items would end up, can they be dropped here)"""
        def name(p):
            return lib.folder_name(p) if os.path.isdir(p) else lib.title(p)

        def place(folder):
            return "Unassigned" if lib.is_inbox(folder) else "“%s”" % lib.crumbs(folder)
        if not target:
            return "✕  Not here — let go to cancel (or press Esc)", False
        kind = target[0]
        if kind == "inbox":
            return "→  Goes to:  Unassigned", True
        if kind == "trash":
            return "→  Goes to:  the Trash (you can restore it)", True
        if kind == "folder":
            return "→  Goes into:  %s" % place(target[1]), True
        if kind == "open":
            if all(os.path.isdir(p) for p in self.items):
                return "→  Opens the folder’s list (nothing is moved)", True
            return "%s  (nothing is moved)" % self.app.ws.describe(target[1], "").strip(" :"), True
        _, iid, where = target
        if where == "into":
            return "→  Goes into:  %s" % place(iid), True
        folder = os.path.dirname(iid)
        side = "above" if where == "above" else "below"
        if os.path.normcase(folder) == os.path.normcase(os.path.abspath(NOTES_DIR)):
            return "→  Becomes a book / campaign, %s “%s”" % (side, name(iid)), True
        return "→  Goes into:  %s,  %s “%s”" % (place(folder), side, name(iid)), True

    def _hot(self, w, iid):
        try:
            w.item(iid, tags=tuple(w.item(iid, "tags")) + ("dropinto",))
            self.hot = (w, iid)
        except tk.TclError:
            pass

    def _autoscroll(self, e):
        tv = self.app.tree
        if not (tv.winfo_rootx() <= e.x_root < tv.winfo_rootx() + tv.winfo_width()
                and tv.winfo_rooty() - 30 <= e.y_root < tv.winfo_rooty() + tv.winfo_height() + 30):
            return
        y = e.y_root - tv.winfo_rooty()
        edge = max(18, tv.winfo_height() // 12)
        if y < edge:
            tv.yview_scroll(-1, "units")
        elif y > tv.winfo_height() - edge:
            tv.yview_scroll(1, "units")

    # ------------------------------------------------------------ where would it land?
    def _valid_into(self, folder):
        for p in self.items:
            if os.path.isdir(p):
                a, b = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(folder))
                if b == a or b.startswith(a + os.sep):
                    return False
        return True

    def _find_target(self, xr, yr):
        t = self._target_at(xr, yr)
        if not (t and t[0] == "place" and t[2] == "into"):
            self.hover = (None, 0.0)           # left the folder: the "open it after a moment" clock restarts
        return t

    def _target_at(self, xr, yr):
        app = self.app
        # which part of Nabu is under the mouse - worked out from positions, not from "the window under
        # the mouse", because the blue shade itself can be under the mouse
        w = None
        for cand in (app.nav, app.tree, app.projview._tv, app.inbox._tv):
            try:
                if cand.winfo_ismapped() and cand.winfo_rootx() <= xr < cand.winfo_rootx() + cand.winfo_width() \
                        and cand.winfo_rooty() <= yr < cand.winfo_rooty() + cand.winfo_height():
                    w = cand
                    break
            except tk.TclError:
                pass
        if w is app.nav:
            iid = app.nav.identify_row(yr - app.nav.winfo_rooty())
            if iid == "inbox" and all(not os.path.isdir(p) for p in self.items):
                return ("inbox",)
            if iid == "trash":
                return ("trash",)
            return None
        if w is app.tree:
            tv = app.tree
            y = yr - tv.winfo_rooty()
            iid = tv.identify_row(y)
            if not iid:            # empty space under the list: end of the top level
                projs = lib.projects()
                if projs and all(os.path.isdir(p) for p in self.items):
                    return ("place", projs[-1], "below")
                return None
            if iid.startswith("empty:"):
                folder = iid[6:]
                return ("place", folder, "into") if os.path.isdir(folder) and self._valid_into(folder) else None
            if iid in self.items:
                return None
            bb = tv.bbox(iid)
            frac = (y - bb[1]) / float(max(1, bb[3])) if bb else 0.5
            if os.path.isdir(iid):
                if frac < 0.25:
                    where = "above"
                elif frac > 0.75 and not tv.item(iid, "open"):
                    where = "below"
                else:
                    where = "into"
                if where == "into":
                    if not self._valid_into(iid):
                        return None
                    # hovering on a closed folder opens it after a moment
                    if self.hover[0] == iid:
                        if time.time() - self.hover[1] > 0.8 and not tv.item(iid, "open"):
                            app._tree_open(iid, True)
                    else:
                        self.hover = (iid, time.time())
                else:
                    if not self._valid_into(os.path.dirname(iid)):
                        return None
                    top = os.path.normcase(os.path.dirname(iid)) == os.path.normcase(os.path.abspath(NOTES_DIR))
                    if top and not all(os.path.isdir(p) for p in self.items):
                        return ("place", iid, "into")     # notes can't sit at the very top level
                return ("place", iid, where)
            # a note row: above / below it (in its folder)
            if not self._valid_into(os.path.dirname(iid)):
                return None
            return ("place", iid, "above" if frac < 0.5 else "below")
        # onto a folder row in an open folder list: move it inside
        for view in (app.projview, app.inbox):
            tv = view._tv
            if w is tv and view.winfo_ismapped():
                iid = tv.identify_row(yr - tv.winfo_rooty())
                if iid and os.path.isdir(iid) and iid not in self.items and self._valid_into(iid):
                    return ("folder", iid, (tv, iid))
        # anywhere else on the page area (or well outside the window): open it there
        t = app.ws.target(xr, yr)
        if not t:
            return None
        if t["kind"] != "out":
            try:
                if xr < app.content.winfo_rootx():
                    return None              # over the sidebar, but not on anything there
            except tk.TclError:
                return None
        if all(os.path.isdir(p) for p in self.items):
            return ("open", t) if t["kind"] != "out" else None
        return ("open", t)

    # ------------------------------------------------------------ do it
    def _drop(self, target):
        app = self.app
        items = [p for p in self.items if os.path.exists(p)]
        if not items:
            return
        kind = target[0]
        if kind == "trash":
            app._trash_mixed(items)
            return
        if kind == "inbox":
            app.move_notes(items, INBOX_DIR)
            return
        if kind == "folder":
            app.move_notes(items, target[1])
            return
        if kind == "open":
            notes = [p for p in items if os.path.isfile(p)]
            if notes:
                app.ws.drop_notes(target[1], notes, *self.last_xy)
            else:
                app.show_project(items[0])
                app._reveal(items[0])
            return
        _, tgt, where = target
        app.ws.save_all()
        moved = 0
        anchor, mode = tgt, where
        for p in items:
            try:
                new = lib.place(p, anchor, mode)
            except Exception as ex:
                T.info(self.root, "Nabu Notes", str(ex))
                break
            if os.path.normcase(new) != os.path.normcase(p):
                if os.path.isdir(p):
                    app._rebase_open_note(p, new)
                else:
                    app._repath(p, new)
            if mode in ("above", "below"):
                anchor, mode = new, "below"      # keep several dragged items together, in order
            moved += 1
        if where == "into" and app.tree.exists(tgt):
            app._tree_open(tgt, True)
        app.refresh_library()
        if moved:
            dest = os.path.dirname(tgt) if where != "into" else tgt
            name = "the top level" if os.path.normcase(dest) == os.path.normcase(os.path.abspath(NOTES_DIR)) \
                else "“%s”" % lib.crumbs(dest)
            app.set_status("Moved %d item%s %s %s." % (moved, "" if moved == 1 else "s",
                                                        "into" if where == "into" else "to", name))


class ExplorerHint:
    """A label beside the mouse while files dragged in from Windows Explorer are over a part of Nabu,
    saying what will happen to them if let go there (same look as the label of Nabu's own drags)."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.lbl = None
        self.text = ""

    def show(self, text, xr, yr, ok=True):
        if self.win is None or not self.win.winfo_exists():
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.lbl = tk.Label(self.win, bg=T.PANEL, font=T.UI_BOLD, padx=10, pady=4, justify="left")
            self.lbl.pack()
        self.text = text
        self.lbl.configure(text=text, fg=T.FG if ok else T.FAINT)
        self.win.geometry("+%d+%d" % (xr + 18, yr + 16))

    def hide(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self.text = ""


def explorer_files(ev, root):
    """The files of a drag from Windows Explorer (may be empty while still dragging)."""
    try:
        return list(root.tk.splitlist(ev.data or ""))
    except (tk.TclError, AttributeError, TypeError):
        return []
