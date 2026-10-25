"""Rich-text model shared by the editor, importers, exporters and the clipboard.

Storage (a note's "items") keeps text runs with tag lists. Tags:
  character:  b i u s sup sub meta lm   ff:<family>  fs:<pt>  fg:#rrggbb  hl:#rrggbb  audio|<file>
              link:<web address>  (made safe by clean_url: no spaces, quotes or braces)
  paragraph:  st:<style>  al:left|center|right|justify  ls:<multiple>  sb:<pt>  sa:<pt>
              ind:<inches>  fi:<inches>  li:bullet:<level> | li:num:<level>
  blocks:     {"table": {"rows": [[...]]}}   {"pb": 1}  (page break)   {"i": image, "w": px, "h": px}
              a picture placed anywhere on the page also has "float": {"wrap", "text", "x", "y"} (see nobu_float)
              (a picture's "h" is only there when it was stretched; without it the picture keeps its shape)
"lm" marks list-marker text ("•\\t", "3.\\t") that the editor draws; exporters skip it.

"paras" is the export-friendly form: a list of blocks
  {"type":"p", "style":..., "align":..., "ls":..., "sb":..., "sa":..., "ind":..., "fi":..., "list":(kind,level)|None,
   "runs":[{"t":..., "b":..., ...} | {"img": rel, "w": px}]}
  {"type":"table", "rows":[[str]]}      {"type":"pb"}
"""
import base64
import html
import mimetypes
import re
from html.parser import HTMLParser

from nobu_config import abs_from_home

CHAR_FLAGS = ("b", "i", "u", "s", "sup", "sub", "meta", "lm")
CHAR_KEYS = ("ff", "fs", "fg", "hl", "link")
PAR_KEYS = ("st", "al", "ls", "sb", "sa", "ind", "fi", "li")
AUDIO = "audio|"

# Word-like styles. size = multiple of the base (Normal) size; role picks text or heading font.
STYLES = {
    "normal":   dict(label="Normal", role="body", size=1.0, sb=0, sa=8, ls=1.08),
    "title":    dict(label="Title", role="heading", size=2.0, sb=0, sa=6, ls=1.0, align="center"),
    "subtitle": dict(label="Subtitle", role="body", size=1.15, italic=True, sb=0, sa=10, ls=1.08),
    "h1":       dict(label="Heading 1", role="heading", size=1.6, sb=14, sa=6, ls=1.0),
    "h2":       dict(label="Heading 2", role="heading", size=1.3, sb=10, sa=4, ls=1.0),
    "h3":       dict(label="Heading 3", role="body", size=1.1, bold=True, sb=8, sa=4, ls=1.0),
    "quote":    dict(label="Quote", role="body", size=1.0, italic=True, sb=6, sa=10, ls=1.08, ind=0.5),
}
STYLE_ORDER = ["normal", "title", "subtitle", "h1", "h2", "h3", "quote"]
LEGACY = {"h1": "st:h1", "h2": "st:h2", "center": "al:center"}


def is_char_tag(t):
    return t in CHAR_FLAGS or t.startswith(AUDIO) or t.split(":", 1)[0] in CHAR_KEYS and ":" in t


def is_par_tag(t):
    return ":" in t and t.split(":", 1)[0] in PAR_KEYS


def persistent(t):
    return is_char_tag(t) or is_par_tag(t)


def tag_value(tags, key, default=None):
    p = key + ":"
    for t in tags:
        if t.startswith(p):
            return t[len(p):]
    return default


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def upgrade_tags(tags):
    return [LEGACY.get(t, t) for t in tags]


# ---------------------------------------------------------------- links
LINK_COLOUR = "#0563c1"            # Word's hyperlink blue, used in exports
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"]+", re.I)
_URL_SAFE = ":/?#[]@!$&'()*+,;=%~-._"


def clean_url(url):
    """A web address ready to store in a tag and to open: 'www.x.com' gets https://, and spaces, quotes,
    braces and backslashes are %-encoded (they would break the tag, or the link in Word / RTF)."""
    from urllib.parse import quote
    url = (url or "").strip()
    if url.lower().startswith("www."):
        url = "https://" + url
    return quote(url, safe=_URL_SAFE)


def is_web_link(url):
    return bool(re.match(r"(https?://|mailto:)\S", url or "", re.I))


def find_urls(text):
    """(start, end, address) for every web address written in text. Full stops, commas, quotes and an
    unmatched closing bracket at the end belong to the sentence, not the address."""
    out = []
    for m in URL_RE.finditer(text):
        s = m.group()
        while s:
            if s[-1] in ".,;:!?'\"":
                s = s[:-1]
            elif s[-1] == ")" and s.count("(") < s.count(")"):
                s = s[:-1]
            elif s[-1] == "]" and s.count("[") < s.count("]"):
                s = s[:-1]
            else:
                break
        if len(s) > (4 if s.lower().startswith("www.") else 8) and "." in s:
            out.append((m.start(), m.start() + len(s), clean_url(s)))
    return out


# ---------------------------------------------------------------- items <-> paras
def _run_from_tags(text, tags):
    tags = set(tags)
    r = {"t": text}
    for f in ("b", "i", "u", "s", "sup", "sub", "meta"):
        if f in tags:
            r[f] = True
    for k in CHAR_KEYS:
        v = tag_value(tags, k)
        if v is not None:
            r[k] = fnum(v) if k == "fs" else v
    for t in tags:
        if t.startswith(AUDIO):
            r["audio"] = t[len(AUDIO):]
    return r


def _par_from_tags(tags):
    tags = upgrade_tags(tags)
    st = tag_value(tags, "st", "normal")
    p = {"type": "p", "style": st, "align": tag_value(tags, "al") or STYLES.get(st, STYLES["normal"]).get("align", "left"),
         "ls": fnum(tag_value(tags, "ls")), "sb": fnum(tag_value(tags, "sb")), "sa": fnum(tag_value(tags, "sa")),
         "ind": fnum(tag_value(tags, "ind"), 0.0), "fi": fnum(tag_value(tags, "fi")), "list": None, "runs": []}
    li = tag_value(tags, "li")
    if li:
        kind, _, lvl = li.partition(":")
        p["list"] = (kind, int(fnum(lvl, 0)))
    if p["style"] not in STYLES:
        p["style"] = "normal"
    return p


def items_to_paras(items):
    out = []
    cur_runs = []
    last_tags = []

    def close(par_tags):
        p = _par_from_tags(par_tags)
        p["runs"] = cur_runs[:]
        out.append(p)
        cur_runs.clear()

    skip_nl = False
    for it in items:
        tags = upgrade_tags(it.get("g", []))
        if "table" in it or "pb" in it:
            if cur_runs:
                close(last_tags)
            out.append({"type": "table", "rows": it["table"].get("rows", [])} if "table" in it else {"type": "pb"})
            skip_nl = True
            continue
        if "i" in it:
            cur_runs.append(dict({"img": it["i"], "w": it.get("w"), "h": it.get("h")},
                                 **({"float": dict(it["float"])} if it.get("float") else {})))
            last_tags = tags
            skip_nl = False
            continue
        text = it.get("t", "")
        parts = text.split("\n")
        for k, seg in enumerate(parts):
            if seg and "lm" not in tags:
                cur_runs.append(_run_from_tags(seg, tags))
                skip_nl = False
            if k < len(parts) - 1:
                if skip_nl and not cur_runs:
                    skip_nl = False
                    continue
                close(tags)
                skip_nl = False
        last_tags = tags
    if cur_runs:
        close(last_tags)
    return out


def _char_tags(r):
    g = [f for f in ("b", "i", "u", "s", "sup", "sub", "meta") if r.get(f)]
    for k in CHAR_KEYS:
        if r.get(k) not in (None, ""):
            v = r[k]
            if k == "fs":
                v = ("%.1f" % float(v)).rstrip("0").rstrip(".")
            g.append("%s:%s" % (k, v))
    if r.get("audio"):
        g.append(AUDIO + r["audio"])
    return g


def _par_tags(p):
    g = []
    if p.get("style", "normal") != "normal":
        g.append("st:" + p["style"])
    if p.get("align", "left") != STYLES.get(p.get("style", "normal"), STYLES["normal"]).get("align", "left"):
        g.append("al:" + p["align"])
    for k in ("ls", "sb", "sa", "fi"):
        if p.get(k) is not None:
            g.append("%s:%s" % (k, ("%.2f" % p[k]).rstrip("0").rstrip(".")))
    if p.get("ind"):
        g.append("ind:%s" % ("%.2f" % p["ind"]).rstrip("0").rstrip("."))
    if p.get("list"):
        g.append("li:%s:%d" % (p["list"][0], p["list"][1]))
    return g


def paras_to_items(paras):
    items = []
    num = {}
    for p in paras:
        if p["type"] == "table":
            items.append({"table": {"rows": p["rows"]}, "g": []})
            items.append({"t": "\n", "g": []})
            continue
        if p["type"] == "pb":
            items.append({"pb": 1, "g": []})
            items.append({"t": "\n", "g": []})
            continue
        pt = _par_tags(p)
        if p.get("list"):
            kind, lvl = p["list"]
            if kind == "num":
                num[lvl] = num.get(lvl, 0) + 1
                for deeper in [k for k in num if k > lvl]:
                    del num[deeper]
                marker = "%d.\t" % num[lvl]
            else:
                marker = "\u2022\t"
            items.append({"t": marker, "g": sorted(pt + ["lm"])})
        else:
            num.clear()
        for r in p.get("runs", []):
            if "img" in r:
                it = {"i": r["img"], "w": r.get("w"), "g": [] if r.get("float") else sorted(pt)}
                if r.get("h"):
                    it["h"] = r["h"]
                if r.get("float"):
                    it["float"] = dict(r["float"])
                items.append(it)
            elif r.get("t"):
                items.append({"t": r["t"], "g": sorted(set(pt + _char_tags(r)))})
        items.append({"t": "\n", "g": sorted(pt)})
    return items


def _plain_run(r, links):
    t = r["t"]
    url = r.get("link")
    if links and url and t.strip() and url.rstrip("/") not in (t.strip().rstrip("/"), clean_url(t.strip()).rstrip("/")):
        t += " (%s)" % url          # a link whose words aren't its address: keep the address in plain text
    return t


def plain_text(paras, links=False):
    out = []
    for p in paras:
        if p["type"] == "table":
            out.append("\n".join("\t".join(row) for row in p["rows"]))
        elif p["type"] == "pb":
            out.append("\f")
        else:
            prefix = ("\u2022 " if p["list"] and p["list"][0] == "bullet" else "- " if p["list"] else "")
            out.append("    " * (p["list"][1] if p["list"] else 0) + prefix +
                       "".join(_plain_run(r, links) for r in p["runs"] if "t" in r))
    return "\n".join(out)


# ---------------------------------------------------------------- resolved formatting
class Ctx:
    """Fonts and base size used to resolve styles (from the user's settings)."""

    def __init__(self, body="IM FELL English", heading="Eagle Lake", size=14.0):
        self.body, self.heading, self.size = body, heading, float(size)

    def style(self, name):
        return STYLES.get(name, STYLES["normal"])

    def par_metrics(self, p):
        s = self.style(p["style"])
        return dict(
            sb=p["sb"] if p.get("sb") is not None else s.get("sb", 0),
            sa=p["sa"] if p.get("sa") is not None else s.get("sa", 8),
            ls=p["ls"] if p.get("ls") is not None else s.get("ls", 1.08),
            ind=(p.get("ind") or 0) + s.get("ind", 0),
            fi=p.get("fi") or 0.0,
            align=p.get("align", "left"))

    def run_font(self, p_style, r):
        s = self.style(p_style)
        fam = r.get("ff") or (self.heading if s["role"] == "heading" else self.body)
        size = r.get("fs") or round(self.size * s["size"] * 2) / 2.0
        if r.get("meta"):
            size = max(8.0, round(self.size * 0.75))
        bold = bool(r.get("b") or s.get("bold"))
        italic = bool(r.get("i") or s.get("italic"))
        return fam, float(size), bold, italic


def luminance(hexcol):
    try:
        h = hexcol.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    except Exception:
        return 1.0


# ---------------------------------------------------------------- HTML out
def _css_font(fam):
    return "'%s'" % fam.replace("'", "")


def stretched(rel, w, h):
    """Is w x h a different shape from the picture itself (more than 2% off)?"""
    try:
        from PIL import Image
        with Image.open(abs_from_home(rel)) as im:
            w0, h0 = im.size
        return abs(h - w * h0 / float(w0)) > 0.02 * h
    except Exception:
        return False


def image_data_uri(rel):
    p = abs_from_home(rel)
    with open(p, "rb") as f:
        b = base64.b64encode(f.read()).decode("ascii")
    return "data:%s;base64,%s" % (mimetypes.guess_type(p)[0] or "image/png", b)


def to_html(paras, ctx, img_src=image_data_uri, full_page=False, title="", fonts_css="", for_word=False):
    """HTML with inline styles (Word reads these when pasting / opening)."""
    out = []
    open_lists = []

    def close_lists(to=0):
        while len(open_lists) > to:
            out.append("</%s>" % open_lists.pop())

    for p in paras:
        if p["type"] == "table":
            close_lists()
            out.append("<table style='border-collapse:collapse;margin:6pt 0'>")
            for row in p["rows"]:
                out.append("<tr>" + "".join(
                    "<td style='border:1px solid #888;padding:3pt 6pt;font-family:%s;font-size:%spt'>%s</td>"
                    % (_css_font(ctx.body), _fmt(ctx.size), html.escape(c).replace("\n", "<br>")) for c in row) + "</tr>")
            out.append("</table>")
            continue
        if p["type"] == "pb":
            close_lists()
            out.append("<br style='page-break-before:always;mso-break-type:section-break' clear=all>"
                       if for_word else "<div style='page-break-after:always'></div>")
            continue
        m = ctx.par_metrics(p)
        style = ("margin:%spt 0 %spt %sin;line-height:%d%%;text-align:%s%s" %
                 (_fmt(m["sb"]), _fmt(m["sa"]), _fmt(m["ind"]), round(m["ls"] * 100), m["align"],
                  (";text-indent:%sin" % _fmt(m["fi"])) if m["fi"] else ""))
        body = "".join(_run_html(r, p["style"], ctx, img_src) for r in p["runs"]) or "&nbsp;"
        tag = {"title": "h1", "h1": "h1", "h2": "h2", "h3": "h3", "subtitle": "p", "quote": "blockquote"}.get(
            p["style"], "p")
        if p.get("list"):
            kind, lvl = p["list"]
            want = "ul" if kind == "bullet" else "ol"
            depth = lvl + 1
            if len(open_lists) > depth:
                close_lists(depth)
            while len(open_lists) < depth:
                out.append("<%s style='margin:0 0 0 %sin'>" % (want, "0.25"))
                open_lists.append(want)
            if open_lists and open_lists[-1] != want:
                close_lists(depth - 1)
                out.append("<%s>" % want)
                open_lists.append(want)
            out.append("<li style='%s'>%s</li>" % (style, body))
            continue
        close_lists()
        out.append("<%s style='%s'>%s</%s>" % (tag, style, body, tag))
    close_lists()
    frag = "\n".join(out)
    if not full_page:
        return frag
    return ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title><style>%s\n"
            "body{background:#fff;color:#111;max-width:6.5in;margin:1in auto;font-family:%s,serif;font-size:%spt}"
            "img{max-width:100%%}</style></head><body>%s</body></html>"
            % (html.escape(title), fonts_css, _css_font(ctx.body), _fmt(ctx.size), frag))


TEXT_W_PX = 624            # page pixels (96 to the inch): the width of the text on a page (6.5")
TEXT_H_PX = 864            # ... and its height (9")


def float_side(f, w):
    """Which side of the text a floating picture sits on in a flowing layout (web page, e-book, PDF):
    "left" or "right" (a picture with the text on its right sits on the left), or None (on its own lines)."""
    if f.get("wrap") != "square":
        return None
    if f.get("text") == "right":
        return "left"
    if f.get("text") == "left":
        return "right"
    x = f.get("x", 0)
    return "left" if TEXT_W_PX - (x + w) >= x else "right"


def _float_html(src, r):
    f = r["float"]
    w = int(r.get("w") or 400)
    size = "width:%dpx;height:%dpx" % (w, int(r["h"])) if r.get("h") else "width:%dpx;max-width:60%%" % w
    side = float_side(f, w)
    x, y = int(f.get("x", 0)), int(f.get("y", 0))
    if side == "left":
        pos = "float:left;margin:%dpx 12px 8px %dpx" % (y, x)
    elif side == "right":
        pos = "float:right;margin:%dpx %dpx 8px 12px" % (y, max(0, TEXT_W_PX - x - w))
    else:
        pos = "display:block;clear:both;margin:%dpx 0 8px %dpx" % (y, x)
    return "<img src='%s' style='%s;%s' width='%d'>" % (src, size, pos, w)


def _fmt(v):
    return ("%.2f" % float(v)).rstrip("0").rstrip(".")


def _run_html(r, pstyle, ctx, img_src):
    if "img" in r:
        try:
            src = img_src(r["img"])
        except Exception:
            return "[missing picture]"
        w = r.get("w") or 400
        if r.get("float"):
            return _float_html(src, r)
        if r.get("h"):                    # stretched: both sizes, so it isn't put back into shape
            return "<img src='%s' style='width:%dpx;height:%dpx' width='%d' height='%d'>" % (
                src, int(w), int(r["h"]), int(w), int(r["h"]))
        return "<img src='%s' style='width:%dpx;max-width:100%%' width='%d'>" % (src, int(w), int(w))
    fam, size, bold, italic = ctx.run_font(pstyle, r)
    css = ["font-family:%s" % _css_font(fam), "font-size:%spt" % _fmt(size)]
    if bold:
        css.append("font-weight:bold")
    if italic:
        css.append("font-style:italic")
    deco = [d for f, d in (("u", "underline"), ("s", "line-through")) if r.get(f)]
    if deco:
        css.append("text-decoration:" + " ".join(deco))
    if r.get("sup"):
        css.append("vertical-align:super")
    if r.get("sub"):
        css.append("vertical-align:sub")
    if r.get("fg"):
        css.append("color:" + r["fg"])
    elif r.get("meta"):
        css.append("color:#777")
    if r.get("hl"):
        css.append("background:" + r["hl"])
    t = html.escape(r["t"]).replace("\t", "&emsp;")
    span = "<span style=\"%s\">%s</span>" % (";".join(css), t)
    if r.get("link"):
        return "<a href=\"%s\">%s</a>" % (html.escape(r["link"], quote=True), span)
    return span


# ---------------------------------------------------------------- HTML in (paste from Word/web, .html import)
_COLOR_NAMES = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "yellow": "#ffff00", "blue": "#0000ff",
                "green": "#008000", "gray": "#808080", "grey": "#808080", "lime": "#00ff00", "cyan": "#00ffff",
                "magenta": "#ff00ff", "aqua": "#00ffff", "fuchsia": "#ff00ff", "silver": "#c0c0c0",
                "maroon": "#800000", "navy": "#000080", "olive": "#808000", "purple": "#800080", "teal": "#008080",
                "orange": "#ffa500"}


def _color(v):
    v = (v or "").strip().lower()
    if not v or v in ("windowtext", "auto", "inherit", "transparent", "initial", "none"):
        return None
    if v in _COLOR_NAMES:
        return _COLOR_NAMES[v]
    m = re.match(r"#([0-9a-f]{3}|[0-9a-f]{6})$", v)
    if m:
        h = m.group(1)
        return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)
    m = re.match(r"rgba?\((\d+)\D+(\d+)\D+(\d+)", v)
    if m:
        return "#%02x%02x%02x" % tuple(min(255, int(x)) for x in m.groups())
    return None


def _size_pt(v):
    v = (v or "").strip().lower()
    m = re.match(r"([\d.]+)\s*(pt|px|em|rem|%)?", v)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2) or "px"
    return {"pt": n, "px": n * 0.75, "em": n * 12, "rem": n * 12, "%": n * 0.12}[unit]


def _parse_style(s):
    d = {}
    for part in (s or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip().lower()] = v.strip()
    return d


class _HTMLToParas(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "tr", "title"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr", "source", "embed", "param"}

    def __init__(self, image_cb=None):
        super().__init__(convert_charrefs=True)
        self.paras = []
        self.fmt = [("", {})]       # (tag, formatting) - closing a tag drops everything opened inside it
        self.par = None
        self.lists = []
        self.image_cb = image_cb
        self.table = None
        self.cell = None
        self.skip = 0

    def _cur(self):
        return self.fmt[-1][1]

    def _start_par(self, style="normal", align=None, extra=None):
        self._end_par()
        self.par = {"type": "p", "style": style, "align": align or "left", "ls": None, "sb": None, "sa": None,
                    "ind": 0.0, "fi": None, "list": None, "runs": []}
        if extra:
            self.par.update(extra)

    def _end_par(self):
        if self.par is not None:
            if self.par["runs"] or self.par["style"] != "normal" or self.par.get("list"):
                self.paras.append(self.par)
            self.par = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "head", "xml"):
            self.skip += 1
            return
        st = _parse_style(a.get("style"))
        f = dict(self._cur())
        if tag in ("b", "strong"):
            f["b"] = True
        if tag in ("i", "em", "cite"):
            f["i"] = True
        if tag == "u":
            f["u"] = True
        if tag in ("s", "strike", "del"):
            f["s"] = True
        if tag == "sup":
            f["sup"] = True
        if tag == "sub":
            f["sub"] = True
        if tag == "a" and is_web_link(a.get("href")):    # (page anchors and relative links can't be followed)
            f["link"] = clean_url(a["href"])
        if tag == "font":
            if a.get("face"):
                f["ff"] = a["face"].split(",")[0].strip(" '\"")
            if a.get("color") and _color(a["color"]):
                f["fg"] = _color(a["color"])
        if st.get("font-weight") in ("bold", "700", "800", "900", "600"):
            f["b"] = True
        if st.get("font-weight") in ("normal", "400"):
            f.pop("b", None)
        if st.get("font-style") == "italic":
            f["i"] = True
        deco = st.get("text-decoration", "") + " " + st.get("text-decoration-line", "")
        if "underline" in deco:
            f["u"] = True
        if "line-through" in deco:
            f["s"] = True
        if st.get("vertical-align") in ("super", "sup"):
            f["sup"] = True
        if st.get("vertical-align") == "sub":
            f["sub"] = True
        if st.get("font-family"):
            fam = st["font-family"].split(",")[0].strip(" '\"")
            if fam and not fam.lower().startswith(("mso-", "-")):
                f["ff"] = fam
        if st.get("font-size") and _size_pt(st["font-size"]):
            f["fs"] = round(_size_pt(st["font-size"]) * 2) / 2.0
        col = _color(st.get("color"))
        if col:
            f["fg"] = col
        bg = _color(st.get("background") or st.get("background-color") or st.get("mso-highlight"))
        if bg and bg != "#ffffff":
            f["hl"] = bg
        if tag not in self.VOID:            # (<br>, <img>... never get a closing tag)
            self.fmt.append((tag, f))
        if tag in ("ul", "ol"):
            self.lists.append("bullet" if tag == "ul" else "num")
        if tag == "table":
            self._end_par()
            self.table = []
        if tag == "tr" and self.table is not None:
            self.table.append([])
            return
        if tag in ("td", "th") and self.table is not None:
            self.cell = []
            return
        if tag in self.BLOCK and self.table is None:
            style = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3",
                     "blockquote": "quote", "title": "title"}.get(tag, "normal")
            cls = (a.get("class") or "").lower()
            if "msotitle" in cls:
                style = "title"
            elif "msosubtitle" in cls:
                style = "subtitle"
            elif "msoquote" in cls:
                style = "quote"
            al = st.get("text-align") or a.get("align")
            al = al.lower() if al and al.lower() in ("left", "center", "right", "justify") else None
            extra = {}
            mb = _size_pt(st.get("margin-bottom", "")) if st.get("margin-bottom") else None
            mt = _size_pt(st.get("margin-top", "")) if st.get("margin-top") else None
            if mb is not None:
                extra["sa"] = round(mb, 1)
            if mt is not None:
                extra["sb"] = round(mt, 1)
            lh = st.get("line-height", "")
            m = re.match(r"([\d.]+)\s*%", lh)
            if m:
                extra["ls"] = round(float(m.group(1)) / 100.0, 2)
            elif re.match(r"^[\d.]+$", lh or "x"):
                extra["ls"] = float(lh)
            ti = st.get("text-indent")
            if ti and _size_pt(ti):
                extra["fi"] = round(_size_pt(ti) / 72.0, 2)
            if tag == "li" and self.lists:
                extra["list"] = (self.lists[-1], len(self.lists) - 1)
            elif "mso-list" in (a.get("style") or "") and tag == "p":
                extra["list"] = ("bullet", 0)
            self._start_par(style, al, extra)
        if tag == "br":
            if self.cell is not None:
                self.cell.append("\n")
            elif self.par is not None:
                self._add_text("\n")
        if tag == "img" and self.image_cb:
            rel = self.image_cb(a.get("src", ""))
            if rel:
                if self.par is None:
                    self._start_par()
                def px(v):
                    try:
                        return int(float(str(v).replace("px", ""))) if v else None
                    except ValueError:
                        return None
                w, h = px(a.get("width")), px(a.get("height"))
                run = {"img": rel, "w": w}
                if w and h and stretched(rel, w, h):
                    run["h"] = h
                self.par["runs"].append(run)

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "xml"):
            self.skip = max(0, self.skip - 1)
            return
        for k in range(len(self.fmt) - 1, 0, -1):     # close the matching tag (and anything left open in it)
            if self.fmt[k][0] == tag:
                del self.fmt[k:]
                break
        if tag in ("ul", "ol") and self.lists:
            self.lists.pop()
        if tag in ("td", "th") and self.table is not None and self.cell is not None:
            if self.table:
                self.table[-1].append("".join(self.cell).strip())
            self.cell = None
            return
        if tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            if rows:
                w = max(len(r) for r in rows)
                self.paras.append({"type": "table", "rows": [r + [""] * (w - len(r)) for r in rows]})
            self.table = None
            return
        if tag in self.BLOCK and self.table is None:
            self._end_par()

    def _add_text(self, data):
        f = self._cur()
        run = dict(f, t=data)
        if self.par is None:
            self._start_par()
        runs = self.par["runs"]
        if runs and "t" in runs[-1] and {k: v for k, v in runs[-1].items() if k != "t"} == f:
            runs[-1]["t"] += data
        else:
            runs.append(run)

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        data = re.sub(r"[\r\n\t ]+", " ", data)
        if not data.strip() and (self.par is None or not self.par["runs"]):
            return
        self._add_text(data)

    def close(self):
        super().close()
        self._end_par()
        for p in self.paras:
            if p["type"] == "p" and p["runs"]:
                r0 = p["runs"][0]
                if "t" in r0:
                    r0["t"] = r0["t"].lstrip(" ")
                r1 = p["runs"][-1]
                if "t" in r1:
                    r1["t"] = r1["t"].rstrip(" ")
        return _split_soft(self.paras)     # line breaks become separate paragraphs (Nobu has no soft breaks)


def _split_soft(paras):
    out = []
    for p in paras:
        if p["type"] != "p" or not any("t" in r and "\n" in r["t"] for r in p["runs"]):
            out.append(p)
            continue
        cur = dict(p, runs=[])
        for r in p["runs"]:
            if "t" not in r or "\n" not in r["t"]:
                cur["runs"].append(r)
                continue
            parts = r["t"].split("\n")
            for k, seg in enumerate(parts):
                if seg:
                    cur["runs"].append(dict(r, t=seg))
                if k < len(parts) - 1:
                    out.append(cur)
                    cur = dict(p, runs=[], sb=0)
        out.append(cur)
    return out


def html_to_paras(text, image_cb=None):
    m = re.search(r"<!--StartFragment-->(.*)<!--EndFragment-->", text, re.S)
    if m:
        text = m.group(1)
    parser = _HTMLToParas(image_cb)
    parser.feed(text)
    return parser.close()


# ---------------------------------------------------------------- Markdown in
def markdown_to_paras(md, image_cb=None):
    paras = []
    for line in md.replace("\r\n", "\n").split("\n"):
        s = line.rstrip()
        if not s.strip():
            continue
        style, lst = "normal", None
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            style = {1: "h1", 2: "h2"}.get(len(m.group(1)), "h3")
            s = m.group(2)
        elif re.match(r"^\s*([-*+])\s+", s):
            lvl = (len(s) - len(s.lstrip())) // 2
            lst = ("bullet", min(lvl, 4))
            s = re.sub(r"^\s*[-*+]\s+", "", s)
        elif re.match(r"^\s*\d+[.)]\s+", s):
            lvl = (len(s) - len(s.lstrip())) // 2
            lst = ("num", min(lvl, 4))
            s = re.sub(r"^\s*\d+[.)]\s+", "", s)
        elif s.startswith(">"):
            style = "quote"
            s = s.lstrip("> ")
        elif re.match(r"^(\*\s*){3,}$|^(-\s*){3,}$", s):
            continue
        runs = []
        pos = 0
        for mm in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)|\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_|~~(.+?)~~"
                              r"|\[([^\]]+)\]\(((?:https?://|mailto:)[^)\s]+)\)", s):
            if mm.start() > pos:
                runs.append({"t": s[pos:mm.start()]})
            if mm.group(1) is not None:
                rel = image_cb(mm.group(1)) if image_cb else None
                if rel:
                    runs.append({"img": rel, "w": None})
            elif mm.group(2):
                runs.append({"t": mm.group(2), "b": True, "i": True})
            elif mm.group(3) or mm.group(4):
                runs.append({"t": mm.group(3) or mm.group(4), "b": True})
            elif mm.group(5) or mm.group(6):
                runs.append({"t": mm.group(5) or mm.group(6), "i": True})
            elif mm.group(7):
                runs.append({"t": mm.group(7), "s": True})
            elif mm.group(8):
                runs.append({"t": mm.group(8), "link": clean_url(mm.group(9))})
            pos = mm.end()
        if pos < len(s):
            runs.append({"t": s[pos:]})
        paras.append({"type": "p", "style": style, "align": "left", "ls": None, "sb": None, "sa": None,
                      "ind": 0.0, "fi": None, "list": lst, "runs": runs})
    return paras


def text_to_paras(txt):
    paras = []
    for line in txt.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip() == "\f":
            paras.append({"type": "pb"})
            continue
        paras.append({"type": "p", "style": "normal", "align": "left", "ls": None, "sb": None, "sa": None,
                      "ind": 0.0, "fi": None, "list": None, "runs": [{"t": line}] if line else []})
    return paras


# ---------------------------------------------------------------- RTF out (clipboard for Word)
def _rtf_escape(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\t":
            out.append("\\tab ")
        elif o > 127:
            if o > 0xFFFF:
                o -= 0x10000
                for u in (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)):
                    out.append("\\u%d?" % (u - 65536 if u > 32767 else u))
            else:
                out.append("\\u%d?" % (o - 65536 if o > 32767 else o))
        else:
            out.append(ch)
    return "".join(out)


def to_rtf(paras, ctx):
    fonts, colors = [], ["#000000"]

    def fi(name):
        if name not in fonts:
            fonts.append(name)
        return fonts.index(name)

    def ci(c):
        if c not in colors:
            colors.append(c)
        return colors.index(c) + 1

    body = []
    for p in paras:
        if p["type"] == "pb":
            body.append("\\page ")
            continue
        if p["type"] == "table":
            n = max(len(r) for r in p["rows"]) if p["rows"] else 1
            for row in p["rows"]:
                body.append("\\trowd\\trgaph108" + "".join(
                    "\\clbrdrt\\brdrs\\clbrdrl\\brdrs\\clbrdrb\\brdrs\\clbrdrr\\brdrs\\cellx%d" % int(9360 * (k + 1) / n)
                    for k in range(n)))
                for c in row:
                    body.append("\\pard\\intbl\\f%d\\fs%d %s\\cell " % (fi(ctx.body), int(ctx.size * 2), _rtf_escape(c)))
                body.append("\\row ")
            body.append("\\pard ")
            continue
        m = ctx.par_metrics(p)
        al = {"left": "\\ql", "center": "\\qc", "right": "\\qr", "justify": "\\qj"}[m["align"]]
        ind = m["ind"] + (0.25 * (p["list"][1] + 1) if p.get("list") else 0)
        fi_tw = int((m["fi"] if not p.get("list") else -0.25) * 1440)
        body.append("\\pard%s\\sb%d\\sa%d\\sl%d\\slmult1\\li%d\\fi%d " % (
            al, int(m["sb"] * 20), int(m["sa"] * 20), int(240 * m["ls"]), int(ind * 1440), fi_tw))
        if p.get("list"):
            fam, size, _, _ = ctx.run_font(p["style"], {})
            body.append("{\\f%d\\fs%d %s\\tab}" % (fi(fam), int(size * 2),
                                                   "\\u8226?" if p["list"][0] == "bullet" else "-"))
        for r in p["runs"]:
            if "img" in r:
                try:
                    from PIL import Image
                    import io
                    with Image.open(abs_from_home(r["img"])) as im:
                        buf = io.BytesIO()
                        im.convert("RGBA").save(buf, "PNG")
                        w = (r.get("w") or min(im.width, 480))
                        h = int(r.get("h") or im.height * w / im.width)
                    body.append("{\\pict\\pngblip\\picwgoal%d\\pichgoal%d %s}" % (
                        w * 15, h * 15, buf.getvalue().hex()))
                except Exception:
                    pass
                continue
            fam, size, bold, italic = ctx.run_font(p["style"], r)
            codes = "\\f%d\\fs%d" % (fi(fam), int(round(size * 2)))
            codes += ("\\b" if bold else "") + ("\\i" if italic else "") + ("\\ul" if r.get("u") else "")
            codes += ("\\strike" if r.get("s") else "") + ("\\super" if r.get("sup") else "")
            codes += ("\\sub" if r.get("sub") else "")
            if r.get("fg"):
                codes += "\\cf%d" % ci(r["fg"])
            if r.get("hl"):
                codes += "\\highlight%d\\chcbpat%d" % (ci(r["hl"]), ci(r["hl"]))
            if r.get("link"):
                if not r.get("fg"):           # links look like links (Word's own blue)
                    codes += "\\cf%d" % ci(LINK_COLOUR) + ("" if r.get("u") else "\\ul")
                body.append("{\\field{\\*\\fldinst{HYPERLINK \"%s\"}}{\\fldrslt{%s %s}}}" % (
                    _rtf_escape(r["link"]), codes, _rtf_escape(r["t"])))
            else:
                body.append("{%s %s}" % (codes, _rtf_escape(r["t"])))
        body.append("\\par\n")
    ftbl = "".join("{\\f%d\\fnil\\fcharset0 %s;}" % (k, _rtf_escape(f)) for k, f in enumerate(fonts or [ctx.body]))
    ctbl = ";" + "".join("\\red%d\\green%d\\blue%d;" % (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
                         for c in colors)
    return "{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl%s}{\\colortbl%s}\\viewkind4\\uc1 %s}" % (
        ftbl, ctbl, "".join(body))
