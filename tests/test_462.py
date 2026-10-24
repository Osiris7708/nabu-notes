import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, traceback, json
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
import nobu_main as M, nobu_config as C, nobu_hotkeys as HK
# --- Windows key states: 0x8 = Num Lock, 0x20000 = Alt, 0x4 Ctrl, 0x1 Shift
class Ev:
    def __init__(s,k,st): s.keysym=k; s.state=st
HK.IS_WIN=True
for k,st in [('F9',0x8),('r',0x8),('r',0x8|0x20000),('r',0x4|0x8),('exclam',0x1|0x8),('Escape',0x8),('Escape',0x4),('Up',0),('KP_End',0x8)]:
    c=HK.combo_from_event(Ev(k,st)); print('WIN', k, hex(st), '->', c, HK.valid(c)[:1], 'warn' if HK.valid(c)[2] else '', HK.to_win(c))
HK.IS_WIN=False
app=M.App(); app._server=M._claim_instance()
def step(fn):
    ev=threading.Event(); r={}
    def go():
        try: r['v']=fn()
        except Exception as e: r['e']=repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(30); return r.get('v', r.get('e'))
def cap():
    return [x for x in app.settings_win.win.winfo_children() if isinstance(x, M.tk.Toplevel) and 'shortcut' in x.title().lower()]
def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)
def go():
    try:
        time.sleep(2)
        step(app.open_settings); st=app.settings_win
        # single plain key F9 -> accepted immediately
        step(lambda: st._capture_hotkey('record'))
        step(lambda: (cap()[0].focus_force(), cap()[0].event_generate('<KeyPress-F9>'))); time.sleep(1)
        print('F9 saved:', json.load(open(C.CONFIG_PATH)).get('hotkey_record'))
        # letter q -> warning, then "Use it anyway"
        step(lambda: st._capture_hotkey('edit'))
        step(lambda: (cap()[0].focus_force(), cap()[0].event_generate('<KeyPress-q>'))); time.sleep(0.4)
        msgs=step(lambda: [x.cget('text') for x in walk(cap()[0]) if isinstance(x, M.ttk.Label)])
        print('Q dialog:', msgs)
        step(lambda: [x.invoke() for x in walk(cap()[0]) if isinstance(x, M.ttk.Button) and x.cget('text')=='Use it anyway']); time.sleep(1)
        print('Q saved:', json.load(open(C.CONFIG_PATH)).get('hotkey_edit'))
        # Escape alone cancels; Return alone refused
        step(lambda: st._capture_hotkey('cut'))
        step(lambda: (cap()[0].focus_force(), cap()[0].event_generate('<KeyPress-Return>'))); time.sleep(0.4)
        print('Return dialog:', step(lambda: [x.cget('text') for x in walk(cap()[0]) if isinstance(x, M.ttk.Label)]))
        step(lambda: (cap()[0].focus_force(), cap()[0].event_generate('<KeyPress-Escape>'))); time.sleep(0.6)
        print('open after Esc:', step(lambda: len(cap())), 'cut =', app.cfg.get('hotkey_cut'))
        print('HINTS', step(lambda: app.rec_hint.cget('text')))
        step(lambda: st.cancel())
        print('AFTER RESTART', {k: C.Config().get('hotkey_'+k) for k in ('record','edit','cut')})
    except Exception: traceback.print_exc()
    os._exit(0)
threading.Thread(target=go,daemon=True).start(); app.run()
