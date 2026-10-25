"""Moving and resizing pictures right on the page.

  * click a picture ............. a blue frame appears around it, with a square on each corner and side
  * drag the picture ............ it comes loose from its line (a floating picture, text flowing round it -
                                  see nobu_float) and follows the mouse anywhere on the page. Near the left
                                  edge, the middle or the right edge it snaps there (hold Alt: no snapping).
  * Ctrl + drag ................. move it within the text instead: a see-through copy follows the mouse and
                                  a blue line shows where it will land (Esc while dragging: leave it)
  * drag a side (or its square) . stretch it: left / right side = wider or narrower, top / bottom = taller
                                  or shorter
  * drag a corner ............... bigger or smaller, keeping its shape (hold Shift to stretch freely)
  * Delete / Backspace .......... removes the selected picture;  Esc or a click elsewhere: done
Every move or resize is one Ctrl+Z step. Sizes are page pixels (96 to the inch), as stored in the note.
"""
import base64
import io
import tkinter as tk

from PIL import Image

import nobu_doc as nd
import nobu_rich as R
import nobu_theme as T

DRAG_START = 5            # pixels the mouse must move before a press becomes a drag
SNAP = 12                 # page pixels: this close to the left edge, the middle or the right edge, a picture snaps
BAR = 4                   # thickness of the frame around a selected picture (screen pixels)
SQ = 10                   # size of the squares on its corners and sides
MIN_W, MIN_H = 30, 20     # smallest picture (page pixels)
MAX_W, MAX_H = R.TEXT_W_PX, R.TEXT_H_PX   # the page's text area: 6.5" wide, 9" tall
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
        self.fpress = None           # while dragging a floating picture: where it started
        self.nudging = False         # arrow keys are moving the selected floating picture (one undo step)
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
    def _float(self, name=None):
        return self.ed.flow.is_float(name or self.sel)

    def geometry(self, name=None):
        """The picture's box on screen, in place() terms: (x, y, width, height), or None if out of sight."""
        name = name or self.sel
        info = self.ed.images.get(name)
        if info and info.get("float"):                 # a floating picture: where it was placed
            return info["_px"], info["_py"], info["photo"].width(), info["photo"].height()
        try:
            bb = self.t.bbox(name)
        except tk.TclError:
            return None
        if not bb or not info:
            return None
        ix, iy = self.ed._text_inset()
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
            self.bars[e].lift()
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
        if name != self.sel:
            self.nudging = False
        self.sel = name
        self.t.tag_remove("sel", "1.0", "end")
        self.sync()
        if self._float(name):
            self.ed.app.set_status("Drag the picture anywhere on the page (arrow keys nudge it). Drag a side to "
                                   "stretch it, or a corner to resize it. Right-click > Text wrapping for more.")
        else:
            self.ed.app.set_status("Drag the picture to move it. Drag a side to stretch it, or a corner to resize it "
                                   "(Shift: stretch freely). Right-click > Text wrapping to place it anywhere.")

    def deselect(self):
        self._end_drag()
        self.sel = None
        self.press = None
        self.resize = None
        self.fpress = None
        self.nudging = False
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
        self.press = (e.x, e.y, e.x_root, e.y_root)
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
            img = nd.load_picture(info["rel"])
            k = info["photo"].width()
            img.thumbnail((min(220, k), min(220, info["photo"].height())))
            self.ghost = g = tk.Toplevel(self.t)
            g.overrideredirect(True)
            try:
                g.attributes("-alpha", 0.6)
                g.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.ghost_photo = tk_photo(img)
            tk.Label(g, image=self.ghost_photo, bd=1, relief="solid", bg=T.ACCENT).pack()
        except Exception:
            self.ghost = None

    def _drag(self, e):
        if self.resize is not None:
            return "break"
        if self.fpress is not None:      # (a picture that came loose when the drag began: it follows the mouse)
            return self._fdrag(e)
        if not self.press or not self.sel:
            return None
        if not self.dragging:
            if abs(e.x - self.press[0]) < DRAG_START and abs(e.y - self.press[1]) < DRAG_START:
                return "break"
            if not getattr(e, "state", 0) & 0x0004:      # plain drag: anywhere on the page (Ctrl: within the text)
                return self._come_loose(e)
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
            ix, iy = self.ed._text_inset()
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
        if self.fpress is not None:
            self.press = None
            return self._frelease(e)
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
        if self.fpress is not None:      # stop moving a floating picture: back where it was
            fp, self.fpress = self.fpress, None
            info = self.ed.images.get(fp["name"])
            if info and fp.get("undo_taken"):        # (it came loose from a line: undo that, put it back)
                self.ed.undo()
            elif info and fp["moved"]:
                info["float"]["x"], info["float"]["y"] = fp["fx"], fp["fy"]
                self.t.mark_set(fp["name"], fp["anchor"])
                if self.ed._undo:
                    self.ed._undo.pop()
                self.ed.flow.reflow()
            self.t.config(cursor="xterm")
            return "break"
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

    # ------------------------------------------------------------ floating pictures
    def _come_loose(self, e):
        """A picture in a line of text, dragged: it becomes a floating picture right where it is (text on the
        side with more room) and follows the mouse from here on."""
        name = self.sel
        self.press, press = None, self.press
        new = self.ed.set_wrap(name, "square", "largest")      # (one Ctrl+Z step, taken here)
        if not new or new not in self.ed.images:
            return "break"
        info = self.ed.images[new]
        fl = self.ed.flow
        self.fpress = {"name": new, "x": press[2], "y": press[3], "px": info["_px"], "fx": info["float"]["x"],
                       "fy": info["float"]["y"], "top": info["_doc_top"] if info["_doc_top"] is not None else 0,
                       "anchor": self.t.index(new), "off": fl.view_offset(), "moved": True, "undo_taken": True}
        self.ed.app.set_status("The picture came loose: put it anywhere. Right-click > Text wrapping > In line "
                               "with text puts it back in a line. (Ctrl + drag moves it within the text.)")
        return self._fdrag(e)

    def snap_x(self, x, w):
        """x (page pixels) moved to the left edge, the middle or the right edge when it's close to one."""
        for spot in (0, (MAX_W - w) / 2.0, MAX_W - w):
            if abs(x - spot) <= SNAP:
                return spot
        return x

    def bind_float(self, name, lab):
        lab.bind("<ButtonPress-1>", lambda e, n=name: self._fpress(e, n))
        lab.bind("<B1-Motion>", self._fdrag)
        lab.bind("<ButtonRelease-1>", self._frelease)
        lab.bind("<Double-Button-1>", lambda e, n=name: self.ed._open_picture(n))
        lab.bind("<Button-3>", lambda e, n=name: (self.select(n), self.ed.picture_menu(n, e.x_root, e.y_root)))
        lab.bind("<Escape>", self._escape)

    def _fpress(self, e, name):
        info = self.ed.images.get(name)
        if not info:
            return "break"
        self.t.focus_set()
        self.select(name)
        f = info["float"]
        fl = self.ed.flow
        self.fpress = {"name": name, "x": e.x_root, "y": e.y_root, "px": info["_px"], "fx": f["x"], "fy": f["y"],
                       "top": info["_doc_top"] if info["_doc_top"] is not None else 0, "anchor": self.t.index(name),
                       "off": fl.view_offset(), "moved": False}
        return "break"

    def _fdrag(self, e):
        fp = self.fpress
        if not fp or fp["name"] not in self.ed.images:
            return "break"
        dx, dy = e.x_root - fp["x"], e.y_root - fp["y"]
        if not fp["moved"]:
            if abs(dx) < DRAG_START and abs(dy) < DRAG_START:
                return "break"
            fp["moved"] = True
            self.ed._push_undo()
        fl = self.ed.flow
        wy = e.y_root - self.t.winfo_rooty()
        if wy < 24:                       # near the top or bottom edge: the page scrolls
            self.t.yview_scroll(-1, "units")
        elif wy > self.t.winfo_height() - 24:
            self.t.yview_scroll(1, "units")
        k = self.ed.img_scale()
        scrolled = fl.view_offset() - fp["off"]
        x = fp["fx"] + dx / k
        if not getattr(e, "state", 0) & 0x20000:         # (Alt held: no snapping)
            x = self.snap_x(x, self.ed.images[fp["name"]]["photo"].width() / k)
        fl.move_to(fp["name"], x, doc_top=fp["top"] + dy + scrolled)
        self.ed.app.set_status("Let go to put the picture here. Esc: leave it where it was.")
        return "break"

    def _frelease(self, e):
        fp, self.fpress = self.fpress, None
        if fp and fp["moved"] and fp["name"] in self.ed.images:
            self.ed._mark_changed()
            self.ed.flow.reflow()
            self.select(fp["name"])
        return "break"

    # ------------------------------------------------------------ resizing
    def _resize_press(self, e, edge):
        info = self.ed.images.get(self.sel)
        if not info:
            return "break"
        img = nd.load_picture(info["rel"])
        natural = img.height / float(img.width)                  # the picture's own shape (height / width)
        img.thumbnail((1600, 1600))                               # (a smaller copy for the live preview)
        k = self.ed.img_scale()
        w0 = float(info["w"])
        h0 = float(info["h"]) if info.get("h") else w0 * natural    # (its own shape: exact, not from the screen)
        f = info.get("float")
        self.resize = {"edge": edge, "x": e.x_root, "y": e.y_root, "w0": w0, "h0": h0, "w": w0, "h": h0,
                       "natural": natural, "img": img, "undo": False,
                       "fx": f["x"] if f else 0, "top": info.get("_doc_top") or 0}
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
        if self._float():                # a floating picture grows from the side you drag (it moves to stay put)
            fx = r["fx"] + (r["w0"] - r["w"] if "l" in r["edge"] else 0)
            top = r["top"] + ((r["h0"] - r["h"]) * k if "t" in r["edge"] else 0)
            self.ed.flow.move_to(self.sel, fx, doc_top=top, width=r["w"], place=False)
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
        self.ed._show_photo(self.sel, photo)
        if info.get("float"):
            self.ed.flow.reflow()
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
