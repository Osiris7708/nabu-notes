import _here  # finds the app and keeps the test away from your real notes
import os, sys, shutil, json, tempfile
H = tempfile.mkdtemp(); os.makedirs(H + "/Images")
os.environ["NOBU_HOME"] = H
from PIL import Image
Image.new("RGB", (300, 150), (200, 60, 60)).save(H + "/Images/red.png")
import nobu_rich as R, nobu_export as E, nobu_importers as I, nobu_doc as nd, nobu_library as lib
items = [
 {"t": "The Ashen Crown\n", "g": ["st:title"]},
 {"t": "Book one\n", "g": ["st:subtitle"]},
 {"t": "Chapter 1\n", "g": ["st:h1"]},
 {"t": "Kaelith walked ", "g": ["fi:0.5"]}, {"t": "slowly", "g": ["fi:0.5", "i"]}, {"t": " into the ", "g": ["fi:0.5"]},
 {"t": "burning", "g": ["fi:0.5", "b", "fg:#c00000"]}, {"t": " hall, H", "g": ["fi:0.5"]}, {"t": "2", "g": ["fi:0.5", "sub"]},
 {"t": "O and ", "g": ["fi:0.5"]}, {"t": "ᚠᚢᚦ runes", "g": ["fi:0.5", "hl:#ffff00"]}, {"t": " in Cinzel.", "g": ["fi:0.5", "ff:Cinzel", "fs:18"]},
 {"t": "\n", "g": ["fi:0.5"]},
 {"t": "•\t", "g": ["li:bullet:0", "lm"]}, {"t": "first point\n", "g": ["li:bullet:0"]},
 {"t": "•\t", "g": ["li:bullet:1", "lm"]}, {"t": "nested\n", "g": ["li:bullet:1"]},
 {"t": "1.\t", "g": ["li:num:0", "lm"]}, {"t": "step one\n", "g": ["li:num:0"]},
 {"t": "2.\t", "g": ["li:num:0", "lm"]}, {"t": "step two\n", "g": ["li:num:0"]},
 {"t": "Centred line\n", "g": ["al:center"]},
 {"i": "Images/red.png", "w": 200, "g": ["al:center"]}, {"t": "\n", "g": ["al:center"]},
 {"table": {"rows": [["Name", "Role"], ["Kaelith", "Thief"]]}, "g": []}, {"t": "\n", "g": []},
 {"pb": 1, "g": []}, {"t": "\n", "g": []},
 {"t": "Chapter 2\n", "g": ["st:h1"]},
 {"t": "A quote here.\n", "g": ["st:quote"]},
 {"t": "Jan 1  ", "g": ["meta"]}, {"t": "▶ Play recording", "g": ["meta", "audio|Recordings/x.wav"]}, {"t": "\n", "g": []},
]
paras = R.items_to_paras(items)
print([ (p["type"], p.get("style"), p.get("list")) for p in paras])
os.makedirs(H + "/Notes/Book", exist_ok=True)
note = H + "/Notes/Book/Ch1.nobu"
d = nd.empty_doc(); d["items"] = items; nd.save_doc(note, d)
ctx = R.Ctx("IM FELL English", "Cinzel", 14)
os.makedirs("out", exist_ok=True)
for fmt in ("docx", "pdf", "epub", "html", "txt"):
    p = E.export([note], fmt, "out/test." + fmt, ctx, {})
    print(fmt, os.path.getsize(p))
# re-import docx
pi = I.import_file("out/test.docx", H + "/Notes/Book", ctx=ctx)
back = R.items_to_paras(nd.load_doc(pi)["items"])
for p in back:
    print(p["type"], p.get("style"), p.get("align"), p.get("list"), p.get("fi"), [ {k:v for k,v in r.items()} for r in p.get("runs", [])][:6] if p["type"]=="p" else p.get("rows"))
for f in ("html", "md"):
    pass
