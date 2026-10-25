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

# ---------------------------------------------------------------- web links (v4.9.2)
import zipfile
def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra, flush=True)
    assert cond, name
ok("find_urls: addresses in a sentence, without the full stop / comma / bracket after them",
   [u for _s, _e, u in R.find_urls("See https://example.com/a, (www.nobu.test) and https://x.org/wiki/A_(b).")]
   == ["https://example.com/a", "https://www.nobu.test", "https://x.org/wiki/A_(b)"],
   R.find_urls("See https://example.com/a, (www.nobu.test) and https://x.org/wiki/A_(b)."))
ok("find_urls: ordinary words are not links", R.find_urls("version 4.9 is out, e.g. today") == [])
ok("clean_url makes addresses safe to store", R.clean_url('https://a.org/x y"{}') == "https://a.org/x%20y%22%7B%7D")
hp = R.html_to_paras('<p>Read <a href="https://example.org/guide">the guide</a> now. <a href="#top">Top</a></p>')
hr = [r for p in hp for r in p["runs"]]
ok("pasted web text keeps its links (page anchors are left out)",
   [(r["t"], r.get("link")) for r in hr] == [("Read ", None), ("the guide", "https://example.org/guide"), (" now. Top", None)],
   hr)
mp = R.markdown_to_paras("Go to [the site](https://example.org/md) today")
ok("Markdown links", any(r.get("link") == "https://example.org/md" and r["t"] == "the site" for p in mp for r in p["runs"]))
link_items = [{"t": "Read ", "g": []}, {"t": "the guide", "g": ["link:https://example.org/guide"]},
              {"t": " or ", "g": []}, {"t": "https://example.org/raw", "g": ["link:https://example.org/raw"]},
              {"t": ".\n", "g": []}]
ok("links survive the note format", R.paras_to_items(R.items_to_paras(link_items))[1]["g"] == ["link:https://example.org/guide"])
lnote = H + "/Notes/Book/Links.nobu"
d = nd.empty_doc(); d["items"] = link_items; nd.save_doc(lnote, d)
for fmt in ("docx", "pdf", "epub", "html", "txt"):
    E.export([lnote], fmt, "out/links." + fmt, ctx, {})
with zipfile.ZipFile("out/links.docx") as z:
    doc_xml = z.read("word/document.xml").decode("utf-8")
    rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
ok("Word: the link is a real hyperlink", doc_xml.count("<w:hyperlink") == 2 and "https://example.org/guide" in rels, doc_xml[:400])
pdf = open("out/links.pdf", "rb").read()
ok("PDF: the link can be clicked", pdf.count(b"/URI") >= 2 and b"https://example.org/guide" in pdf)
html_out = open("out/links.html", encoding="utf-8").read()
ok("web page: <a href>", '<a href="https://example.org/guide">' in html_out)
with zipfile.ZipFile("out/links.epub") as z:
    ch = z.read("OEBPS/chapter1.xhtml").decode("utf-8")
ok("e-book: <a href>", 'href="https://example.org/guide"' in ch)
txt = open("out/links.txt", encoding="utf-8-sig").read()
ok("text file: the address is written after link words", "the guide (https://example.org/guide)" in txt
   and "https://example.org/raw (" not in txt, txt)
rtf = R.to_rtf(R.items_to_paras(link_items), ctx)
ok("copy to Word (RTF): hyperlink field", 'HYPERLINK "https://example.org/guide"' in rtf)
back = nd.load_doc(I.import_file("out/links.docx", H + "/Notes/Book", ctx=ctx))["items"]
ok("importing a Word file keeps its links", any("link:https://example.org/guide" in it.get("g", []) and it.get("t") == "the guide"
                                               for it in back), back)
print("links: all checks passed")

# ---------------------------------------------------------------- stretched pictures (v4.9.3)
st_items = [{"i": "Images/red.png", "w": 300, "h": 60, "g": []}, {"t": "\n", "g": []},
            {"i": "Images/red.png", "w": 300, "g": []}, {"t": "\n", "g": []}]
ok("a stretched picture keeps its height in the note format",
   [it.get("h") for it in R.paras_to_items(R.items_to_paras(st_items)) if "i" in it] == [60, None])
ok("export size: stretched keeps its height, unstretched keeps its shape",
   E.image_size_in("Images/red.png", 300, 60) == (300 / 96.0, 60 / 96.0)
   and E.image_size_in("Images/red.png", 300) == (300 / 96.0, 150 / 96.0))
w_, h_ = E.image_size_in("Images/red.png", 1200, 300)
ok("...and a too-wide stretched picture shrinks evenly to the page", abs(w_ - E.TEXT_W_IN) < 1e-6 and abs(h_ - 300 / 96.0 * E.TEXT_W_IN / 12.5) < 1e-6)
ok("pasted web pictures with a different shape stay stretched",
   [r.get("h") for p in R.html_to_paras('<img src="x" width="300" height="60"><img src="y" width="300" height="150">',
                                         image_cb=lambda s: "Images/red.png") for r in p["runs"]] == [60, None])
snote = H + "/Notes/Book/Stretch.nobu"
d = nd.empty_doc(); d["items"] = st_items; nd.save_doc(snote, d)
for fmt in ("docx", "html", "pdf"):
    E.export([snote], fmt, "out/stretch." + fmt, ctx, {})
with zipfile.ZipFile("out/stretch.docx") as z:
    ext = [tuple(int(v) for v in m) for m in __import__("re").findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', z.read("word/document.xml").decode())]
ok("Word: the stretched picture is 300 x 60, the other 300 x 150", [(round(cx / 9525), round(cy / 9525)) for cx, cy in ext] == [(300, 60), (300, 150)], ext)
ok("web page: width and height", "width:300px;height:60px" in open("out/stretch.html", encoding="utf-8").read())
print("stretched pictures: all checks passed")

# ---------------------------------------------------------------- pictures placed anywhere on the page (v4.9.3)
import re as _re
fl_para = "The ember-light crept across the old stones of the keep, and Kaelith counted the steps twice. " * 4
fl_items = [{"i": "Images/red.png", "w": 200, "float": {"wrap": "square", "text": "right", "x": 0, "y": 10}, "g": []},
            {"t": fl_para + "\n", "g": []}, {"t": fl_para + "\n", "g": []},
            {"i": "Images/red.png", "w": 200, "h": 60, "float": {"wrap": "square", "text": "largest", "x": 400, "y": 0}, "g": []},
            {"t": fl_para + "\n", "g": []},
            {"i": "Images/red.png", "w": 300, "float": {"wrap": "topbottom", "text": "largest", "x": 160, "y": 0}, "g": []},
            {"t": fl_para + "\n", "g": []},
            {"i": "Images/red.png", "w": 120, "float": {"wrap": "front", "text": "largest", "x": 250, "y": 20}, "g": []},
            {"t": fl_para + "\n", "g": []}]
ok("floating pictures keep their wrapping and place in the note format",
   [it.get("float") for it in R.paras_to_items(R.items_to_paras(fl_items)) if "i" in it] == [it["float"] for it in fl_items if "i" in it])
ok("side for flowing layouts: text on the right -> picture on the left; more room decides 'largest'",
   [R.float_side(it["float"], it["w"]) for it in fl_items if "i" in it] == ["left", "right", None, None])
fnote = H + "/Notes/Book/Float.nobu"
d = nd.empty_doc(); d["items"] = fl_items; nd.save_doc(fnote, d)
for fmt in ("docx", "pdf", "epub", "html", "txt"):
    E.export([fnote], fmt, "out/float." + fmt, ctx, {})
with zipfile.ZipFile("out/float.docx") as z:
    fx = z.read("word/document.xml").decode("utf-8")
ok("Word: real floating pictures with Word's own text wrapping",
   fx.count("<wp:anchor") == 4 and "<wp:inline" not in fx
   and _re.findall(r"<wp:(wrap\w+)", fx) == ["wrapSquare", "wrapSquare", "wrapTopAndBottom", "wrapNone"]
   and _re.findall(r'wrapText="(\w+)"', fx) == ["right", "largest"], _re.findall(r"<wp:wrap[^>]*>", fx))
ok("Word: placed where they were (from the left of the text, down from the paragraph)",
   _re.findall(r"<wp:posOffset>(\d+)</wp:posOffset>", fx)[:4] == [str(0), str(95250), str(3810000), str(0)],
   _re.findall(r"<wp:posOffset>(\d+)</wp:posOffset>", fx))
import docx as _docx
_docx.Document("out/float.docx")
fh = open("out/float.html", encoding="utf-8").read()
ok("web page / e-book: pictures float left or right with the text flowing past",
   _re.findall(r"(float:\w+|display:block;clear:both)", fh) == ["float:left", "float:right", "display:block;clear:both",
                                                                "display:block;clear:both"])
ok("PDF: made, with all 4 pictures", open("out/float.pdf", "rb").read().count(b"/Subtype /Image") >= 1)
back = nd.load_doc(I.import_file("out/float.docx", H + "/Notes/Book", ctx=ctx))["items"]
ok("importing that Word file brings all 4 pictures back", sum(1 for it in back if "i" in it) == 4)
print("floating pictures: all checks passed")

# ---------------------------------------------------------------- the app icon (tools\set_icon.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(R.__file__))), "tools"))
import set_icon
from PIL import ImageDraw
src = Image.new("RGB", (600, 600), (0, 0, 0))                     # a rounded square on a black border
ImageDraw.Draw(src).rounded_rectangle((50, 50, 549, 549), radius=90, fill=(20, 24, 60))
src.save("out/icon_src.png")
art = set_icon.cut_out("out/icon_src.png")
ok("icon: the black border is cut away (square, corners see-through, middle solid)",
   art.size[0] == art.size[1] and abs(art.size[0] - 500) <= 4 and art.getpixel((0, 0))[3] == 0
   and art.getpixel((art.width // 2, art.height // 2))[3] == 255, art.size)
sizes = [s for s, _png in set_icon.write_ico(art, "out/test.ico")]
ok("icon: the .ico has every size Windows uses", sizes == [16, 24, 32, 48, 64, 128, 256])
ok("icon: Nobu's own icon is 256 x 256 with see-through corners",
   Image.open(os.path.join(os.path.dirname(os.path.abspath(R.__file__)), "nobu_icon.png")).getpixel((0, 0))[3] == 0)
print("icon: all checks passed")
