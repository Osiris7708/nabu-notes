import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, subprocess, traceback, json, zipfile, shutil
H=tempfile.mkdtemp(); os.environ['NABU_HOME']=H
import nabu_models; nabu_models.missing=lambda n: []
import nabu_audio, nabu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s,a,prompt=None): return []
nabu_transcribe.Detector=lambda c: D()
class E2(nabu_audio.Engine):
    def __init__(s,*a,**k): k['start_stream']=False; super().__init__(*a,**k)
nabu_audio.Engine=E2
import nabu_main as M, nabu_fonts as F, nabu_config as C
app=M.App(); app._server=M._claim_instance()
def step(fn):
    ev=threading.Event(); r={}
    def go():
        try: r['v']=fn()
        except Exception as e: r['e']=repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(30); return r.get('v', r.get('e'))
def go():
    try:
        time.sleep(2)
        # fonts: zip with font + __MACOSX junk, import twice (second time = already there)
        src=os.path.join(_here.APP, 'fonts', 'lib') + os.sep + ''
        z=os.path.join(H,'kings.zip')
        with zipfile.ZipFile(z,'w') as zz:
            zz.write(src+'Kings-regular.ttf','Kings/Kings-regular.ttf'); zz.writestr('__MACOSX/Kings/._Kings-regular.ttf','junk')
        print('ADD1', F.add_user_fonts([z], install=False))
        print('ADD2', F.add_user_fonts([z], install=False))
        os.chmod(os.path.join(F.USER_FONTS,'Kings-regular.ttf'), 0o444)   # like a locked/in-use font
        print('ADD3', F.add_user_fonts([src+'Kings-regular.ttf'], install=False))
        print('personal?', F.licence_blocks_embedding('Ethereal Nymeria Personal Use'), F.licence_blocks_embedding('Kings'))
        # hotkey capture -> saved immediately, survives reload
        step(app.open_settings); st=app.settings_win
        step(lambda: st._capture_hotkey('record'))
        def press():
            w=[x for x in st.win.winfo_children() if isinstance(x, M.tk.Toplevel) and 'shortcut' in x.title().lower()][0]
            class E: pass
            e=E(); e.keysym='F9'; e.state=0
            for seq in w.bind(): pass
            # call the bound handler via event_generate
            w.focus_force(); w.event_generate('<KeyPress-F9>')
        step(press); time.sleep(1)
        print('CFG now', app.cfg.get('hotkey_record'), json.load(open(C.CONFIG_PATH)).get('hotkey_record'))
        print('HINT', step(lambda: app.rec_hint.cget('text')))
        step(lambda: st.cancel())
        cfg2=C.Config(); print('AFTER RESTART', cfg2.get('hotkey_record'))
    except Exception: traceback.print_exc()
    os._exit(0)
threading.Thread(target=go,daemon=True).start(); app.run()
