import _here  # finds the app and keeps the test away from your real notes
import sys, os, tempfile, threading, time, subprocess, datetime, traceback
H=tempfile.mkdtemp(); os.environ['NABU_HOME']=H
import nabu_models; nabu_models.missing=lambda n: []
import nabu_audio, nabu_transcribe
class D:
    def warm(s): pass
    def reload(s): pass
    def detect(s,a): return []
nabu_transcribe.Detector=lambda c: D()
class E2(nabu_audio.Engine):
    def __init__(s,*a,**k): k['start_stream']=False; super().__init__(*a,**k)
nabu_audio.Engine=E2
import nabu_main as M, nabu_config as C, nabu_library as lib, nabu_doc as nd, nabu_rich as R
app=M.App(); app._server=M._claim_instance()
print('FONTS', app.body_family, '|', app.heading_family, '|', app.ui_family)
def step(fn):
    ev=threading.Event(); r={}
    def go():
        try: r['v']=fn()
        except Exception as e: r['e']=repr(e); traceback.print_exc()
        finally: ev.set()
    app.ui(go); ev.wait(30); return r.get('v', r.get('e'))
def shot(n, w=1.0): _here.shot(n, w)
EXPORT = os.path.abspath('out')
def go():
    try:
        time.sleep(2)
        book=lib.create_project('The Hollow Crown')
        para = "Kaelith crept through the burnt orchard, counting the silent bells of the old abbey as the moon rose over Varnholt. "
        items=[{"t":"Chapter One\n","g":["st:h1"]},{"t":"The Ember Gate\n","g":["st:subtitle"]}]
        for k in range(14):
            items.append({"t": para*3 + "Teh wizzard waited.\n", "g":["fi:0.5"]})
        n1=lib.create_note(book,'Chapter One', items)
        step(app.refresh_library); step(lambda: app.open_note(n1)); time.sleep(1.5)
        shot('1_editor', 1.5)
        ed=app.editor
        print('PAGES', step(lambda: (len(ed.page_marks)+1, ed.page_lbl.cget('text'))))
        print('SPELL', step(lambda: [ed.text.get(*r) for r in zip(*[iter(ed.text.tag_ranges('sp_err'))]*2)][:6]))
        # formatting ops on first paragraph
        def fmt():
            t=ed.text
            t.tag_remove('sel','1.0','end'); t.tag_add('sel','3.0','3.7'); ed.toggle_flag('b')
            t.tag_remove('sel','1.0','end'); t.tag_add('sel','3.8','3.13'); ed.set_char('ff','Cinzel'); ed.set_char('fs',20)
            t.tag_remove('sel','1.0','end'); t.tag_add('sel','3.14','3.21'); ed.set_char('fg','#c00000'); ed.set_char('hl','#ffff00')
            t.tag_remove('sel','1.0','end'); t.mark_set('insert','4.0'); ed.toggle_list('bullet')
            t.mark_set('insert','5.0'); ed.toggle_list('num'); t.mark_set('insert','6.0'); ed.toggle_list('num')
            t.mark_set('insert','6.end'); ed.list_level(1)
            t.mark_set('insert','2.0'); ed.set_par('al','center')
            t.mark_set('insert','7.0'); ed.insert_page_break()
            return R.items_to_paras(ed.serialize()['items'])[:8]
        for p in step(fmt): print('  ', p.get('style'), p.get('align'), p.get('list'), [ {k:v for k,v in r.items() if k!='t'} for r in p.get('runs',[])][:4])
        step(lambda: ed.text.see('3.0')); shot('2_formatted')
        # table
        def table():
            ed.text.mark_set('insert','2.end'); ed._push_undo(); ed._insert_block('table',[['Name','Role','Home'],['Kaelith','Thief','Varnholt']])
            return [b.rows() for b in ed.blocks.values() if hasattr(b,'rows')]
        print('TABLE', step(table)); step(lambda: ed.text.see('1.0')); shot('3_table')
        # typing with pending format
        def typing():
            t=ed.text; t.mark_set('insert','2.end')
            class Ev: pass
            ed.toggle_flag('i')
            for ch in ' (draft)':
                e=Ev(); e.char=ch; e.state=0; ed._on_key(e)
            return t.get('2.0','2.end'), t.tag_names('2.end-2c')
        print('TYPED', step(typing))
        print('UNDO', step(lambda: (ed.undo(), ed.text.get('2.0','2.end'))[1]))
        print('REDO', step(lambda: (ed.redo(), ed.text.get('2.0','2.end'))[1]))
        step(ed.save)
        # reload from disk and compare
        a=step(lambda: ed.serialize()['items']); step(lambda: app.open_note(n1)); b=step(lambda: ed.serialize()['items'])
        print('RELOAD SAME', a==b, len(a), len(b))
        if a!=b:
            for x,y in zip(a,b):
                if x!=y: print('  DIFF', x, y); break
        # zoom
        step(lambda: ed.set_zoom('75%')); shot('4_zoom75'); step(lambda: ed.set_zoom('Fit width'))
        step(lambda: ed.goto_page(2)); shot('5_page2')
        # thesaurus + spell menu (post menus would block; call fill functions)
        app.thesaurus.ensure(); time.sleep(4)
        def syn():
            import nabu_theme as T
            m=T.menu(app.root); ed._fill_synonyms(m,'silent','1.0','1.1'); return [m.entrycget(i,'label') for i in range(min(8,m.index('end')+1))]
        print('SYN', step(syn))
        print('SUGG', app.speller.suggestions('wizzard'), app.speller.suggestions('Teh'))
        # export dialog screenshot, font browser screenshot
        step(lambda: app.export_dialog([n1])); shot('6_export'); step(lambda: app.root.focus_get() and [w.destroy() for w in app.root.winfo_children() if str(w).startswith('.!toplevel')])
        step(app.open_font_browser); step(lambda: app.font_win._pick('Cinzel Decorative')); shot('7_fonts'); step(lambda: app.font_win.win.destroy())
        # export all formats via module
        import nabu_export as E
        ctx=R.Ctx(app.body_family, app.heading_family, 14)
        for f in ('docx','pdf','epub','html','txt'):
            print('EXPORT', f, os.path.getsize(E.export([n1], f, os.path.join(EXPORT,'gui.'+f), ctx, {})))
        # import the docx we made
        import nabu_importers as I
        p=step(lambda: I.import_file(os.path.join(EXPORT,'gui.docx'), book, True, ctx))
        step(lambda: app.open_note(p)); step(lambda: ed.text.see('1.0')); shot('8_imported')
        step(lambda: app.show_project(book)); shot('9_project')
        step(app.show_home); shot('10_home')
    except Exception:
        traceback.print_exc()
    os._exit(0)
threading.Thread(target=go,daemon=True).start(); app.run()
