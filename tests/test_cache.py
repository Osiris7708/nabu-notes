import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile
H=tempfile.mkdtemp(); os.environ['NOBU_HOME']=H
import tkinter as tk, nobu_theme as T, nobu_rich as R, nobu_doc as nd, nobu_library as lib, nobu_spell
root=tk.Tk(); T.apply(root,'Eagle Lake')
class Cfg(dict):
    def get(s,k,d=None): return dict.get(s,k,d)
    def set_temp(s,**k): pass
class App:
    body_family='IM FELL English'; heading_family='Eagle Lake'; clip_items=None
    speller=nobu_spell.Speller()
    def set_status(s,m): pass
    def __getattr__(s,n): return lambda *a,**k: None
import nobu_editor as NE
app=App(); ed=NE.NoteEditor(root, app, Cfg(font_size=12, zoom='100%')); ed.frame.pack(fill='both',expand=True)
p=lib.create_note(H+'/Notes/B','T',[{"t":"Hello world\n","g":[]}]); ed.load(p); root.update()
txt=lambda: "".join(i.get("t","") for i in ed.serialize()["items"])
ed.serialize(); a=txt()
ed.text.insert("1.0","X")            ; print('direct insert seen', txt().startswith("XHello"))
ed.text.focus_force(); root.update(); ed.text.mark_set('insert','1.end')
ed.text.event_generate('<BackSpace>'); root.update(); print('class BackSpace seen', 'worl\n' in txt() or txt().startswith('XHello worl'), repr(txt()[:14]))
ed.text.tag_add('sel','1.0','1.3'); ed.toggle_flag('b'); print('bold seen', any('b' in i['g'] for i in ed.serialize()['items']))
ed.text.mark_set('insert','end-1c'); ed._insert_block('table',[['a','b']]); root.update()
blk=[b for b in ed.blocks.values() if hasattr(b,'rows')][0]; blk.cells[0][0].insert('1.0','CELL'); root.update()
print('table cell seen', any('table' in i and i['table']['rows'][0][0].startswith('CELL') for i in ed.serialize()['items']))
ed.save(); d=nd.load_doc(p); print('saved ok', "".join(i.get('t','') for i in d['items'])[:12])
