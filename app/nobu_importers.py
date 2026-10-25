"""Import documents from outside Nobu into a folder as notes, keeping their formatting and pictures.

Word (.docx), OpenDocument (.odt), PDF (text), web pages (.html/.htm), Markdown (.md), rich text (.rtf),
plain text (.txt) and Nobu notes (.nobu)."""
import base64
import io
import logging
import os
import re
import shutil
import urllib.parse
import zipfile

import nobu_doc as nd
import nobu_library as lib
import nobu_rich as R
from nobu_config import IMAGES_DIR, rel_to_home

log = logging.getLogger("nobu.import")

EXTS = (".docx", ".odt", ".pdf", ".html", ".htm", ".md", ".markdown", ".rtf", ".txt", ".text", ".nobu")
FILETYPES = [("Documents", " ".join("*" + e for e in EXTS)), ("Word", "*.docx"), ("PDF", "*.pdf"),
             ("Text", "*.txt *.md *.rtf"), ("All files", "*.*")]


# ---------------------------------------------------------------- pictures
def _save_image_bytes(data, note_path, name="image", ext=".png"):
    stem = os.path.splitext(os.path.basename(note_path or "Imported"))[0]
    folder = os.path.join(IMAGES_DIR, stem)
    os.makedirs(folder, exist_ok=True)
    ext = ext.lower() if ext.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff") else None
    if ext is None or ext in (".tif", ".tiff", ".bmp"):
        try:      # convert odd formats (emf/wmf can't be converted; skipped by caller) to PNG
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            data, ext = buf.getvalue(), ".png"
        except Exception:
            return None
    base = re.sub(r"[^\w-]+", "_", name)[:40] or "image"
    dest = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(folder, "%s_%d%s" % (base, n, ext))
        n += 1
    with open(dest, "wb") as f:
        f.write(data)
    return rel_to_home(dest)


def _img_width_css(data, emu_width=None):
    if emu_width:
        return max(20, int(round(emu_width / 914400.0 * 96)))
    try:
        from PIL import Image
        return min(Image.open(io.BytesIO(data)).size[0], R.TEXT_W_PX)
    except Exception:
        return 400


def fetch_image(src, note_path, base_dir=None):
    """An image referenced from HTML/Markdown (data: URI, file path or file:// URL). Returns a rel path."""
    if not src:
        return None
    try:
        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            m = re.search(r"image/(\w+)", head)
            ext = "." + (m.group(1) if m else "png").replace("jpeg", "jpg")
            return _save_image_bytes(base64.b64decode(b64), note_path, "pasted", ext)
        if src.startswith(("http://", "https://")):
            return None     # Nobu stays offline
        p = src
        if p.startswith("file:"):
            p = urllib.parse.unquote(urllib.parse.urlparse(p).path)
            if re.match(r"^/[A-Za-z]:", p):
                p = p[1:]
        else:
            p = urllib.parse.unquote(p)
        if base_dir and not os.path.isabs(p):
            p = os.path.join(base_dir, p)
        if os.path.isfile(p):
            return nd.import_image(p, note_path)
    except Exception:
        log.exception("image %s", src[:80])
    return None


# ---------------------------------------------------------------- Word .docx
_STYLE_MAP = {"title": "title", "subtitle": "subtitle", "heading 1": "h1", "heading 2": "h2", "heading 3": "h3",
              "heading 4": "h3", "heading 5": "h3", "heading 6": "h3", "quote": "quote", "intense quote": "quote"}
_HL = {"YELLOW": "#ffff00", "BRIGHT_GREEN": "#00ff00", "TURQUOISE": "#00ffff", "PINK": "#ff00ff", "BLUE": "#0000ff",
       "RED": "#ff0000", "DARK_BLUE": "#000080", "TEAL": "#008080", "GREEN": "#008000", "VIOLET": "#800080",
       "DARK_RED": "#800000", "DARK_YELLOW": "#808000", "GRAY_50": "#808080", "GRAY_25": "#c0c0c0", "BLACK": "#000000"}


class _DocxFonts:
    """Works out the font family/size Word would actually show for a run."""

    def __init__(self, doc):
        from docx.oxml.ns import qn
        self.qn = qn
        self.theme = {}
        try:
            for rel in doc.part.rels.values():
                if rel.reltype.endswith("/theme"):
                    xml = rel.target_part.blob.decode("utf-8", "replace")
                    for kind in ("major", "minor"):
                        m = re.search(r"<a:%sFont>\s*<a:latin typeface=\"([^\"]*)\"" % kind, xml)
                        if m:
                            self.theme[kind] = m.group(1)
        except Exception:
            pass
        self.default_font, self.default_size = None, 11.0
        try:
            rpr = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
            self.default_font = self._rfonts(rpr)
            sz = rpr.find(qn("w:sz"))
            if sz is not None:
                self.default_size = int(sz.get(qn("w:val"))) / 2.0
        except Exception:
            pass

    def _rfonts(self, rpr):
        if rpr is None:
            return None
        rf = rpr.find(self.qn("w:rFonts"))
        if rf is None:
            return None
        name = rf.get(self.qn("w:ascii")) or rf.get(self.qn("w:hAnsi"))
        if name:
            return name
        th = rf.get(self.qn("w:asciiTheme")) or rf.get(self.qn("w:hAnsiTheme"))
        if th:
            return self.theme.get("major" if th.startswith("major") else "minor")
        return None

    def style_font(self, style):
        while style is not None:
            f = self._rfonts(style.element.rPr) if style.element.rPr is not None else None
            if f:
                return f
            style = style.base_style
        return self.default_font

    def style_size(self, style):
        while style is not None:
            if style.font.size is not None:
                return style.font.size.pt
            style = style.base_style
        return self.default_size

    def style_flag(self, style, attr):
        while style is not None:
            v = getattr(style.font, attr)
            if v is not None:
                return bool(v)
            style = style.base_style
        return False


def _docx_list_kind(doc, par):
    from docx.oxml.ns import qn
    ppr = par._p.pPr
    numpr = ppr.numPr if ppr is not None else None
    if numpr is None:
        sname = (par.style.name or "").lower() if par.style is not None else ""
        if sname.startswith("list bullet"):
            m = re.search(r"(\d+)$", sname)
            return "bullet", (int(m.group(1)) - 1) if m else 0
        if sname.startswith("list number"):
            m = re.search(r"(\d+)$", sname)
            return "num", (int(m.group(1)) - 1) if m else 0
        return None
    try:
        ilvl = int(numpr.ilvl.val) if numpr.ilvl is not None else 0
        nid = numpr.numId.val
        if not nid:
            return None
        numbering = doc.part.numbering_part.element
        aid = None
        for num in numbering.findall(qn("w:num")):
            if num.get(qn("w:numId")) == str(nid):
                aid = num.find(qn("w:abstractNumId")).get(qn("w:val"))
        fmt = "bullet"
        for an in numbering.findall(qn("w:abstractNum")):
            if an.get(qn("w:abstractNumId")) == aid:
                for lvl in an.findall(qn("w:lvl")):
                    if lvl.get(qn("w:ilvl")) == str(ilvl):
                        nf = lvl.find(qn("w:numFmt"))
                        fmt = nf.get(qn("w:val")) if nf is not None else "bullet"
        return ("bullet" if fmt in ("bullet", "none") else "num"), min(ilvl, 5)
    except Exception:
        return "bullet", 0


def _docx_images_in(run_el, part, note_path):
    from docx.oxml.ns import qn
    out = []
    for drawing in run_el.iter(qn("w:drawing")):
        emu = None
        ext = drawing.find(".//" + qn("wp:extent"))
        if ext is not None:
            emu = int(ext.get("cx", "0")) or None
        for blip in drawing.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            if not rid or rid not in part.related_parts:
                continue
            ip = part.related_parts[rid]
            ext_name = os.path.splitext(str(ip.partname))[1]
            if ext_name.lower() in (".emf", ".wmf"):
                continue
            rel = _save_image_bytes(ip.blob, note_path, os.path.splitext(os.path.basename(str(ip.partname)))[0], ext_name)
            if rel:
                out.append({"img": rel, "w": _img_width_css(ip.blob, emu)})
    return out


def docx_to_paras(path, note_path, keep_fonts=True, ctx=None):
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    ctx = ctx or R.Ctx()
    doc = docx.Document(path)
    fonts = _DocxFonts(doc)
    paras = []
    align_map = {0: "left", 1: "center", 2: "right", 3: "justify", 4: "justify", 7: "justify", 8: "justify", 9: "justify"}

    def handle_par(par):
        st = par.style
        sname = (st.name or "").lower() if st is not None else ""
        style = _STYLE_MAP.get(sname, "normal")
        lst = _docx_list_kind(doc, par)
        pf = par.paragraph_format
        p = {"type": "p", "style": style, "align": "left", "ls": None, "sb": None, "sa": None, "ind": 0.0, "fi": None,
             "list": lst, "runs": []}
        try:
            if par.alignment is not None:
                p["align"] = align_map.get(int(par.alignment), "left")
            elif st is not None and st.paragraph_format.alignment is not None:
                p["align"] = align_map.get(int(st.paragraph_format.alignment), "left")
        except Exception:
            pass

        def eff(attr):
            v = getattr(pf, attr)
            s2 = st
            while v is None and s2 is not None:
                v = getattr(s2.paragraph_format, attr)
                s2 = s2.base_style
            return v
        sb, sa, ls = eff("space_before"), eff("space_after"), eff("line_spacing")
        s = R.STYLES[style]
        if sb is not None and abs(sb.pt - s.get("sb", 0)) > 0.5:
            p["sb"] = round(sb.pt, 1)
        if sa is not None and abs(sa.pt - s.get("sa", 8)) > 0.5:
            p["sa"] = round(sa.pt, 1)
        if isinstance(ls, float) and abs(ls - s.get("ls", 1.08)) > 0.01:
            p["ls"] = round(ls, 2)
        elif ls is not None and hasattr(ls, "pt"):
            p["ls"] = round(max(1.0, ls.pt / (fonts.style_size(st) * 1.17)), 2)
        li = eff("left_indent")
        if li is not None and not lst and li.inches > 0.05:
            p["ind"] = round(li.inches - s.get("ind", 0), 2)
        fi = eff("first_line_indent")
        if fi is not None and not lst and abs(fi.inches) > 0.02:
            p["fi"] = round(fi.inches, 2)
        if pf.page_break_before:
            paras.append({"type": "pb"})
        s_font = fonts.style_font(st)
        s_size = fonts.style_size(st)
        our_fam, our_size, _ob, _oi = ctx.run_font(style, {})
        for item in par.iter_inner_content():
            runs = item.runs if hasattr(item, "runs") and not hasattr(item, "font") else [item]
            link = getattr(item, "url", None) if runs and runs[0] is not item else None    # a Word hyperlink
            link = R.clean_url(link) if R.is_web_link(link) else None
            for run in runs:
                el = run._r
                for br in el.findall(qn("w:br")):
                    if br.get(qn("w:type")) == "page":
                        if p["runs"]:
                            paras.append(p)
                            p = dict(p, runs=[])
                        paras.append({"type": "pb"})
                p["runs"] += _docx_images_in(el, doc.part, note_path)
                text = run.text
                if not text:
                    continue
                f = run.font
                r = {"t": text.replace("\n", " ")}
                if link:
                    r["link"] = link
                b = f.bold if f.bold is not None else fonts.style_flag(st, "bold")
                i = f.italic if f.italic is not None else fonts.style_flag(st, "italic")
                if b and not s.get("bold"):
                    r["b"] = True
                if i and not s.get("italic"):
                    r["i"] = True
                if f.underline:
                    r["u"] = True
                if f.strike or f.double_strike:
                    r["s"] = True
                if f.superscript:
                    r["sup"] = True
                if f.subscript:
                    r["sub"] = True
                if keep_fonts:
                    fam = fonts._rfonts(el.rPr) if el.rPr is not None else None
                    fam = fam or s_font
                    if fam and fam.lower() != our_fam.lower():
                        r["ff"] = fam
                    size = f.size.pt if f.size is not None else s_size
                    if size and abs(size - our_size) > 0.25:
                        r["fs"] = size
                elif f.size is not None and abs(f.size.pt - s_size) > 0.25:
                    r["fs"] = round(our_size * f.size.pt / max(1.0, s_size) * 2) / 2.0
                try:
                    if f.color is not None and f.color.type is not None and f.color.rgb is not None:
                        hexc = "#" + str(f.color.rgb).lower()
                        if hexc != "#000000":
                            r["fg"] = hexc
                except Exception:
                    pass
                try:
                    if f.highlight_color is not None:
                        r["hl"] = _HL.get(f.highlight_color.name)
                except Exception:
                    pass
                if not r.get("hl"):
                    shd = el.rPr.find(qn("w:shd")) if el.rPr is not None else None
                    if shd is not None and shd.get(qn("w:fill")) not in (None, "auto", "FFFFFF"):
                        r["hl"] = "#" + shd.get(qn("w:fill")).lower()
                if not r.get("hl"):
                    r.pop("hl", None)
                p["runs"].append(r)
        paras.append(p)

    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            handle_par(block)
        elif isinstance(block, Table):
            rows = []
            for row in block.rows:
                cells = []
                for c in row.cells:
                    cells.append("\n".join(pp.text for pp in c.paragraphs).strip())
                rows.append(cells)
            if rows:
                paras.append({"type": "table", "rows": rows})
    return paras


# ---------------------------------------------------------------- OpenDocument .odt
def odt_to_paras(path, note_path):
    with zipfile.ZipFile(path) as z:
        return _odt_to_paras(z, note_path)


def _odt_to_paras(z, note_path):
    from lxml import etree
    root = etree.fromstring(z.read("content.xml"))
    ns = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
          "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
          "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
          "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
          "xlink": "http://www.w3.org/1999/xlink",
          "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
          "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
          "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"}

    def q(p, t):
        return "{%s}%s" % (ns[p], t)
    auto = {}
    for st in root.iter(q("style", "style")):
        props = {}
        tp = st.find(q("style", "text-properties"))
        if tp is not None:
            if tp.get(q("fo", "font-weight")) == "bold":
                props["b"] = True
            if tp.get(q("fo", "font-style")) == "italic":
                props["i"] = True
            if tp.get(q("style", "text-underline-style")) not in (None, "none"):
                props["u"] = True
            if tp.get(q("style", "text-line-through-style")) not in (None, "none"):
                props["s"] = True
            fn = tp.get(q("style", "font-name")) or tp.get(q("fo", "font-family"))
            if fn:
                props["ff"] = fn.strip("'")
            fs = tp.get(q("fo", "font-size"))
            if fs and fs.endswith("pt"):
                props["fs"] = float(fs[:-2])
            col = tp.get(q("fo", "color"))
            if col and col.lower() != "#000000":
                props["fg"] = col.lower()
            bg = tp.get(q("fo", "background-color"))
            if bg and bg != "transparent":
                props["hl"] = bg.lower()
        pp = st.find(q("style", "paragraph-properties"))
        if pp is not None:
            al = pp.get(q("fo", "text-align"))
            if al:
                props["_al"] = {"start": "left", "end": "right", "center": "center", "justify": "justify"}.get(al, "left")
            if pp.get(q("fo", "break-before")) == "page":
                props["_pb"] = True
        auto[st.get(q("style", "name"))] = props
    paras = []

    def runs_of(el, base):
        out = []
        if el.text:
            out.append(dict(base, t=el.text))
        for ch in el:
            tag = etree.QName(ch).localname
            if tag == "span":
                out += runs_of(ch, dict(base, **{k: v for k, v in auto.get(ch.get(q("text", "style-name")), {}).items()
                                               if not k.startswith("_")}))
            elif tag == "s":
                out.append(dict(base, t=" " * int(ch.get(q("text", "c"), "1"))))
            elif tag == "tab":
                out.append(dict(base, t="\t"))
            elif tag == "line-break":
                out.append(dict(base, t=" "))
            elif tag == "frame":
                im = ch.find(q("draw", "image"))
                if im is not None:
                    href = im.get(q("xlink", "href"))
                    try:
                        data = z.read(href)
                        rel = _save_image_bytes(data, note_path, os.path.basename(href).split(".")[0],
                                                os.path.splitext(href)[1])
                        if rel:
                            w = ch.get(q("svg", "width"), "")
                            wcss = None
                            m = re.match(r"([\d.]+)(in|cm|mm)", w)
                            if m:
                                wcss = float(m.group(1)) * {"in": 96, "cm": 37.8, "mm": 3.78}[m.group(2)]
                            out.append({"img": rel, "w": int(wcss) if wcss else _img_width_css(data)})
                    except KeyError:
                        pass
            elif tag in ("a",):
                out += runs_of(ch, base)
            if ch.tail:
                out.append(dict(base, t=ch.tail))
        return out

    def walk(el, lst=None, level=-1):
        for ch in el:
            tag = etree.QName(ch).localname
            if tag in ("p", "h"):
                sty = auto.get(ch.get(q("text", "style-name")), {})
                pname = (ch.get(q("text", "style-name")) or "").lower()
                style = "normal"
                if tag == "h":
                    style = {1: "h1", 2: "h2"}.get(int(ch.get(q("text", "outline-level"), "1")), "h3")
                elif "title" in pname:
                    style = "title"
                elif "subtitle" in pname:
                    style = "subtitle"
                elif "quot" in pname:
                    style = "quote"
                if sty.get("_pb"):
                    paras.append({"type": "pb"})
                base = {k: v for k, v in sty.items() if not k.startswith("_")}
                paras.append({"type": "p", "style": style, "align": sty.get("_al", "left"), "ls": None, "sb": None,
                              "sa": None, "ind": 0.0, "fi": None, "list": (lst, max(0, level)) if lst else None,
                              "runs": [r for r in runs_of(ch, base) if r.get("t") or "img" in r]})
            elif tag == "list":
                kind = lst or "bullet"
                if "num" in (ch.get(q("text", "style-name")) or "").lower():
                    kind = "num"
                walk(ch, kind, level + 1)
            elif tag in ("list-item", "section", "list-header"):
                walk(ch, lst, level)
            elif tag == "table":
                rows = []
                for tr in ch.iter(q("table", "table-row")):
                    rows.append(["\n".join("".join(p.itertext()) for p in tc.iter(q("text", "p")))
                                 for tc in tr.iter(q("table", "table-cell"))])
                if rows:
                    paras.append({"type": "table", "rows": rows})
    body = root.find(q("office", "body"))
    txt = body.find(q("office", "text")) if body is not None else None
    if txt is not None:
        walk(txt)
    return paras


# ---------------------------------------------------------------- other formats
def pdf_to_paras(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    paras = []
    for k, page in enumerate(reader.pages):
        if k:
            paras.append({"type": "pb"})
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        block = []
        for line in text.split("\n"):
            if not line.strip():
                if block:
                    paras.append(_plain(" ".join(block)))
                    block = []
                continue
            block.append(line.strip())
            if re.search(r"[.!?”\"']$", line.strip()) and len(line.strip()) < 60:
                paras.append(_plain(" ".join(block)))
                block = []
        if block:
            paras.append(_plain(" ".join(block)))
    return paras


def _plain(text, style="normal"):
    return {"type": "p", "style": style, "align": "left", "ls": None, "sb": None, "sa": None, "ind": 0.0, "fi": None,
            "list": None, "runs": [{"t": text}] if text else []}


def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def rtf_to_paras(path):
    from striprtf.striprtf import rtf_to_text
    return R.text_to_paras(rtf_to_text(_read_text(path)))


# ---------------------------------------------------------------- entry point
def to_paras(src, note_path, keep_fonts=True, ctx=None):
    ext = os.path.splitext(src)[1].lower()
    base = os.path.dirname(src)
    if ext == ".docx":
        return docx_to_paras(src, note_path, keep_fonts, ctx)
    if ext == ".odt":
        return odt_to_paras(src, note_path)
    if ext == ".pdf":
        return pdf_to_paras(src)
    if ext in (".html", ".htm"):
        return R.html_to_paras(_read_text(src), image_cb=lambda s: fetch_image(s, note_path, base))
    if ext in (".md", ".markdown"):
        return R.markdown_to_paras(_read_text(src), image_cb=lambda s: fetch_image(s, note_path, base))
    if ext == ".rtf":
        return rtf_to_paras(src)
    return R.text_to_paras(_read_text(src))


def import_file(src, folder, keep_fonts=True, ctx=None):
    """Make a new note in folder from a document. Returns the new note's path."""
    ext = os.path.splitext(src)[1].lower()
    stem = lib.note_stem(os.path.splitext(os.path.basename(src))[0], "Imported")
    os.makedirs(folder, exist_ok=True)
    dest = lib.unique_path(folder, stem)
    if ext == ".nobu":
        shutil.copy2(src, dest)
        return dest
    paras = to_paras(src, dest, keep_fonts, ctx)
    if not keep_fonts:
        for p in paras:
            for r in p.get("runs", []):
                r.pop("ff", None)
    while paras and paras[-1].get("type") == "p" and not paras[-1]["runs"]:
        paras.pop()
    paras = [p for k, p in enumerate(paras)
             if not (k and p.get("type") == "p" and not p["runs"] and paras[k - 1].get("type") == "table")]
    doc = nd.empty_doc()
    doc["items"] = R.paras_to_items(paras)
    nd.save_doc(dest, doc)
    return dest
