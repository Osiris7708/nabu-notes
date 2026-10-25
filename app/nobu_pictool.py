"""Moving and resizing pictures right on the page.

  * click a picture ............. a blue frame appears around it, with a square on each corner and side
  * drag the picture ............ a see-through copy follows the mouse and a blue line shows where it will
                                  land; let go to move it there (Esc while dragging: leave it where it was)
  * drag a side (or its square) . stretch it: left / right side = wider or narrower, top / bottom = taller
                                  or shorter
  * drag a corner ............... bigger or smaller, keeping its shape (hold Shift to stretch freely)
  * Delete / Backspace .......... removes the selected picture;  Esc or a click elsewhere: done
Every move or resize is one Ctrl+Z step. Sizes are page pixels (96 to the inch), as stored in the note.
"""
import base64
import io
import tkinter as tk

from PIL import Image, ImageOps

import nobu_theme as T
from nobu_config import abs_from_home

DRAG_START = 5            # pixels the mouse must move before a press becomes a drag
BAR = 4                   # thickness of the frame around a selected picture (screen pixels)
SQ = 10                   # size of the squares on its corners and sides
MIN_W, MIN_H = 30, 20     # smallest picture (page pixels)
MAX_W, MAX_H = 624, 864   # the page's text area: 6.5" wide, 9" tall
PREVIEW_MS = 16           # live resize redraws at most this often

_CURSORS = {"l": ("sb_h_double_arrow",), "r": ("sb_h_double_arrow",), "t": ("sb_v_double_arrow",),
            "b": ("sb_v_double_arrow",), "tl": ("size_nw_se", "top_left_corner"),
            "br": ("size_nw_se", "bottom_right_corner"), "tr": ("size_ne_sw", "top_right_corner"),
            "bl": ("size_ne_sw", "bottom_left_corner")}


def tk_photo(img):
    """A PIL picture ready for Tk (fast path; the PNG route only if ImageTk is missing)."""
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(img)
    except Exception:
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))


def _set_cursor(w, names):
    for c in names:
        try:
            w.config(cursor=c)
            return
        except tk.TclError:
            pass


class PictureTool:
    def __init__(self, editor):
        self.ed = editor
        t = self.t = editor.text
        self.sel = None              # name of the selected picture
        self.press = None            # (x, y) where the mouse went down on the picture
        self.dragging = False        # moving the picture
        self.ghost = None            # the see-through copy that follows the mouse
        self.ghost_photo = None
        self.resize = None           # while dragging a side or corner: what it started from
        self.over = False            # the mouse is over a picture (for the cursor)
        self._sync_job = None
        self._poll_job = None
        self._preview_job = None
        k = T.ui_scale(t)
        self.B, self.S = max(BAR, round(BAR * k)), max(SQ, round(SQ * k))     # (bigger on high-resolution screens)
        self.bars = {}
        self.squares = {}
        for e in ("t", "b", "l", "r"):
            self.bars[e] = self._grip(tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=0), e)
        for e in ("tl", "t", "tr", "r", "br", "b", "bl", "l"):
            self.squares[e] = self._grip(tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=1,
                                                  highlightbackground=T.PAPER), e)
        self.caret = tk.Frame(t, bg=T.ACCENT, bd=0, highlightthickness=0)
        t.bind("<ButtonPress-1>", self._press)
        t.bind("<B1-Motion>", self._drag)
        t.bind("<ButtonRelease-1>", self._release, add="+")
        t.bind("<Motion>", self._hover, add="+")
        t.bind("<Escape>", self._escape, add="+")
        t.bind("<Configure>", lambda e: self.sync_soon(), add="+")

    def _grip(self, w, edge):
        _set_cursor(w, _CURSORS[edge])
        w.bind("<ButtonPress-1>", lambda e, k=edge: self._resize_press(e, k))
        w.bind("<B1-Motion>", self._resize_drag)
        w.bind("<ButtonRelease-1>", self._resize_release)
        return w

    def _widgets(self):
        return list(self.bars.values()) + list(self.squares.values())

    # ------------------------------------------------------------ where things are
    def _inset(self):
        """place() inside a Text counts from inside its border and padding; bbox() counts from its corner."""
        t = self.t
        px = lambda v: int(round(t.winfo_fpixels(v)))     # noqa: E731
        bd = px(t.cget("borderwidth")) + px(t.cget("highlightthickness"))
        return bd + px(t.cget("padx")), bd + px(t.cget("pady"))

    def geometry(self, name=None):
        """The picture's box on screen, in place() terms: (x, y, width, height), or None if out of sight."""
        name = name or self.sel
        info = self.ed.images.get(name)
        try:
            bb = self.t.bbox(name)
        except tk.TclError:
            return None
        if not bb or not info:
            return None
        ix, iy = self._inset()
        photo = info["photo"]
        w, h = photo.width(), photo.height()
        x, y = bb[0], bb[1]
        if bb[3] < h and y <= iy + 1:          # partly scrolled off the top: bbox only covers the visible part
            y = bb[1] + bb[3] - h
        if bb[2] < w and x <= ix + 1:
            x = bb[0] + bb[2] - w
        return x - ix, y - iy, w, h

    def _show_box(self, x, y, w, h):
        B, S = self.B, self.S
        for e, (fx, fy, fw, fh) in (("t", (x - B, y - B, w + 2 * B, B)), ("b", (x - B, y + h, w + 2 * B, B)),
                                    ("l", (x - B, y, B, h)), ("r", (x + w, y, B, h))):
            self.bars[e].place(x=fx, y=fy, width=fw, height=fh)
        cx, cy = {"l": x - B / 2, "m": x + w / 2, "r": x + w + B / 2}, {"t": y - B / 2, "m": y + h / 2, "b": y + h + B / 2}
        for e, (hx, hy) in (("tl", ("l", "t")), ("t", ("m", "t")), ("tr", ("r", "t")), ("r", ("r", "m")),
                            ("br", ("r", "b")), ("b", ("m", "b")), ("bl", ("l", "b")), ("l", ("l", "m"))):
            sq = self.squares[e]
            sq.place(x=int(cx[hx] - S / 2), y=int(cy[hy] - S / 2), width=S, height=S)
            sq.lift()

    def _hide_box(self):
        for w in self._widgets():
            w.place_forget()

    # ------------------------------------------------------------ selecting
    def select(self, name):
        if name not in self.ed.images:
            return
        self.sel = name
        self.t.tag_remove("sel", "1.0", "end")
        self.sync()
        self.ed.app.set_status("Drag the picture to move it. Drag a side to stretch it, or a corner to resize it "
                               "(Shift: stretch freely). Right-click for more.")

    def deselect(self):
        self._end_drag()
        self.sel = None
        self.press = None
        self.resize = None
        self._hide_box()

    def sync_soon(self):
        if self.sel and self._sync_job is None:
            self._sync_job = T.later(self.t, None, self.sync)

    def sync(self):
        """Put the frame back on the picture (after scrolling, zooming, typing, resizing...)."""
        self._sync_job = None
        if not self.sel:
            return
        try:
            self.t.index(self.sel)
        except tk.TclError:              # the picture is gone (deleted, undone, another note opened)
            self.deselect()
            return
        self.t.update_idletasks()
        g = self.geometry()
        if g:
            self._show_box(*g)
        else:
            self._hide_box()
        if self._poll_job is None:       # (text typed above it moves it without any other signal)
            self._poll_job = T.later(self.t, 400, self._poll)

    def _poll(self):
        self._poll_job = None
        if self.sel and self.resize is None:
            self.sync()

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

    def _start_drag(self):
        self.dragging = True
        self.t.config(cursor="fleur")
        info = self.ed.images.get(self.sel)
        try:
            with Image.open(abs_from_home(info["rel"])) as src:
                img = ImageOps.exif_transpose(src)
                img.load()
            k = info["photo"].width()
            img.thumbnail((min(220, k), min(220, info["photo"].height())))
            self.ghost = g = tk.Toplevel(self.t)
            g.overrideredirect(True)
            try:
                g.attributes("-alpha", 0.6)
                g.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.ghost_photo = tk_photo(img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img)
            tk.Label(g, image=self.ghost_photo, bd=1, relief="solid", bg=T.ACCENT).pack()
        except Exception:
            self.ghost = None

    def _drag(self, e):
        if self.resize is not None:
            return "break"
        if not self.press or not self.sel:
            return None
        if not self.dragging:
            if abs(e.x - self.press[0]) < DRAG_START and abs(e.y - self.press[1]) < DRAG_START:
                return "break"
            self._start_drag()
        if self.ghost is not None:
            self.ghost.geometry("+%d+%d" % (e.x_root + 14, e.y_root + 10))
        h = self.t.winfo_height()
        if e.y < 24:
            self.t.yview_scroll(-1, "units")
        elif e.y > h - 24:
            self.t.yview_scroll(1, "units")
        gap = self._gap_at(e.x, e.y)
        here, before = self.t.bbox(gap), self.t.bbox(gap + " -1c")
        bb = here or before
        if bb:
            ix, iy = self._inset()
            x = bb[0] if here else bb[0] + bb[2]
            self.caret.place(x=x - 1 - ix, y=bb[1] - iy, width=3, height=max(bb[3], 14))
            self.caret.lift()
        return "break"

    def _end_drag(self):
        self.dragging = False
        self.caret.place_forget()
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except tk.TclError:
                pass
        self.ghost = self.ghost_photo = None
        try:
            self.t.config(cursor="xterm")
        except tk.TclError:
            pass

    def _release(self, e):
        if self.resize is not None:
            return "break"
        if not self.press:
            return None
        was = self.dragging
        self.press = None
        self._end_drag()
        inside = 0 <= e.x < self.t.winfo_width() and 0 <= e.y < self.t.winfo_height()
        if was and self.sel and inside:
            new = self.ed.move_image(self.sel, self._gap_at(e.x, e.y))
            if new:
                self.select(new)
                return "break"
        self.sync()
        return "break"

    def _escape(self, e):
        if self.dragging:                # stop the move; the picture stays where it was
            self.press = None
            self._end_drag()
            self.sync()
            return "break"
        if self.sel:
            self.deselect()
        return None

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
    def _resize_press(self, e, edge):
        info = self.ed.images.get(self.sel)
        if not info:
            return "break"
        with Image.open(abs_from_home(info["rel"])) as src:      # (closed at once: never locks the file)
            img = ImageOps.exif_transpose(src)
            img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if ("A" in img.mode or img.mode == "P") else "RGB")
        natural = img.height / float(img.width)                  # the picture's own shape (height / width)
        img.thumbnail((1600, 1600))                               # (a smaller copy for the live preview)
        k = self.ed.img_scale()
        w0 = float(info["w"])
        h0 = float(info["h"]) if info.get("h") else info["photo"].height() / k
        self.resize = {"edge": edge, "x": e.x_root, "y": e.y_root, "w0": w0, "h0": h0, "w": w0, "h": h0,
                       "natural": natural, "img": img, "undo": False}
        return "break"

    def new_size(self, edge, dx, dy, free=False):
        """Width and height (page pixels) after dragging edge by dx, dy page pixels."""
        r = self.resize
        w0, h0 = r["w0"], r["h0"]
        w, h = w0, h0
        if "r" in edge:
            w = w0 + dx
        if "l" in edge:
            w = w0 - dx
        if "b" in edge:
            h = h0 + dy
        if "t" in edge:
            h = h0 - dy
        if len(edge) == 2 and not free:          # a corner keeps the shape: the bigger change wins
            f = w / w0 if abs(w / w0 - 1) >= abs(h / h0 - 1) else h / h0
            f = max(f, MIN_W / w0, MIN_H / h0)
            f = min(f, MAX_W / w0, MAX_H / h0)
            return w0 * f, h0 * f
        return max(MIN_W, min(MAX_W, w)), max(MIN_H, min(MAX_H, h))

    def _resize_drag(self, e):
        r = self.resize
        if not r or self.sel not in self.ed.images:
            return "break"
        k = self.ed.img_scale()
        free = bool(getattr(e, "state", 0) & 0x0001)                # Shift held
        r["w"], r["h"] = self.new_size(r["edge"], (e.x_root - r["x"]) / k, (e.y_root - r["y"]) / k, free)
        if (round(r["w"]), round(r["h"])) == (round(r["w0"]), round(r["h0"])) and not r["undo"]:
            return "break"                       # (not moved yet)
        if not r["undo"]:
            self.ed._push_undo()
            r["undo"] = True
        if self._preview_job is None:
            self._preview_job = T.later(self.t, PREVIEW_MS, self._preview)
        return "break"

    def _preview(self):
        """Live resize: a quick picture at the new size (the sharp one comes when you let go)."""
        self._preview_job = None
        r = self.resize
        if not r or self.sel not in self.ed.images:
            return
        info = self.ed.images[self.sel]
        k = self.ed.img_scale()
        img = r["img"]
        photo = tk_photo(img.resize((max(1, int(r["w"] * k)), max(1, int(r["h"] * k))), Image.BILINEAR))
        self.t.image_configure(self.sel, image=photo)
        info["photo"] = photo
        self.ed.app.set_status("Picture: %.1f × %.1f in" % (r["w"] / 96.0, r["h"] / 96.0))
        self.sync()

    def _resize_release(self, e=None):
        r = self.resize
        if self._preview_job is not None:
            try:
                self.t.after_cancel(self._preview_job)
            except tk.TclError:
                pass
            self._preview_job = None
        self.resize = None
        if r and r["undo"] and self.sel in self.ed.images:
            w, h = r["w"], r["h"]
            same_shape = abs(h - w * r["natural"]) <= 0.02 * h
            self.ed.resize_image(self.sel, w, None if same_shape else h, undo=False)    # the final, sharp picture
        self.sync()
        return "break"
