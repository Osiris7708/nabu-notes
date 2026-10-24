import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, subprocess, traceback, datetime, json
H=tempfile.mkdtemp(); os.environ['NOBU_HOME']=H
json.dump({"config_version":2,"custom_vocabulary":"Kryptik, Varnholt\nMoraine"}, open(H+'/config.json','w'))
import nobu_models; nobu_models.missing=lambda n: []
import nobu_audio, nobu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s,a): return []
nobu_transcribe.Detector=lambda c: D()
class E2(nobu_audio.Engine):
    def __init__(s,*a,**k): k['start_stream']=False; super().__init__(*a,**k)
nobu_audio.Engine=E2
import nobu_main as M, nobu_library as lib, nobu_dictionary
app=M.App(); app._server=M._claim_instance()
print('DICT', [e['word'] for e in nobu_dictionary.load()], repr(app.cfg.get('custom_vocabulary')))
def step(fn):
    ev=threading.Event(); r={}
    def go():
        try: r['v']=fn()
        except Exception as e: r['e']=repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(30); return r.get('v', r.get('e'))
def shot(n, w=1.0): _here.shot(n, w)
class Ev: pass
def drag(src_w, iid, dst_w, dst_iid, frac, shoot=None):
    def pos(w, i, f):
        bb=w.bbox(i); return w.winfo_rootx()+bb[0]+30, w.winfo_rooty()+bb[1]+int(bb[3]*f)
    def go():
        dd=app.dragdrop
        x,y=pos(src_w,iid,0.5); e=Ev(); e.x_root,e.y_root=x,y; e.x=x-src_w.winfo_rootx(); e.y=y-src_w.winfo_rooty()
        dd._press(e, src_w)
        x2,y2=pos(dst_w,dst_iid,frac)
        for k in range(1,6):
            e=Ev(); e.x_root=x+(x2-x)*k//5; e.y_root=y+(y2-y)*k//5; dd._motion(e, src_w)
        return (x2,y2)
    x2,y2=step(go)
    if shoot: shot(shoot,0.6)
    def rel():
        e=Ev(); e.x_root,e.y_root=x2,y2; app.dragdrop._release(e, src_w)
    step(rel); time.sleep(0.6)
def tree():
    out=[]
    def walk(i,d):
        for c in app.tree.get_children(i): out.append('  '*d+app.tree.item(c,'text').strip()); walk(c,d+1)
    walk('',0); return out
def go():
    try:
        time.sleep(2)
        A=lib.create_project('Alpha Book'); B=lib.create_project('Beta Campaign'); C=lib.create_project('Gamma Saga')
        chars=lib.create_folder(A,'Characters'); locs=lib.create_folder(A,'Locations')
        n1=lib.create_note(A,'Note one'); n2=lib.create_note(A,'Note two')
        ib=lib.make_inbox_note(datetime.datetime.now(), H+'/Recordings/x.wav', ['A loose idea.'])
        step(app.refresh_library); step(lambda: [app.tree.item(i, open=True) for i in (A,)])
        T=app.tree
        # Gamma above Alpha
        drag(T, C, T, A, 0.1, '44_line'); print('1', [os.path.basename(p) for p in lib.projects()])
        # Locations into Characters
        drag(T, locs, T, chars, 0.5, '44_into'); print('2', [os.path.relpath(p,H) for p in lib.subfolders(chars)])
        # Characters/Locations out to top level, below Beta
        locs2=os.path.join(chars,'Locations'); step(lambda: app.tree.item(chars, open=True)); step(app.refresh_library)
        drag(T, locs2, T, B, 0.9); print('3', [os.path.basename(p) for p in lib.projects()])
        # note two above note one
        drag(T, n2, T, n1, 0.2); print('4', [os.path.basename(p) for p in lib.notes_in(A)])
        # inbox note from Unassigned list into Beta
        step(app.show_inbox); drag(app.inbox._tv, ib, T, B, 0.5); print('5', [os.path.basename(p) for p in lib.notes_in(B)])
        # note back to unassigned via nav
        nb=lib.notes_in(B)[0]; step(lambda: app.tree.item(B, open=True)); step(app.refresh_library)
        drag(T, nb, app.nav, 'inbox', 0.5); print('6 inbox', len(lib.notes_in(M.C.INBOX_DIR)))
        print('\n'.join(step(tree)))
        step(app.show_home); step(app.open_tutorial); shot('44_tutorial')
        step(lambda: (app.tutorial_win.toc.selection_set('sec6'))); shot('44_tutorial2', 0.6)
    except Exception: traceback.print_exc()
    os._exit(0)
threading.Thread(target=go,daemon=True).start(); app.run()
