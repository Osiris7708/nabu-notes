import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, time
os.environ['NABU_HOME'] = tempfile.mkdtemp()
import tkinter as tk, nabu_theme as T
r = tk.Tk(); T.set_theme("dark"); T.apply(r, "TkDefaultFont"); r.geometry("200x200+0+0")
import nabu_help as h
w = h.TutorialWindow(r); w.win.geometry("1100x760+0+0"); r.update(); time.sleep(0.5); r.update()
_here.shot("tut1")
w.toc.selection_set("sec5"); r.update(); time.sleep(0.3); r.update(); _here.shot("tut2")
print("ok")
