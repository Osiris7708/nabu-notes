import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile
H=tempfile.mkdtemp(); os.environ['NOBU_HOME']=H
import tkinter as tk, nobu_theme as T, nobu_rich as R, nobu_doc as nd, nobu_library as lib
root=tk.Tk(); T.apply(root,'Varnyx')
class Cfg(dict):
    def get(s,k,d=None): return dict.get(s,k,d)
    def set_temp(s,**k): pass
import nobu_spell
class App:
    body_family='IM FELL English'; heading_family='Varnyx'; clip_items=None
    speller=nobu_spell.Speller()
    def set_status(s,m): print('STATUS',m)
    def __getattr__(s,n): return lambda *a,**k: None
import nobu_editor as NE
app=App(); ed=NE.NoteEditor(root, app, Cfg(font_size=14, zoom='100%'))
ed.frame.pack(fill='both',expand=True)
p=lib.create_note(H+'/Notes/B','T',[{"t":"Hello world. The quick brown fox jumps over the lazy dog.\n","g":[]}])
ed.load(p); root.update()
t=ed.text
class Ev: pass
def key(ch):
    e=Ev(); e.char=ch; e.state=0
    if ch=='\n': ed._on_return(e)
    else: ed._on_key(e)
# list typing
t.mark_set('insert','end-1c'); ed.toggle_list('bullet')
for ch in 'alpha\nbeta\n': key(ch)
e=Ev(); ed._on_tab(e)
for ch in 'nested\n\n': key(ch)  # Enter twice: end list? first Enter creates nested item, second ends
for ch in 'after list': key(ch)
print(repr(t.get('1.0','end-1c')))
print([ (p['list'], ''.join(r.get('t','') for r in p['runs'])) for p in R.items_to_paras(ed.serialize()['items'])])
# numbered then renumber
t.mark_set('insert','2.0'); ed.toggle_list('num'); print(repr(t.get('2.0','5.0')))
# dictation
t.mark_set('insert','1.5'); ed.begin_dictation(); ed.insert_dictation(p, ['brave new']); print(repr(t.get('1.0','1.end')))
# cut by voice
ed.propose_cut(p, 'the quick brown fox'); print('CUTMATCH', t.get(*t.tag_ranges('cutmatch')))
ed._do_cut(); print(repr(t.get('1.0','1.end')))
ed.undo(); print('UNDO', repr(t.get('1.0','1.end')))
# copy/paste internal
t.tag_add('sel','1.0','1.5'); ed.toggle_flag('b'); ed.copy(); t.tag_remove('sel','1.0','end'); t.mark_set('insert','1.end'); ed.paste()
print('PASTE', repr(t.get('1.0','1.end')), t.tag_names('1.end-2c'))
# html paste via html_to_paras
import nobu_clip; nobu_clip.get_html=lambda: '<p><b>Bold</b> and <i style="color:#ff0000">red italic</i></p><ul><li>one</li><li>two</li></ul>'
app.clip_items=None; root.clipboard_clear(); root.clipboard_append('Bold and red italic\none\ntwo')
t.mark_set('insert','end-1c'); ed.paste()
print([ (p['list'], [(r.get('t'),r.get('b'),r.get('i'),r.get('fg')) for r in p['runs']]) for p in R.items_to_paras(ed.serialize()['items'])][-4:])
# backspace at list marker removes list
ln = [i for i in range(1,30) if 'li:bullet:0' in t.tag_names('%d.0'%i)]
t.mark_set('insert','%d.2'%ln[-1]); e=Ev(); print('BS', ed._on_backspace(e), repr(t.get('%d.0'%ln[-1],'%d.end'%ln[-1])))
ed.save(); print('saved items', len(nd.load_doc(p)['items']))
# find_replace replace_all via direct
print('WORDS', ed.words_lbl.cget('text'))
