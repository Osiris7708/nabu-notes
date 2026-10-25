"""Export notes so other people can read them with the same look:
Word (.docx, fonts embedded), PDF, e-book (.epub) and web page (.html) / plain text."""
import base64
import datetime
import html
import logging
import mimetypes
import os
import re
import uuid
import zipfile

import nobu_doc as nd
import nobu_fonts as F
import nobu_library as lib
import nobu_rich as R
from nobu_config import abs_from_home

log = logging.getLogger("nobu.export")

FORMATS = [("docx", "Word document (.docx)", "Opens in Microsoft Word, Google Docs, LibreOffice, Pages. Editable."),
           ("pdf", "PDF (.pdf)", "Looks exactly the same on every device. Best for sending and printing."),
           ("epub", "E-book (.epub)", "For e-readers and book apps (Apple Books, Kobo, Kindle via Send-to-Kindle)."),
           ("html", "Web page (.html) or plain text (.txt)", "A single page that opens in any browser, or bare text.")]
PAGE_W_IN, MARGIN_IN = 8.5, 1.0
TEXT_W_IN = PAGE_W_IN - 2 * MARGIN_IN
FALLBACK_GLYPH_FONTS = ["Segoe UI Symbol", "Segoe UI Historic", "Segoe UI", "Cambria Math", "Arial Unicode MS",
                        "DejaVu Sans", "Noto Sans"]


# ====================================================================== gather
class Note:
    def __init__(self, title, paras):
        self.title, self.paras = title, paras


def load_notes(paths, keep_meta=False):
    out = []
    for p in paths:
        try:
            doc = nd.load_doc(p)
        except Exception:
            log.exception("cannot read %s", p)
            continue
        out.append(Note(lib.title(p), clean(R.items_to_paras(doc.get("items", [])), keep_meta)))
    return out


def clean(paras, keep_meta):
    """Drop Nobu-only bits (recording links, grey timestamps) unless asked to keep them."""
    out = []
    for p in paras:
        if p["type"] != "p":
            out.append(p)
            continue
        runs = []
        for r in p["runs"]:
            if r.get("audio") or (r.get("meta") and not keep_meta):
                continue
            runs.append(r)
        if not runs and p["runs"]:
            continue    # paragraph was only Nobu notes
        q = dict(p)
        q["runs"] = runs
        out.append(q)
    while out and out[0]["type"] == "p" and not any(r.get("t", "").strip() or "img" in r for r in out[0]["runs"]):
        out.pop(0)
    while out and out[-1]["type"] == "p" and not any(r.get("t", "").strip() or "img" in r for r in out[-1]["runs"]):
        out.pop()
    return out


def combined(notes, opts):
    """One paragraph list for a set of notes (chapter titles and page breaks between notes)."""
    out = []
    for k, n in enumerate(notes):
        if k and opts.get("page_per_note", True):
            out.append({"type": "pb"})
        if opts.get("chapter_titles", True) and len(notes) > 1:
            out.append(_par("h1", [{"t": n.title}]))
        out += n.paras
    return out


def _par(style, runs, **kw):
    p = {"type": "p", "style": style, "align": "left", "ls": None, "sb": None, "sa": None, "ind": 0.0, "fi": None,
         "list": None, "runs": runs}
    p.update(kw)
    return p


def fonts_used(paras, ctx):
    used = set()
    for p in paras:
        if p["type"] == "table":
            used.add((ctx.body, False, False))
        if p["type"] != "p":
            continue
        for r in p["runs"]:
            if "t" in r:
                used.add(ctx.run_font(p["style"], r)[0:1] + ctx.run_font(p["style"], r)[2:4])
    return used


def image_size_in(rel, w_css, h_css=None):
    """Display width/height in inches for an image stored with a CSS-pixel width (and a height, if it was
    stretched; otherwise it keeps its shape)."""
    from PIL import Image
    with Image.open(abs_from_home(rel)) as im:
        w0, h0 = im.size
    w = (w_css or min(w0, 480)) / 96.0
    h = h_css / 96.0 if h_css else w * h0 / float(w0)
    if w > TEXT_W_IN:                     # never wider than the page (shrinks evenly)
        h, w = h * TEXT_W_IN / w, TEXT_W_IN
    return w, h


def _list_numbers(paras):
    """Marker text for each list paragraph ('1.', 'a.', bullets) like the editor shows."""
    counters, marks = {}, {}
    for i, p in enumerate(paras):
        if p["type"] != "p" or not p.get("list"):
            counters.clear()
            continue
        kind, lvl = p["list"]
        for k in [k for k in counters if k > lvl]:
            del counters[k]
        if kind == "num":
            counters[lvl] = counters.get(lvl, 0) + 1
            marks[i] = "%d." % counters[lvl] if lvl % 2 == 0 else "%s." % chr(96 + min(26, counters[lvl]))
        else:
            counters.pop(lvl, None)
            marks[i] = ["•", "◦", "▪"][lvl % 3]
    return marks


# ====================================================================== Word (.docx)
WORD_HIGHLIGHT = {"#ffff00": "YELLOW", "#00ff00": "BRIGHT_GREEN", "#00ffff": "TURQUOISE", "#ff00ff": "PINK",
                  "#0000ff": "BLUE", "#ff0000": "RED", "#000080": "DARK_BLUE", "#008080": "TEAL", "#008000": "GREEN",
                  "#800080": "VIOLET", "#800000": "DARK_RED", "#808000": "DARK_YELLOW", "#808080": "GRAY_50",
                  "#c0c0c0": "GRAY_25", "#000000": "BLACK"}


def _set_rfonts(el_rpr, fam):
    from docx.oxml.ns import qn
    rf = el_rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = el_rpr.makeelement(qn("w:rFonts"), {})
        rs = el_rpr.find(qn("w:rStyle"))
        if rs is not None:
            rs.addnext(rf)
        else:
            el_rpr.insert(0, rf)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(a), fam)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rf.get(qn(a)) is not None:
            del rf.attrib[qn(a)]


def _docx_styles(doc, ctx):
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_LINE_SPACING
    names = {"normal": "Normal", "title": "Title", "subtitle": "Subtitle", "h1": "Heading 1", "h2": "Heading 2",
             "h3": "Heading 3", "quote": "Quote"}
    for key, wname in names.items():
        s = R.STYLES[key]
        try:
            st = doc.styles[wname]
        except KeyError:
            from docx.enum.style import WD_STYLE_TYPE
            st = doc.styles.add_style(wname, WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = doc.styles["Normal"]
        fam = ctx.heading if s["role"] == "heading" else ctx.body
        f = st.font
        f.name = fam
        _set_rfonts(st.element.get_or_add_rPr(), fam)
        f.size = Pt(round(ctx.size * s["size"] * 2) / 2.0)
        f.bold = bool(s.get("bold"))
        f.italic = bool(s.get("italic"))
        f.color.rgb = RGBColor(0, 0, 0)
        f.all_caps = False
        pf = st.paragraph_format
        pf.space_before = Pt(s.get("sb", 0))
        pf.space_after = Pt(s.get("sa", 8))
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = s.get("ls", 1.08)
        pf.left_indent = Inches(s.get("ind", 0)) if s.get("ind") else None
        if s.get("align") == "center":
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # strip theme borders/shading Word's template puts on Title / Quote
        ppr = st.element.pPr
        if ppr is not None:
            from docx.oxml.ns import qn
            for tag in ("w:pBdr", "w:shd"):
                for el in ppr.findall(qn(tag)):
                    ppr.remove(el)
    return names


def _docx_numbering(doc):
    """Adds bullet + number list definitions; returns a function that makes a new list instance."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls, qn
    numbering = doc.part.numbering_part.element
    defs = {}
    for aid, kind in ((9001, "bullet"), (9002, "num")):
        lv = []
        for lvl in range(6):
            if kind == "bullet":
                fmt, text = "bullet", ["•", "◦", "▪"][lvl % 3]
            else:
                fmt, text = ("decimal" if lvl % 2 == 0 else "lowerLetter"), "%%%d." % (lvl + 1)
            left = 360 * (lvl + 1) + 360
            lv.append('<w:lvl w:ilvl="%d"><w:start w:val="1"/><w:numFmt w:val="%s"/><w:lvlText w:val="%s"/>'
                      '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="%d" w:hanging="360"/></w:pPr>%s</w:lvl>'
                      % (lvl, fmt, html.escape(text, quote=True), left,
                         '<w:rPr><w:rFonts w:ascii="Segoe UI Symbol" w:hAnsi="Segoe UI Symbol"/></w:rPr>'
                         if kind == "bullet" else ""))
        el = parse_xml('<w:abstractNum %s w:abstractNumId="%d"><w:multiLevelType w:val="hybridMultilevel"/>%s'
                       '</w:abstractNum>' % (nsdecls("w"), aid, "".join(lv)))
        first_num = numbering.find(qn("w:num"))
        if first_num is not None:
            first_num.addprevious(el)
        else:
            numbering.append(el)
        defs[kind] = aid
    counter = [9100]

    def new_list(kind):
        counter[0] += 1
        nid = counter[0]
        numbering.append(parse_xml('<w:num %s w:numId="%d"><w:abstractNumId w:val="%d"/>'
                                   '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'
                                   % (nsdecls("w"), nid, defs[kind])))
        return nid
    return new_list


def _docx_hyperlink(par, url, runs):
    """Wrap runs already in the paragraph in a Word hyperlink (python-docx has no call for this)."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), rid)
    h.set(qn("w:history"), "1")
    runs[0]._r.addprevious(h)
    for run in runs:
        h.append(run._r)          # (moves the run inside the link)


def _docx_float(run, f, w_in, h_in):
    """Turn a picture just added to run into a floating one, with Word's own text wrapping."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls, qn
    inline = run._r.find(".//" + qn("wp:inline"))
    if inline is None:
        return
    emu = lambda px: int(round(px / 96.0 * 914400))        # noqa: E731  (page pixels -> Word's units)
    wrap = f.get("wrap")
    if wrap == "square":
        wrap_xml = '<wp:wrapSquare %s wrapText="%s"/>' % (nsdecls("wp"), {"right": "right", "left": "left"}.get(
            f.get("text"), "largest"))
    elif wrap == "topbottom":
        wrap_xml = "<wp:wrapTopAndBottom %s/>" % nsdecls("wp")
    else:
        wrap_xml = "<wp:wrapNone %s/>" % nsdecls("wp")
    anchor = parse_xml(
        '<wp:anchor %s distT="0" distB="76200" distL="114300" distR="114300" simplePos="0" relativeHeight="251659264" '
        'behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="column"><wp:posOffset>%d</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="paragraph"><wp:posOffset>%d</wp:posOffset></wp:positionV></wp:anchor>'
        % (nsdecls("wp"), emu(f.get("x", 0)), emu(f.get("y", 0))))
    anchor.append(inline.find(qn("wp:extent")))
    anchor.append(parse_xml('<wp:effectExtent %s l="0" t="0" r="0" b="0"/>' % nsdecls("wp")))
    anchor.append(parse_xml(wrap_xml))
    for tag in ("wp:docPr", "wp:cNvGraphicFramePr", "a:graphic"):
        el = inline.find(qn(tag))
        if el is not None:
            anchor.append(el)
    inline.getparent().replace(inline, anchor)


def _docx_run(par, r, pstyle, ctx, style_defaults):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_COLOR_INDEX
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    pieces = r["t"].split("\t")
    targets = []
    for k, piece in enumerate(pieces):
        run = par.add_run(piece)
        if k < len(pieces) - 1:
            run.add_tab()
        targets.append(run)
    if r.get("link"):
        _docx_hyperlink(par, r["link"], targets)
        if not r.get("fg"):
            r = dict(r, fg=R.LINK_COLOUR, u=True)
    fam, size, bold, italic = ctx.run_font(pstyle, r)
    s_fam, s_size, s_bold, s_italic = style_defaults
    for run in targets:
        f = run.font
        if fam != s_fam:
            f.name = fam
            _set_rfonts(run._r.get_or_add_rPr(), fam)
        if abs(size - s_size) > 0.01:
            f.size = Pt(size)
        if bold != s_bold:
            f.bold = bold
        if italic != s_italic:
            f.italic = italic
        if r.get("u"):
            f.underline = True
        if r.get("s"):
            f.strike = True
        if r.get("sup"):
            f.superscript = True
        if r.get("sub"):
            f.subscript = True
        if r.get("fg"):
            f.color.rgb = RGBColor.from_string(r["fg"].lstrip("#").upper())
        elif r.get("meta"):
            f.color.rgb = RGBColor(0x77, 0x77, 0x77)
        if r.get("hl"):
            name = WORD_HIGHLIGHT.get(r["hl"].lower())
            if name:
                f.highlight_color = getattr(WD_COLOR_INDEX, name)
            else:
                rpr = run._r.get_or_add_rPr()
                shd = parse_xml('<w:shd %s w:val="clear" w:color="auto" w:fill="%s"/>'
                                % (nsdecls("w"), r["hl"].lstrip("#").upper()))
                later = None
                for tag in ("fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"):
                    later = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}" + tag)
                    if later is not None:
                        break
                if later is not None:
                    later.addprevious(shd)
                else:
                    rpr.append(shd)


def _page_number_footer(section, ctx):
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p._p.append(parse_xml('<w:fldSimple %s w:instr="PAGE"><w:r><w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s"/>'
                          '<w:sz w:val="%d"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple>'
                          % (nsdecls("w"), html.escape(ctx.body, quote=True), html.escape(ctx.body, quote=True),
                             int(max(9, ctx.size * 0.8) * 2))))


def to_docx(paras, ctx, out_path, title="", opts=None):
    opts = opts or {}
    import docx
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
    from docx.oxml.ns import qn
    doc = docx.Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(MARGIN_IN))
    names = _docx_styles(doc, ctx)
    new_list = _docx_numbering(doc)
    doc.core_properties.title = title or ""
    doc.core_properties.author = ""
    if opts.get("page_numbers", True):
        _page_number_footer(sec, ctx)
    # python-docx's blank template has one empty paragraph: reuse it
    body = doc.element.body
    for p0 in list(body.findall(qn("w:p"))):
        body.remove(p0)
    align = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
             "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
    list_ids, prev_list = {}, None
    pending_break = False
    for idx, p in enumerate(paras):
        if p["type"] == "pb":
            pending_break = True
            prev_list = None
            continue
        if p["type"] == "table":
            rows = p["rows"] or [[""]]
            ncol = max(len(r) for r in rows)
            t = doc.add_table(rows=len(rows), cols=ncol)
            try:
                t.style = doc.styles["Table Grid"]
            except KeyError:
                pass
            for ri, row in enumerate(rows):
                for ci in range(ncol):
                    cell = t.cell(ri, ci)
                    lines = (row[ci] if ci < len(row) else "").split("\n")
                    cp = cell.paragraphs[0]
                    cp.paragraph_format.space_after = Pt(0)
                    for k, ln in enumerate(lines):
                        if k:
                            cp = cell.add_paragraph()
                            cp.paragraph_format.space_after = Pt(0)
                        cp.add_run(ln)
            nxt = paras[idx + 1] if idx + 1 < len(paras) else None
            if nxt is None or nxt["type"] == "table":
                doc.add_paragraph().paragraph_format.space_after = Pt(0)
            prev_list = None
            continue
        style = p["style"]
        par = doc.add_paragraph(style=names.get(style, "Normal"))
        if pending_break:
            par.paragraph_format.page_break_before = True
            pending_break = False
        pf = par.paragraph_format
        s = R.STYLES.get(style, R.STYLES["normal"])
        if p.get("align", "left") != s.get("align", "left"):
            par.alignment = align.get(p["align"])
        if p.get("ls") is not None:
            pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
            pf.line_spacing = float(p["ls"])
        if p.get("sb") is not None:
            pf.space_before = Pt(p["sb"])
        if p.get("sa") is not None:
            pf.space_after = Pt(p["sa"])
        ind = (p.get("ind") or 0) + s.get("ind", 0)
        if p.get("list"):
            kind, lvl = p["list"]
            key = (kind,)
            if prev_list is None or prev_list[0] != kind:
                list_ids[key] = new_list(kind)
            prev_list = (kind, lvl)
            numpr = par._p.get_or_add_pPr().get_or_add_numPr()
            numpr.get_or_add_ilvl().val = min(lvl, 5)
            numpr.get_or_add_numId().val = list_ids[key]
            if ind:
                pf.left_indent = Inches(ind + 0.25 * (lvl + 1) + 0.25)
            pf.space_after = Pt(0) if p.get("sa") is None else pf.space_after
        else:
            prev_list = None
            if ind:
                pf.left_indent = Inches(ind)
            if p.get("fi"):
                pf.first_line_indent = Inches(p["fi"])
        sdef = ((ctx.heading if s["role"] == "heading" else ctx.body), round(ctx.size * s["size"] * 2) / 2.0,
                bool(s.get("bold")), bool(s.get("italic")))
        for r in p["runs"]:
            if "img" in r:
                try:
                    w, h = image_size_in(r["img"], r.get("w"), r.get("h"))
                    run = par.add_run()
                    run.add_picture(abs_from_home(r["img"]), width=Inches(w), height=Inches(h))
                    if r.get("float"):
                        _docx_float(run, r["float"], w, h)
                except Exception:
                    log.exception("image skipped")
                    par.add_run("[missing picture]")
            elif r.get("t"):
                _docx_run(par, r, style, ctx, sdef)
    if pending_break:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.save(out_path)
    if opts.get("embed_fonts", True):
        try:
            _embed_docx_fonts(out_path, fonts_used(paras, ctx) | {(ctx.body, False, False), (ctx.heading, False, False)})
        except Exception:
            log.exception("font embedding failed (the document is still fine)")
    return out_path


def _obfuscate(data, guid):
    key = bytes.fromhex(guid.strip("{}").replace("-", ""))[::-1]
    out = bytearray(data)
    for i in range(min(32, len(out))):
        out[i] ^= key[i % 16]
    return bytes(out)


def _embeddable(path):
    """Font's own licence flags (OS/2 fsType) allow embedding in documents."""
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(path, lazy=True)
        fs = t["OS/2"].fsType if "OS/2" in t else 0
        t.close()
        return not (fs & 0x0002) or bool(fs & 0x000C)   # not "restricted", or preview/editable allowed
    except Exception:
        return False


def _embed_docx_fonts(path, used):
    """Embed the fonts the document uses (Word's 'Embed fonts in the file'), so the recipient sees the same
    fonts without installing anything. Fonts whose licence forbids embedding (e.g. Varnyx) are left out."""
    fams = {}
    for fam, _b, _i in used:
        if F.licence_blocks_embedding(fam):
            continue
        for b, i, slot in ((False, False, "embedRegular"), (True, False, "embedBold"),
                           (False, True, "embedItalic"), (True, True, "embedBoldItalic")):
            fp, sb, si = F.font_file(fam, b, i)
            if fp and not sb and not si and fp.lower().endswith(".ttf") and _embeddable(fp):
                fams.setdefault(fam, {})[slot] = fp
    if not fams:
        return
    src = zipfile.ZipFile(path)
    files = {n: src.read(n) for n in src.namelist()}
    src.close()
    ft = files.get("word/fontTable.xml", b"").decode("utf-8")
    if not ft:
        ft = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:fonts xmlns:w="http://schemas.openxmlformats.'
              'org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
              'relationships"></w:fonts>')
    if "xmlns:r=" not in ft.split(">", 2)[1]:
        ft = re.sub(r"<w:fonts ", '<w:fonts xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                    'relationships" ', ft, count=1)
    rels = []
    n = 0
    for fam, slots in fams.items():
        emb = []
        for slot, fp in slots.items():
            n += 1
            guid = "{%s}" % str(uuid.uuid4()).upper()
            with open(fp, "rb") as f:
                files["word/fonts/font%d.odttf" % n] = _obfuscate(f.read(), guid)
            rels.append('<Relationship Id="rIdF%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        'relationships/font" Target="fonts/font%d.odttf"/>' % (n, n))
            emb.append('<w:%s r:id="rIdF%d" w:fontKey="%s"/>' % (slot, n, guid))
        entry = '<w:font w:name="%s"><w:charset w:val="00"/><w:family w:val="auto"/><w:pitch w:val="variable"/>%s</w:font>' % (
            html.escape(fam, quote=True), "".join(emb))
        ft = re.sub(r'<w:font w:name="%s">.*?</w:font>' % re.escape(html.escape(fam, quote=True)), "", ft, flags=re.S)
        ft = ft.replace("</w:fonts>", entry + "</w:fonts>")
    files["word/fontTable.xml"] = ft.encode("utf-8")
    rp = "word/_rels/fontTable.xml.rels"
    existing = files.get(rp, b"").decode("utf-8")
    if existing:
        existing = existing.replace("</Relationships>", "".join(rels) + "</Relationships>")
    else:
        existing = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.'
                    'openxmlformats.org/package/2006/relationships">%s</Relationships>' % "".join(rels))
    files[rp] = existing.encode("utf-8")
    ct = files["[Content_Types].xml"].decode("utf-8")
    if 'Extension="odttf"' not in ct:
        ct = ct.replace("</Types>", '<Default Extension="odttf" ContentType="application/vnd.openxmlformats-'
                        'officedocument.obfuscatedFont"/></Types>')
    if "/word/fontTable.xml" not in ct:
        ct = ct.replace("</Types>", '<Override PartName="/word/fontTable.xml" ContentType="application/vnd.'
                        'openxmlformats-officedocument.wordprocessingml.fontTable+xml"/></Types>')
    files["[Content_Types].xml"] = ct.encode("utf-8")
    st = files.get("word/settings.xml", b"").decode("utf-8")
    st = re.sub(r'<w:zoom w:val="bestFit"/>', '<w:zoom w:percent="100"/>', st)
    if st and "embedTrueTypeFonts" not in st:
        # schema order: writeProtection, view, zoom, removePersonalInformation, ... then embedTrueTypeFonts
        m = None
        for tag in ("printFormsData", "printFractionalCharacterWidth", "printPostScriptOverText", "displayBackgroundShape",
                    "doNotDisplayPageBoundaries", "removeDateAndTime", "removePersonalInformation", "zoom", "view",
                    "writeProtection"):
            m = re.search(r"<w:%s\b[^>]*?(/>|>.*?</w:%s>)" % (tag, tag), st, re.S)
            if m:
                break
        if m:
            st = st[:m.end()] + "<w:embedTrueTypeFonts/>" + st[m.end():]
        else:
            st = re.sub(r"(<w:settings[^>]*>)", r"\1<w:embedTrueTypeFonts/>", st, count=1)
        files["word/settings.xml"] = st.encode("utf-8")
    dr = "word/_rels/document.xml.rels"
    d = files[dr].decode("utf-8")
    if "fontTable.xml" not in d:
        d = d.replace("</Relationships>", '<Relationship Id="rIdFT1" Type="http://schemas.openxmlformats.org/'
                      'officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/></Relationships>')
        files[dr] = d.encode("utf-8")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        order = ["[Content_Types].xml"] + [k for k in files if k != "[Content_Types].xml"]
        for k in order:
            z.writestr(k, files[k])
    os.replace(tmp, path)


# ====================================================================== PDF
class _PdfFonts:
    def __init__(self):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        self.pm, self.TTFont = pdfmetrics, TTFont
        self.names = {}
        self.fallbacks = None

    def name(self, fam, bold=False, italic=False):
        key = (fam.lower(), bold, italic)
        if key in self.names:
            return self.names[key]
        path, sb, _si = F.font_file(fam, bold, italic)
        nm = None
        if path:
            nm = ("NBSB_%d" if sb else "NB_%d") % len(self.names)
            try:
                self.pm.registerFont(self.TTFont(nm, path))
                self.names[key + ("path",)] = path
            except Exception:
                log.warning("could not use font %s for PDF", path)
                nm = None
        if nm is None:
            nm = {(False, False): "Times-Roman", (True, False): "Times-Bold", (False, True): "Times-Italic",
                  (True, True): "Times-BoldItalic"}[(bold, italic)]
        self.names[key] = nm
        return nm

    def path(self, fam, bold, italic):
        self.name(fam, bold, italic)
        return self.names.get((fam.lower(), bold, italic, "path"))

    def glyph_fallbacks(self):
        if self.fallbacks is None:
            self.fallbacks = []
            for fam in FALLBACK_GLYPH_FONTS:
                p, _, _ = F.font_file(fam)
                if p and p.lower().endswith(".ttf"):
                    self.fallbacks.append((self.name(fam), F.coverage(p)))
        return self.fallbacks


_patched = []


def _patch_reportlab_fake_bold():
    """Fonts with no bold file get Word-style synthetic bold (outline stroke) in PDFs."""
    if _patched:
        return
    from reportlab.pdfgen import textobject as TO
    orig_set, orig_uset, orig_fill = TO.PDFTextObject.setFont, TO.PDFTextObject._setFont, TO.PDFTextObject.setFillColor

    def mode(self, name, size):
        fake = str(name).startswith("NBSB_")
        if fake or getattr(self, "_nb_fake", False):
            self._code.append("%d Tr %s w" % (2 if fake else 0, round(size * 0.03, 3)))
        self._nb_fake = fake

    def setFont(self, psfontname, size, leading=None):
        orig_set(self, psfontname, size, leading)
        mode(self, psfontname, size)

    def _setFont(self, psfontname, size):
        orig_uset(self, psfontname, size)
        mode(self, psfontname, size)

    def setFillColor(self, aColor, alpha=None):
        orig_fill(self, aColor, alpha)
        try:
            self.setStrokeColor(aColor, alpha)
        except Exception:
            pass
    TO.PDFTextObject.setFont, TO.PDFTextObject._setFont, TO.PDFTextObject.setFillColor = setFont, _setFont, setFillColor
    _patched.append(1)


def _pdf_markup(text, fname, cover, fonts):
    """Escape text for a reportlab Paragraph, switching to a fallback font for characters the font lacks."""
    out, buf = [], []
    for ch in text:
        if ch == "\t":
            buf.append("&nbsp;" * 6)
            continue
        if cover is None or ord(ch) in cover or ch in " \n":
            buf.append(html.escape(ch))
            continue
        alt = next((n for n, c in fonts.glyph_fallbacks() if ord(ch) in c), None)
        if alt:
            out.append("".join(buf))
            buf = []
            out.append('<font name="%s">%s</font>' % (alt, html.escape(ch)))
        else:
            buf.append(html.escape(ch))
    out.append("".join(buf))
    return "".join(out)


def _bullet_font(bullet, ctx, fonts, body_name):
    if not bullet or bullet[0].isalnum():
        return body_name
    bp = fonts.path(ctx.body, False, False)
    if bp and ord(bullet[0]) in F.coverage(bp):
        return body_name
    for n, cov in fonts.glyph_fallbacks():
        if ord(bullet[0]) in cov:
            return n
    return body_name


def to_pdf(paras, ctx, out_path, title="", opts=None):
    opts = opts or {}
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import ImageAndFlowables
    _patch_reportlab_fake_bold()
    fonts = _PdfFonts()
    aligns = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
    story = []
    marks = _list_numbers(paras)
    body_name = fonts.name(ctx.body)
    wraps = []                    # (story position, picture, side): text to flow round a floating picture
    for i, p in enumerate(paras):
        if p["type"] == "pb":
            story.append(PageBreak())
            continue
        floats = [r for r in p.get("runs", []) if r.get("float")] if p["type"] == "p" else []
        if floats:
            p = dict(p, runs=[r for r in p["runs"] if not r.get("float")])
        if p["type"] == "table":
            rows = p["rows"] or [[""]]
            ncol = max(len(r) for r in rows)
            cst = ParagraphStyle("cell", fontName=body_name, fontSize=ctx.size, leading=ctx.size * 1.25)
            bp = fonts.path(ctx.body, False, False)
            cover = F.coverage(bp) if bp else None
            data = [[Paragraph(_pdf_markup(row[c] if c < len(row) else "", body_name, cover, fonts).replace("\n", "<br/>"),
                               cst) for c in range(ncol)] for row in rows]
            t = Table(data, colWidths=[TEXT_W_IN * inch / ncol] * ncol)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#555555")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 8)]
            continue
        m = ctx.par_metrics(p)
        s = R.STYLES.get(p["style"], R.STYLES["normal"])
        base_size = round(ctx.size * s["size"] * 2) / 2.0
        leading = base_size * 1.17 * m["ls"]
        ind = m["ind"] * inch
        bullet = None
        if p.get("list"):
            lvl = p["list"][1]
            ind += (0.25 * (lvl + 1) + 0.25) * inch
            bullet = marks.get(i)
            if bullet and not bullet[0].isalnum() and _bullet_font(bullet, ctx, fonts, body_name) == body_name:
                bp = fonts.path(ctx.body, False, False)
                if bp and ord(bullet[0]) not in F.coverage(bp):
                    bullet = "\u2022" if ord("\u2022") in F.coverage(bp) else "-"
        st = ParagraphStyle("p%d" % i, fontName=body_name, fontSize=base_size, leading=leading,
                            spaceBefore=m["sb"], spaceAfter=m["sa"] if not p.get("list") else (p.get("sa") or 0),
                            leftIndent=ind, firstLineIndent=(m["fi"] * inch) if (m["fi"] and not bullet) else 0,
                            alignment=aligns.get(m["align"], TA_LEFT), bulletIndent=ind - 0.25 * inch,
                            bulletFontName=_bullet_font(bullet, ctx, fonts, body_name),
                            bulletFontSize=base_size)
        parts = []
        images_only = all("img" in r for r in p["runs"]) and p["runs"]
        if images_only:
            for r in p["runs"]:
                try:
                    w, h = image_size_in(r["img"], r.get("w"), r.get("h"))
                    im = RLImage(abs_from_home(r["img"]), width=w * inch, height=h * inch)
                    im.hAlign = {"center": "CENTER", "right": "RIGHT"}.get(m["align"], "LEFT")
                    story += [Spacer(1, m["sb"]), im, Spacer(1, m["sa"])]
                except Exception:
                    log.exception("pdf image")
            continue
        for r in p["runs"]:
            if "img" in r:
                try:
                    w, h = image_size_in(r["img"], r.get("w"), r.get("h"))
                    parts.append('<img src="%s" width="%d" height="%d" valign="bottom"/>' % (
                        html.escape(abs_from_home(r["img"])), w * 72, h * 72))
                except Exception:
                    pass
                continue
            fam, size, bold, italic = ctx.run_font(p["style"], r)
            fname = fonts.name(fam, bold, italic)
            fp = fonts.path(fam, bold, italic)
            txt = _pdf_markup(r["t"], fname, F.coverage(fp) if fp else None, fonts)
            attrs = 'name="%s" size="%s"' % (fname, R._fmt(size))
            if r.get("fg"):
                attrs += ' color="%s"' % r["fg"]
            elif r.get("meta"):
                attrs += ' color="#777777"'
            if r.get("hl"):
                attrs += ' backColor="%s"' % r["hl"]
            txt = "<font %s>%s</font>" % (attrs, txt)
            if r.get("u"):
                txt = "<u>%s</u>" % txt
            if r.get("s"):
                txt = "<strike>%s</strike>" % txt
            if r.get("sup"):
                txt = "<super>%s</super>" % txt
            if r.get("sub"):
                txt = "<sub>%s</sub>" % txt
            if r.get("link"):                 # links look like links (Word's own blue), and open when clicked
                if not r.get("fg"):
                    txt = '<font color="%s">%s</font>' % (R.LINK_COLOUR, txt)
                if not r.get("u"):
                    txt = "<u>%s</u>" % txt
                txt = '<a href="%s">%s</a>' % (html.escape(r["link"], quote=True), txt)
            parts.append(txt)
        markup = "".join(parts) or "&nbsp;"
        for r in floats:              # floating pictures: beside this paragraph (text flows round), or above it
            try:
                w, h = image_size_in(r["img"], r.get("w"), r.get("h"))
                im = RLImage(abs_from_home(r["img"]), width=w * inch, height=h * inch)
                side = R.float_side(r["float"], r.get("w") or w * 96)
                if side:
                    wraps.append((len(story), im, side))
                else:
                    x = r["float"].get("x", 0) / 96.0
                    im.hAlign = "LEFT" if x < 0.5 else ("RIGHT" if x + w > TEXT_W_IN - 0.5 else "CENTER")
                    story += [Spacer(1, r["float"].get("y", 0) * 0.75), im, Spacer(1, 6)]
            except Exception:
                log.exception("pdf floating picture")
        try:
            story.append(Paragraph(markup, st, bulletText=bullet))
        except Exception:
            log.exception("pdf paragraph fallback")
            story.append(Paragraph(html.escape("".join(r.get("t", "") for r in p["runs"])), st, bulletText=bullet))
    for pos, im, side in reversed(wraps):     # the paragraphs after a floating picture flow round it
        end = pos
        while end < len(story) and end - pos < 30 and isinstance(story[end], Paragraph):
            end += 1
        if end > pos:
            story[pos:end] = [ImageAndFlowables(im, story[pos:end], imageSide=side, imageLeftPadding=9,
                                                imageRightPadding=9, imageBottomPadding=6)]
        else:
            story.insert(pos, im)

    page_no = opts.get("page_numbers", True)

    def on_page(canvas, doc):
        if page_no:
            canvas.saveState()
            canvas.setFont(body_name, max(9, ctx.size * 0.8))
            canvas.drawCentredString(letter[0] / 2.0, 0.6 * inch, str(doc.page))
            canvas.restoreState()

    doc = SimpleDocTemplate(out_path, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch,
                            bottomMargin=inch, title=title or "", author="", creator="Nobu Notes")
    doc.build(story or [Spacer(1, 1)], onFirstPage=on_page, onLaterPages=on_page)
    return out_path


# ====================================================================== web page, e-book, text
def _font_faces(paras, ctx, mode="data", folder=None):
    """@font-face rules for the fonts used (only fonts whose licence allows it).
    mode 'data' inlines them; mode 'files' copies them into folder and links relative paths."""
    css, files = [], {}
    fams = {f for f, _b, _i in fonts_used(paras, ctx)} | {ctx.body, ctx.heading}
    lib_fams = {e["family"].lower(): e for e in F.registry() if e["category"] not in ("yours", "system")}
    for fam in sorted(fams):
        e = lib_fams.get(fam.lower())
        if not e or F.licence_blocks_embedding(fam):
            continue
        for style, fp in e["files"].items():
            weight = "bold" if "bold" in style else "normal"
            sty = "italic" if "italic" in style else "normal"
            fmt = "opentype" if fp.lower().endswith(".otf") else "truetype"
            if mode == "data":
                with open(fp, "rb") as f:
                    src = "data:font/%s;base64,%s" % ("otf" if fmt == "opentype" else "ttf",
                                                      base64.b64encode(f.read()).decode("ascii"))
            else:
                name = "fonts/" + os.path.basename(fp)
                files[name] = fp
                src = name
            css.append("@font-face{font-family:'%s';src:url(%s) format('%s');font-weight:%s;font-style:%s}"
                       % (fam, src, fmt, weight, sty))
    return "\n".join(css), files


def to_html_file(paras, ctx, out_path, title="", opts=None):
    css, _ = _font_faces(paras, ctx, "data")
    page = R.to_html(paras, ctx, img_src=R.image_data_uri, full_page=True, title=title, fonts_css=css)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return out_path


def to_txt(paras, ctx, out_path, title="", opts=None):
    with open(out_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(R.plain_text(paras, links=True).replace("\f", "\n\n"))
    return out_path


def _xhtml(fragment):
    """Turn an HTML fragment into well-formed XHTML for an e-book."""
    from lxml import etree
    from lxml import html as lh
    root = lh.fragment_fromstring(fragment or "<p></p>", create_parent="div")
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        el.attrib.pop("clear", None)
    return "".join(etree.tostring(ch, method="xml", encoding="unicode") for ch in root) or "<p/>"


def to_epub(notes, ctx, out_path, title="", opts=None):
    opts = opts or {}
    book_id = "urn:uuid:" + str(uuid.uuid4())
    all_paras = [p for n in notes for p in n.paras]
    css_faces, font_files = _font_faces(all_paras, ctx, "files")
    images = {}

    def img_src(rel):
        if rel not in images:
            ext = os.path.splitext(rel)[1].lower() or ".png"
            images[rel] = "images/img%d%s" % (len(images) + 1, ext)
        return images[rel]

    chapters = []
    multi = len(notes) > 1
    for k, n in enumerate(notes):
        paras = n.paras
        if multi and opts.get("chapter_titles", True):
            paras = [_par("h1", [{"t": n.title}])] + paras
        frag = R.to_html([p for p in paras if p["type"] != "pb"], ctx, img_src=img_src)
        chapters.append((n.title, "chapter%d.xhtml" % (k + 1), _xhtml(frag)))
    css = (css_faces + "\nbody{font-family:'%s',Georgia,serif;font-size:1em;line-height:1.35;margin:0 5%%}"
           "img{max-width:100%%;height:auto}table{border-collapse:collapse}td{border:1px solid #888;padding:.2em .4em}"
           "h1,h2{font-family:'%s',Georgia,serif}" % (ctx.body, ctx.heading))
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        man, spine = [], []
        for t, fn, body in chapters:
            z.writestr("OEBPS/" + fn, '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/'
                       '1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>%s</title>'
                       '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>%s</body></html>'
                       % (html.escape(t), body), compress_type=zipfile.ZIP_DEFLATED)
            iid = fn.split(".")[0]
            man.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (iid, fn))
            spine.append('<itemref idref="%s"/>' % iid)
        nav = "".join('<li><a href="%s">%s</a></li>' % (fn, html.escape(t)) for t, fn, _ in chapters)
        z.writestr("OEBPS/nav.xhtml", '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/'
                   '1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>Contents</title>'
                   '</head><body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol>%s</ol></nav></body></html>' % nav,
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        man.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        man.append('<item id="css" href="style.css" media-type="text/css"/>')
        for k, (name, fp) in enumerate(font_files.items()):
            z.write(fp, "OEBPS/" + name, compress_type=zipfile.ZIP_DEFLATED)
            man.append('<item id="font%d" href="%s" media-type="%s"/>' % (
                k, name, "font/otf" if fp.lower().endswith(".otf") else "font/ttf"))
        for k, (rel, name) in enumerate(images.items()):
            try:
                z.write(abs_from_home(rel), "OEBPS/" + name, compress_type=zipfile.ZIP_DEFLATED)
                man.append('<item id="img%d" href="%s" media-type="%s"/>' % (
                    k, name, mimetypes.guess_type(name)[0] or "image/png"))
            except OSError:
                log.warning("missing image %s", rel)
        now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        z.writestr("OEBPS/content.opf", '<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" '
                   'version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<dc:identifier id="bookid">%s</dc:identifier><dc:title>%s</dc:title><dc:language>en</dc:language>'
                   '<meta property="dcterms:modified">%s</meta></metadata><manifest>%s</manifest><spine>%s</spine></package>'
                   % (book_id, html.escape(title or "Nobu Notes"), now, "".join(man), "".join(spine)),
                   compress_type=zipfile.ZIP_DEFLATED)
    return out_path


# ====================================================================== entry point
def export(paths, fmt, out_path, ctx, opts=None):
    """paths: notes in reading order. fmt: docx | pdf | epub | html | txt."""
    opts = opts or {}
    notes = load_notes(paths, keep_meta=opts.get("keep_meta", False))
    title = opts.get("title") or (notes[0].title if len(notes) == 1 else "Nobu Notes")
    if fmt == "epub":
        return to_epub(notes, ctx, out_path, title, opts)
    paras = combined(notes, opts)
    fn = {"docx": to_docx, "pdf": to_pdf, "html": to_html_file, "txt": to_txt}[fmt]
    return fn(paras, ctx, out_path, title, opts)
