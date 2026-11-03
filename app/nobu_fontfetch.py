"""Fonts in pasted text that this computer doesn't have: look for a free copy and download it.

Only Google Fonts is used: every font there is free and legal to download, use and share (SIL Open Font
License, Apache or Ubuntu Font Licence). A font that isn't there (most fonts that come with Windows, Office or
a Mac are paid fonts, e.g. Book Antiqua) is never downloaded from anywhere else - Nobu just says so.
This is the second (and last) time Nobu goes online, besides the speech models; Settings can turn it off.
"""
import logging
import os
import re
import tempfile

log = logging.getLogger("nobu.fontfetch")

CSS = "https://fonts.googleapis.com/css2?family=%s&display=swap"
_tried = {}                                        # family (lower case) -> result, so each is looked up once


def _ask(url):
    import requests
    # (an ordinary browser name gets .woff2 files; this one gets .ttf, which Windows can install)
    return requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (Windows NT 6.1) NobuNotes"})


LIST = "https://fonts.google.com/metadata/fonts"
LIST_DAYS = 30                                     # Google's list of fonts is fetched again after a month


def catalog():
    """{family in lower case: (Family Name, [styles like "400", "700i"])} of Google's open-source fonts.
    (Asking Google for a font it doesn't have still returns a stand-in font, so the list is the only sure
    way to know.) Kept in cache\\google_fonts.json; must be called inside allow_downloads()."""
    import json
    import time
    from nobu_config import HOME
    path = os.path.join(HOME, "cache", "google_fonts.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - d.get("time", 0) < LIST_DAYS * 86400 and d.get("families"):
            return {k: tuple(v) for k, v in d["families"].items()}
    except (OSError, ValueError):
        pass
    r = _ask(LIST)
    r.raise_for_status()
    text = r.text[4:] if r.text.startswith(")]}'") else r.text
    fams = {}
    for e in json.loads(text).get("familyMetadataList", []):
        if e.get("family") and e.get("isOpenSource", True):
            fams[e["family"].lower()] = (e["family"], sorted((e.get("fonts") or {}).keys()))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"time": time.time(), "families": fams}, f)
    return fams


def _css_for(name, styles):
    """Google Fonts' description of a family it has: regular, bold and italics where it has them."""
    want = [(i, w) for i, w in ((0, 400), (0, 700), (1, 400), (1, 700)) if ("%d%s" % (w, "i" if i else "")) in styles]
    spec = (":ital,wght@" + ";".join("%d,%d" % iw for iw in want)) if want else ""
    r = _ask(CSS % (name.replace(" ", "+") + spec))
    if r.status_code == 200 and "@font-face" in r.text:
        return r.text
    r = _ask(CSS % name.replace(" ", "+"))                 # (just the regular style)
    return r.text if r.status_code == 200 and "@font-face" in r.text else None


def fetch(family, install=True):
    """Look for a free copy of family on Google Fonts and add it to Nobu's fonts (install: into Windows too,
    so Word sees it - Settings > "install fonts"). Returns (outcome, text): outcome is "downloaded",
    "not_free" (not on Google Fonts) or "failed"."""
    key = family.strip().lower()
    if key in _tried:
        return _tried[key]
    import nobu_fonts as F
    import nobu_offline
    result = ("not_free", "")
    try:
        with nobu_offline.allow_downloads():
            entry = catalog().get(key)
            css, found = (_css_for(entry[0], entry[1]), entry[0]) if entry else (None, None)
            if css:
                urls = re.findall(r"font-style:\s*(\w+);\s*font-weight:\s*(\d+);[^}]*?src:\s*url\(([^)]+\.ttf)\)", css)
                if not urls:
                    urls = [("normal", "400", u) for u in re.findall(r"url\(([^)]+\.ttf)\)", css)[:1]]
                tmp = tempfile.mkdtemp(prefix="nobu-font-")
                paths = []
                seen = set()
                for style, weight, url in urls:
                    tag = ("bold" if int(weight) >= 600 else "regular") + ("italic" if style == "italic" else "")
                    tag = {"regularitalic": "italic"}.get(tag, tag)
                    if tag in seen:
                        continue
                    seen.add(tag)
                    data = _ask(url)
                    data.raise_for_status()
                    p = os.path.join(tmp, "%s-%s.ttf" % (found.replace(" ", ""), tag))
                    with open(p, "wb") as f:
                        f.write(data.content)
                    paths.append(p)
                added, already, problems = F.add_user_fonts(paths, install=install)
                if added or already:
                    result = ("downloaded", (added or already)[0])
                else:
                    result = ("failed", "; ".join(problems) or "the files weren't usable fonts")
    except Exception as e:
        log.warning("font download for %s failed: %s", family, e)
        result = ("failed", str(e)[:200])
    _tried[key] = result
    log.info("font %r: %s %s", family, *result)
    return result


def missing_families(items, root):
    """Font families used in items that this computer can't show."""
    import nobu_fonts as F
    have = {f.lower() for f in F.families(root)}
    out = []
    for it in items:
        for g in it.get("g", []):
            if g.startswith("ff:"):
                fam = g[3:].strip()
                if fam and fam.lower() not in have and fam not in out:
                    out.append(fam)
    return out


def message(results):
    """One popup's text for [(family, outcome, detail)]."""
    lines = []
    for fam, outcome, detail in results:
        if outcome == "downloaded":
            lines.append("✓  “%s” was downloaded (free, from Google Fonts) and is now in your font "
                         "list - the pasted text shows in it." % (detail or fam))
        elif outcome == "not_free":
            lines.append("✕  “%s” was not downloaded: there's no free, legal copy of it (it isn't on "
                         "Google Fonts - it's probably a paid font). The text keeps the font name, so it will show in "
                         "it on a computer that has it; here it shows in a similar font." % fam)
        else:
            lines.append("✕  “%s” was not downloaded: the download didn't work (%s). Try pasting again "
                         "later." % (fam, detail or "no internet?"))
    return "\n\n".join(lines)
