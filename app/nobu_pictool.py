"""Moving and resizing pictures right on the page.

  * click a picture ............. it gets a blue frame and a square handle in its bottom-right corner
  * drag the picture ............ a blue line shows where it will go; let go to move it there
  * drag the corner handle ...... make it bigger or smaller (it keeps its shape)
  * Delete / Backspace .......... removes the selected picture;  Esc or a click elsewhere: done
Every move or resize is one Ctrl+Z step.
"""
import base64
import io
import tkinter as tk

from PIL import Image, ImageOps

import nobu_theme as T
from nobu_config import abs_from_home

DRAG_START = 5        # pixels the mouse must move before a press becomes a drag
HANDLE = 11           # size of the corner handle (screen pixels)
MIN_W, MAX_W = 30, 624     # picture width in page pixels (624 = the full 6.5" text width)


class PictureTool:
    def __init__(self, editor):
        self.ed = editor
        t = self.t = editor.text
        self.sel = None              # name of the selected picture
        self.press = None            # (x, y) where the mouse went down on a picture
        self.dragging = False
        self.resize = None           # while dragging the handle: start values
        self.over = False            # the mouse is over a picture (for the cursor)
        self._sync_job = None
        self._last_preview = 0.0
        self.frame = [tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=0) for _ in range(4)]
        self.handle = tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=1, highlightbackground=T.PAPER,
                               width=HANDLE, height=HANDLE)
        for c in ("size_nw_se", "bottom_right_corner"):        # (Windows' name, then the Linux one)
            try:
                self.handle.config(cursor=c)
                break
            except tk.TclError:
                pass
        self.caret = tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=0, width=3)
        self.handle.bind("<ButtonPress-1>", self._resize_press)
        self.handle.bind("<B1-Motion>", self._resize_drag)
        self.handle.bind("<ButtonRelease-1>", self._resize_release)
        t.bind("<ButtonPress-1>", self._press)
        t.bind("<B1-Motion>", self._drag)
        t.bind("<ButtonRelease-1>", self._release, add="+")
        t.bind("<Motion>", self._hover, add="+")
        t.bind("<Escape>", lambda e: self.deselect(), add="+")

    # ------------------------------------------------------------ selecting
    def select(self, name):
        if name not in self.ed.images:
            return
        self.sel = name
        self.t.tag_remove("sel", "1.0", "end")
        self.sync()
        self.ed.app.set_status("Drag the picture to move it, or its corner to change its size. "
                               "Right-click for more.")

    def deselect(self):
        self.sel = None
        self.press = None
        self.dragging = False
        self.resize = None
        for w in self.frame + [self.handle, self.caret]:
            w.place_forget()

    def sync(self):
        """Keep the frame and handle on the picture while the page scrolls, zooms or changes."""
        if self._sync_job:
            try:
                self.t.after_cancel(self._sync_job)
            except tk.TclError:
                pass
            self._sync_job = None
        if not self.sel:
            return
        try:
            self.t.index(self.sel)
        except tk.TclError:              # the picture is gone (deleted, undone, another note opened)
            self.deselect()
            return
        bb = self.t.bbox(self.sel)
        if not bb:                       # scrolled out of sight
            for w in self.frame + [self.handle]:
                w.place_forget()
        else:
            x, y, w, h = bb
            b = 2
            for f, (fx, fy, fw, fh) in zip(self.frame, ((x - b, y - b, w + 2 * b, b), (x - b, y + h, w + 2 * b, b),
                                                         (x - b, y, b, h), (x + w, y, b, h))):
                f.place(x=fx, y=fy, width=fw, height=fh)
            self.handle.place(x=x + w - HANDLE // 2, y=y + h - HANDLE // 2, width=HANDLE, height=HANDLE)
            self.handle.lift()
        self._sync_job = T.later(self.t, 150, self.sync)

    # ------------------------------------------------------------ moving
    def _press(self, e):
        name, _ix = self.ed._image_at(e.x, e.y)
        if not name or name not in self.ed.images:
            if self.sel:
                self.deselect()
            return None
        self.t.focus_set()
        self.select(name)
        self.press = (e.x, e.y)
        self.dragging = False
        return "break"                   # (no text selection starts under a picture)

    def _gap_at(self, x, y):
        """The place between two characters closest to the mouse (as Tk does for clicks)."""
        t = self.t
        idx = t.index("@%d,%d" % (x, y))
        bb = t.bbox(idx)
        if bb and x > bb[0] + bb[2] / 2 and t.get(idx) != "\n":
            idx = t.index(idx + " +1c")
        return idx

    def _drag(self, e):
        if self.resize is not None:
            return "break"
        if not self.press or not self.sel:
            return None
        if not self.dragging:
            if abs(e.x - self.press[0]) < DRAG_START and abs(e.y - self.press[1]) < DRAG_START:
                return "break"
            self.dragging = True
            self.t.config(cursor="fleur")
        h = self.t.winfo_height()
        if e.y < 18:
            self.t.yview_scroll(-1, "units")
        elif e.y > h - 18:
            self.t.yview_scroll(1, "units")
        gap = self._gap_at(e.x, e.y)
        bb = self.t.bbox(gap) or self.t.bbox(gap + " -1c")
        if bb:
            x = bb[0] if self.t.bbox(gap) else bb[0] + bb[2]
            self.caret.place(x=x - 1, y=bb[1], width=3, height=max(bb[3], 12))
            self.caret.lift()
        return "break"

    def _release(self, e):
        if self.resize is not None:
            return "break"
        if not self.press:
            return None
        was = self.dragging
        self.press = None
        self.dragging = False
        self.caret.place_forget()
        self.t.config(cursor="xterm")
        if was and self.sel:
            new = self.ed.move_image(self.sel, self._gap_at(e.x, e.y))
            if new:
                self.select(new)
        return "break"

    def _hover(self, e):
        if self.dragging or self.resize is not None:
            return
        name, _ix = self.ed._image_at(e.x, e.y)
        if name and not self.over:
            self.over = True
            self.t.config(cursor="fleur")
        elif not name and self.over:
            self.over = False
            self.t.config(cursor="xterm")

    # ------------------------------------------------------------ resizing
    def _resize_press(self, e):
        info = self.ed.images.get(self.sel)
        if not info:
            return "break"
        with Image.open(abs_from_home(info["rel"])) as src:      # (closed at once: never locks the file)
            img = ImageOps.exif_transpose(src)
            img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if ("A" in img.mode or img.mode == "P") else "RGB")
        img.thumbnail((1600, 1600))                               # (a smaller copy for the live preview)
        self.resize = {"x": e.x_root, "y": e.y_root, "w": float(info["w"]), "img": img, "undo": False}
        return "break"

    def scale(self):
        """Screen pixels per page pixel at the current zoom."""
        return self.ed.dpi / 96.0 * self.ed.zoom

    def _resize_drag(self, e):
        r = self.resize
        if not r or self.sel not in self.ed.images:
            return "break"
        img = r["img"]
        dx = e.x_root - r["x"]
        dy = (e.y_root - r["y"]) * img.width / max(1, img.height)    # dragging down grows it too
        grow = dx if abs(dx) >= abs(dy) else dy
        w = max(MIN_W, min(MAX_W, r["w"] + grow / self.scale()))
        self.set_width(self.sel, w, preview=True)
        return "break"

    def _resize_release(self, e):
        r = self.resize
        self.resize = None
        if r and self.sel in self.ed.images and r["undo"]:
            self.ed.resize_image(self.sel, self.ed.images[self.sel]["w"], undo=False)    # final, sharp picture
        self.sync()
        return "break"

    def set_width(self, name, w, preview=False):
        """Live resize while dragging (a quick picture; the sharp one comes when you let go)."""
        info = self.ed.images[name]
        r = self.resize
        if r is not None and not r["undo"]:
            self.ed._push_undo()
            r["undo"] = True
        w = int(round(w))
        if w == info["w"]:
            return
        img = r["img"] if r else None
        if preview and img is not None:
            disp = max(20, int(w * self.scale()))
            pic = img.resize((disp, max(1, round(img.height * disp / img.width))), Image.BILINEAR)
            buf = io.BytesIO()
            pic.save(buf, "PNG")
            photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
            self.t.image_configure(name, image=photo)
            info.update(photo=photo, w=w)
            self.ed.app.set_status("Picture width: %.1f in" % (w / 96.0))
            self.sync()
        else:
            self.ed.resize_image(name, w)
