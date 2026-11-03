"""Crop a picture in a note: right-click the picture > Crop...

The whole picture is shown with a box over it; the part outside the box is darkened.
  * drag anywhere outside the box ........ draw a new box
  * drag inside the box .................. move it
  * drag an edge or a corner ............. make it bigger or smaller
Enter or "Crop" keeps what's inside the box, Esc or "Cancel" leaves the picture as it was.
"""
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageEnhance

import nabu_doc as nd
import nabu_theme as T
from nabu_pictool import tk_photo as _photo

GRAB = 9          # how close (screen pixels) to an edge counts as grabbing it
MIN_SIDE = 8      # the smallest box, in screen pixels


class CropWindow:
    def __init__(self, editor, name):
        self.editor = editor
        self.name = name
        img = nd.load_picture(editor.images[name]["rel"])
        self.W, self.H = img.size
        k = T.ui_scale(editor.root)
        self.scale = min(1.0, 760 * k / self.W, 520 * k / self.H)      # shown size / real size
        dw, dh = max(1, round(self.W * self.scale)), max(1, round(self.H * self.scale))
        self.bright = img.resize((dw, dh), Image.LANCZOS)
        dim = ImageEnhance.Brightness(self.bright.convert("RGB")).enhance(0.35)
        self.dim_photo = _photo(dim)
        self.bright_photo = None
        self.box = (0.0, 0.0, float(dw), float(dh))   # the part to keep, in screen pixels
        self.mode = None                              # what the current drag does: new | move | edges
        self.edges = ""                               # which edges are being dragged: some of "lrtb"
        self.start = (0, 0)
        self.start_box = self.box
        self.done = False

        self.win = win = T.toplevel(editor.root, "Crop picture")
        f = ttk.Frame(win, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Drag across the picture to choose the part to keep. "
                          "Drag the box to move it, or its edges to change its size.",
                  wraplength=max(320, dw), justify="left").pack(anchor="w", pady=(0, 10))
        self.canvas = c = tk.Canvas(f, width=dw, height=dh, bg=T.DESK, highlightthickness=0, cursor="crosshair")
        c.pack()
        c.create_image(0, 0, image=self.dim_photo, anchor="nw")
        self.keep_item = c.create_image(0, 0, anchor="nw")
        self.frame_item = c.create_rectangle(0, 0, 0, 0, outline="white", width=1, dash=(4, 3))
        self.size_lbl = ttk.Label(f, text="", foreground=T.MUTED)
        self.size_lbl.pack(anchor="w", pady=(8, 0))
        b = ttk.Frame(f)
        b.pack(fill="x", pady=(10, 0))
        ttk.Button(b, text="Whole picture", command=self.reset).pack(side="left")
        ttk.Button(b, text="Cancel", command=self.cancel).pack(side="right", padx=(6, 0))
        ttk.Button(b, text="Crop", style="Accent.TButton", command=self.apply).pack(side="right")
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Motion>", self._hover)
        win.bind("<Return>", lambda _e: self.apply())
        win.bind("<Escape>", lambda _e: self.cancel())
        win.protocol("WM_DELETE_WINDOW", self.cancel)
        self._draw()
        T.fit(win)
        try:
            win.grab_set()
        except tk.TclError:          # (not on screen yet)
            pass
        win.focus_set()

    # ------------------------------------------------------------ the box
    def real_box(self):
        """The box in the picture's own pixels."""
        l, t, r, b = self.box
        s = self.scale
        return (round(l / s), round(t / s), min(self.W, round(r / s)), min(self.H, round(b / s)))

    def set_box(self, box):
        """Choose the part to keep, in the picture's own pixels (left, top, right, bottom)."""
        s = self.scale
        self._set_screen_box(tuple(v * s for v in box))

    def _set_screen_box(self, box):
        dw, dh = self.bright.size
        l, t, r, b = box
        l, r = sorted((l, r))
        t, b = sorted((t, b))
        l, t = max(0.0, min(l, dw - 1)), max(0.0, min(t, dh - 1))
        r, b = min(float(dw), max(r, l + 1)), min(float(dh), max(b, t + 1))
        self.box = (l, t, r, b)
        self._draw()

    def _draw(self):
        l, t, r, b = (int(round(v)) for v in self.box)
        c = self.canvas
        if r - l >= 1 and b - t >= 1:
            self.bright_photo = _photo(self.bright.crop((l, t, r, b)))
            c.itemconfigure(self.keep_item, image=self.bright_photo)
            c.coords(self.keep_item, l, t)
        c.coords(self.frame_item, l, t, r - 1, b - 1)
        rl, rt, rr, rb = self.real_box()
        whole = (rl, rt, rr, rb) == (0, 0, self.W, self.H)
        self.size_lbl.config(text="Whole picture (%d × %d)" % (self.W, self.H) if whole
                             else "Keeping %d × %d of %d × %d" % (rr - rl, rb - rt, self.W, self.H))

    def _edges_at(self, x, y):
        l, t, r, b = self.box
        if not (l - GRAB <= x <= r + GRAB and t - GRAB <= y <= b + GRAB):
            return None
        e = ""
        if abs(x - l) <= GRAB:
            e += "l"
        elif abs(x - r) <= GRAB:
            e += "r"
        if abs(y - t) <= GRAB:
            e += "t"
        elif abs(y - b) <= GRAB:
            e += "b"
        return e

    # ------------------------------------------------------------ mouse
    _CURSORS = {"l": "sb_h_double_arrow", "r": "sb_h_double_arrow", "t": "sb_v_double_arrow",
                "b": "sb_v_double_arrow", "lt": "size_nw_se", "rb": "size_nw_se", "rt": "size_ne_sw",
                "lb": "size_ne_sw", "": "fleur"}

    def _hover(self, ev):
        e = self._edges_at(ev.x, ev.y)
        try:
            self.canvas.config(cursor="crosshair" if e is None else self._CURSORS.get(e, "fleur"))
        except tk.TclError:
            self.canvas.config(cursor="crosshair")

    def _press(self, ev):
        self.start = (ev.x, ev.y)
        self.start_box = self.box
        e = self._edges_at(ev.x, ev.y)
        whole =self.box == (0.0, 0.0) + tuple(float(v) for v in self.bright.size)
        if e is None or (whole and e == ""):        # outside the box (or it's still the whole picture): a new one
            self.mode, self.edges = "new", ""
        elif e == "":
            self.mode, self.edges = "move", ""
        else:
            self.mode, self.edges = "edges", e

    def _drag(self, ev):
        x0, y0 = self.start
        dx, dy = ev.x - x0, ev.y - y0
        l, t, r, b = self.start_box
        dw, dh = self.bright.size
        if self.mode == "new":
            if abs(dx) < 3 and abs(dy) < 3:
                return
            self._set_screen_box((x0, y0, ev.x, ev.y))
        elif self.mode == "move":
            w, h = r - l, b - t
            nl = max(0, min(l + dx, dw - w))
            nt = max(0, min(t + dy, dh - h))
            self._set_screen_box((nl, nt, nl + w, nt + h))
        elif self.mode == "edges":
            if "l" in self.edges:
                l = min(l + dx, r - MIN_SIDE)
            if "r" in self.edges:
                r = max(r + dx, l + MIN_SIDE)
            if "t" in self.edges:
                t = min(t + dy, b - MIN_SIDE)
            if "b" in self.edges:
                b = max(b + dy, t + MIN_SIDE)
            self._set_screen_box((l, t, r, b))

    def _release(self, ev):
        if self.mode == "new":
            l, t, r, b = self.box
            if r - l < MIN_SIDE or b - t < MIN_SIDE:     # just a click, or a tiny box: keep what there was
                self._set_screen_box(self.start_box)
        self.mode = None

    # ------------------------------------------------------------ buttons
    def reset(self):
        self._set_screen_box((0, 0) + self.bright.size)

    def apply(self):
        box = self.real_box()
        self._close()
        self.done = self.editor.crop_image(self.name, box)
        return self.done

    def cancel(self):
        self._close()

    def _close(self):
        try:
            self.win.grab_release()
            self.win.destroy()
        except tk.TclError:
            pass
