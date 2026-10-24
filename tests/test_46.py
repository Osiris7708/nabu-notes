import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, subprocess, traceback, datetime, json, shutil
H=tempfile.mkdtemp(); os.environ['NOBU_HOME']=H
import nobu_models; nobu_models.missing=lambda n: []
import nobu_audio, nobu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s,a,prompt=None): return []
nobu_transcribe.Detector=lambda c: D()
class E2(nobu_audio.Engine):
    def __init__(s,*a,**k): k['start_stream']=False; super().__init__(*a,**k)
nobu_audio.Engine=E2
import nobu_main as M, nobu_library as lib, nobu_doc as nd
from nobu_match import Word
app=M.App(); app._server=M._claim_instance()
def step(fn):
    ev=threading.Event(); r={}
    def go():
        try: r['v']=fn()
        except Exception as e: r['e']=repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(30); return r.get('v', r.get('e'))
def shot(n, w=1.0): _here.shot(n, w)
def W(s,t0=0.0,dt=0.3):
    out=[];t=t0
    for x in s.split(): out.append(Word(x,t,t+dt-0.05)); t+=dt
    return out
def go():
    try:
        time.sleep(2); step(lambda: app.root.geometry('1480x900+0+0'))
        book=lib.create_project('The Hollow Crown'); ch=lib.create_folder(book,'Characters'); sub=lib.create_folder(ch,'Villains')
        n1=lib.create_note(book,'Chapter One')
        step(app.refresh_library)
        # tree toggle zone: click left of the name on a closed folder
        def toggle():
            tv=app.tree; app._tree_open(book, True); tv.update(); bb=tv.bbox(ch)
            class E: pass
            e=E(); e.x=bb[0]+30; e.y=bb[1]+bb[3]//2; e.state=0
            before=tv.item(ch,'open'); r=app._tree_press(e); return before, tv.item(ch,'open'), r
        print('TOGGLE', step(toggle))
        # title sync inside -> outside
        step(lambda: app.open_note(n1)); ed=app.editor
        def edit_title():
            line,txt=ed.title_line(); t=ed.text
            t.delete(line, line+' lineend'); t.insert(line, 'The Burning Gate', ('st:title',)); ed._mark_changed(); ed._idle_work()
            return os.path.basename(ed.path)
        print('TITLE->NAME', step(edit_title), [os.path.basename(p) for p in lib.notes_in(book)])
        # outside -> inside
        def ren():
            T=M.T; orig=T.ask_string; T.ask_string=lambda *a,**k: 'Ashes and Gold'
            app.rename_note(ed.path); T.ask_string=orig; return os.path.basename(ed.path), ed.title_line()[1]
        print('NAME->TITLE', step(ren))
        # closed note rename -> title in file
        n2=lib.create_note(book,'Chapter Two'); step(app.refresh_library)
        def ren2():
            T=M.T; orig=T.ask_string; T.ask_string=lambda *a,**k: 'The Second Chapter'
            app.rename_note(n2); T.ask_string=orig
        step(ren2); p2=os.path.join(book,'The Second Chapter.nobu'); print('CLOSED RENAME', os.path.exists(p2), nd.load_doc(p2)['items'][0])
        # hotkeys (linux: bind_all) & hints
        print('HOTKEY hint', step(lambda: (app.rec_hint.cget('text'), ed._voice_hints['edit'][0].cget('text'))))
        # settings screenshot
        step(app.open_settings); step(lambda: app.settings_win.canvas.yview_moveto(0.42)); shot('46_settings')
        step(lambda: app.settings_win._capture_hotkey('record')); shot('46_capture',0.6)
        step(lambda: [w.destroy() for w in app.root.winfo_children() if isinstance(w, M.tk.Toplevel) and 'shortcut' in w.title().lower()])
        import nobu_ui
        step(lambda: setattr(app, '_te', nobu_ui.ThemeEditor(app.root, app, app.settings_win))); 
        step(lambda: app._te._start_from('forest')); shot('46_theme')
        step(lambda: app._te.win.destroy()); step(lambda: app.settings_win.cancel())
        # teach flow
        step(app.open_teach); tw=app.teach_win
        step(lambda: (setattr(tw,'stage','phrase'), setattr(tw,'idx',0), setattr(tw,'count',0), tw._show_phrase()))
        heard=[("Now group record this",)]*3+[("No boo and recordings",)]*3+[("No boo add it this",)]*2+[("Nobu cat this",)]*2
        for (h,) in heard: step(lambda h=h: tw.on_heard(h, [], 3000, W(h)))
        print('TEACH stage', tw.stage, tw.samples)
        for h in ["now group record this","nobu add it this","no boo and recordings","the cat sat"]:
            step(lambda h=h: tw.on_heard(h, [], 3000, W(h)))
        shot('46_teach')
        step(tw._finish); print('SAVED', app.cfg.get('phrase_samples'), app.cfg.get('wake_aliases'))
        step(tw.close)
        # add fonts
        import nobu_fonts as F
        src=os.path.join(_here.APP, 'fonts', 'lib') + os.sep + 'Rye-regular.ttf'
        print('ADD FONTS', F.add_user_fonts([src], install=False), [e['family'] for e in F.registry() if e['category']=='yours'])
    except Exception: traceback.print_exc()
    os._exit(0)
threading.Thread(target=go,daemon=True).start(); app.run()
