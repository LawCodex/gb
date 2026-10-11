#!/usr/bin/env python3
"""Step 3: convert cached CLML (Crown Legislation Markup Language) XML to Markdown.

Usage: convert.py [type ...]     (default: all types in common.TYPES)
Reads RAW/index/<type>.json and RAW/xml/<lang>/<path>.xml.gz, writes into the repository:
  <type>/<year>/<file>.md          English text
  cy/<type>/<year>/<file>.md       Welsh text (Senedd / Assembly legislation)
"""
import datetime
import gzip
import html
import json
import os
import re
import sys
import unicodedata
from multiprocessing import Pool

from lxml import etree

from common import RAW, ROOT, TYPES

TODAY = os.environ.get("LAWCODEX_DATE", datetime.date.today().isoformat())

# Annotation (commentary) types kept as footnotes. F = textual amendments, M = marginal
# citations, X = editorial notes on the text. C (modifications), I (commencement), E (extent)
# and P (subordinate legislation) annotations are omitted.
KEEP_COMMENTARY = {"F", "M", "X"}

DOC_TYPE = {
    "ukcm": "church_measure", "mwa": "measure", "mnia": "measure",
}
NUM_PREFIX = {"asp": "asp-", "asc": "asc-", "anaw": "anaw-", "mwa": "nawm-", "ukcm": "no-", "mnia": "no-"}

STRUCT = {"Group", "Part", "Chapter", "Pblock", "PsubBlock", "Schedule", "EUPart", "EUTitle",
          "EUChapter", "EUSection", "EUSubsection", "Division"}
LEVELS = {"P2": 2, "P3": 3, "P4": 4, "P5": 5, "P6": 6, "P7": 7}
SKIP = {"Metadata", "Contents", "Resources", "Commentaries", "Footnotes", "MarginNotes",
        "Versions", "Title", "Number", "Pnumber", "TitleBlock", "Reference", "Subtitle"}


def ln(el):
    t = el.tag
    if not isinstance(t, str):
        return ""
    return t.rsplit("}", 1)[-1]


def esc(s):
    s = s.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_").replace("<", "&lt;")
    return s


def norm_ws(s):
    return re.sub(r"[ \t\r\n]+", " ", s)


def math_text(el):
    n = ln(el)
    kids = [c for c in el if isinstance(c.tag, str)]
    if n == "mfrac" and len(kids) == 2:
        return f"({math_text(kids[0])})/({math_text(kids[1])})"
    if n in ("msub", "munder") and len(kids) == 2:
        return f"{math_text(kids[0])}<sub>{math_text(kids[1])}</sub>"
    if n in ("msup", "mover") and len(kids) == 2:
        return f"{math_text(kids[0])}<sup>{math_text(kids[1])}</sup>"
    if n in ("msubsup", "munderover") and len(kids) == 3:
        return f"{math_text(kids[0])}<sub>{math_text(kids[1])}</sub><sup>{math_text(kids[2])}</sup>"
    if n == "msqrt":
        return "√(" + "".join(math_text(k) for k in kids) + ")"
    if n == "mroot" and len(kids) == 2:
        return f"<sup>{math_text(kids[1])}</sup>√({math_text(kids[0])})"
    if n == "mfenced":
        o, c = el.get("open", "("), el.get("close", ")")
        return o + ", ".join(math_text(k) for k in kids) + c
    if n in ("mi", "mn", "mo", "mtext", "ms"):
        t = norm_ws("".join(el.itertext())).strip()
        return f" {t} " if n == "mo" and t in ("=", "+", "−", "-", "×", "÷", "<", ">", "≤", "≥") else t
    if n == "mspace":
        return " "
    if n == "mtable":
        return "; ".join(math_text(k) for k in kids)
    return "".join(math_text(k) for k in kids)


class Doc:
    def __init__(self, root, lang):
        self.root = root
        self.lang = lang
        self.comm = {}
        for c in root.iter("{*}Commentary"):
            self.comm[c.get("id")] = c
        self.fn = {f.get("id"): f for f in root.iter("{*}Footnote")}
        self.mn = {f.get("id"): f for f in root.iter("{*}MarginNote")}
        self.res = {}
        for r in root.iter("{*}Resource"):
            ev = r.find("{*}ExternalVersion")
            if ev is not None:
                self.res[r.get("id")] = ev.get("URI")
        self.notes = []          # (label, element) in order of first reference
        self.note_label = {}
        self.counters = {}
        self.in_schedule = 0
        # amendment spans: open bracket at first element of a ChangeId, close at the last one
        self.first, self.last = {}, {}
        for i, e in enumerate(root.iter("{*}Addition", "{*}Substitution")):
            cid = e.get("ChangeId")
            if cid:
                self.first.setdefault(cid, e)
                self.last[cid] = e

    # ---------- notes ----------
    def note(self, kind, ref):
        key = (kind, ref)
        if key in self.note_label:
            return f"[^{self.note_label[key]}]"
        if kind == "c":
            c = self.comm.get(ref)
            if c is None or c.get("Type") not in KEEP_COMMENTARY:
                return ""
            prefix = c.get("Type")
        elif kind == "f":
            c = self.fn.get(ref)
            if c is None:
                return ""
            prefix = "n"
        else:
            c = self.mn.get(ref)
            if c is None:
                return ""
            prefix = "M"
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        label = f"{prefix}{self.counters[prefix]}"
        self.note_label[key] = label
        self.notes.append((label, kind, c))
        return f"[^{label}]"

    # ---------- inline ----------
    def inline(self, el, with_tail=False):
        out = []
        if el.text:
            out.append(esc(norm_ws(el.text)))
        for c in el:
            out.append(self.inline_el(c))
            if c.tail:
                out.append(esc(norm_ws(c.tail)))
        s = "".join(out)
        return s

    def inline_el(self, c):
        n = ln(c)
        if not n:
            return ""
        if n == "CommentaryRef":
            return self.note("c", c.get("Ref"))
        if n == "FootnoteRef":
            return self.note("f", c.get("Ref"))
        if n == "MarginNoteRef":
            return self.note("m", c.get("Ref"))
        if n in ("Addition", "Substitution"):
            cid = c.get("ChangeId")
            opening = cid is None or self.first.get(cid) is c
            closing = cid is None or self.last.get(cid) is c
            m = self.note("c", c.get("CommentaryRef")) if (c.get("CommentaryRef") and opening) else ""
            return ("[" + m if opening else "") + self.inline(c) + ("]" if closing else "")
        if n == "Repeal":
            m = self.note("c", c.get("CommentaryRef")) if c.get("CommentaryRef") else ""
            return m + self.inline(c)
        if n == "Emphasis":
            return wrap(self.inline(c), "*")
        if n == "Strong":
            return wrap(self.inline(c), "**")
        if n == "Superior":
            return f"<sup>{self.inline(c)}</sup>"
        if n == "Inferior":
            return f"<sub>{self.inline(c)}</sub>"
        if n == "Character":
            name = c.get("Name")
            return {"NonBreakingSpace": " ", "EmSpace": " ", "EnSpace": " ",
                    "DotPadding": " . . . ", "LinePadding": " ", "Minus": "−",
                    "ThinSpace": " "}.get(name, " ")
        if n == "math":
            return math_text(c)
        if n == "Image":
            uri = self.res.get(c.get("ResourceRef"), "")
            return f"![image]({uri})" if uri else ""
        if n == "Break":
            return "<br>"
        if n in ("Text", "Para", "P", "BlockText", "Title", "Pnumber"):
            return " " + self.inline(c) + " "
        if n in ("Footnote", "MarginNote", "Commentary"):
            return ""
        if n in ("UnorderedList", "OrderedList", "Tabular", "Figure", "BlockAmendment",
                 "BlockExtract"):
            return " " + " ".join(b.replace("\n", " ") for b in self.blocks(c)) + " "
        # Citation, CitationSubRef, Term, Definition, Acronym, Abbreviation, Span, SmallCaps,
        # Underline, InlineAmendment, InternalLink, Expanded, Uppercase, ...
        return self.inline(c)

    def clean(self, s):
        s = re.sub(r" {2,}", " ", s).strip()
        return s

    # ---------- blocks ----------
    def heading(self, level, text):
        text = self.clean(text)
        # drop typographic emphasis inside headings
        text = re.sub(r"(?<!\\)\*\*(.+?)(?<!\\)\*\*", r"\1", text)
        text = re.sub(r"(?<![\\*])\*(?!\*)(.+?)(?<!\\)\*(?!\*)", r"\1", text)
        if not text:
            return []
        if level <= 6:
            return ["#" * level + " " + text]
        return [f"**{text}**"]

    def label_of(self, el):
        pn = el.find("{*}Pnumber")
        if pn is None:
            return ""
        t = self.clean(self.inline(pn))
        return t

    def blocks(self, el, level=2):
        """Return list of Markdown blocks for element el."""
        n = ln(el)
        if not n or n in SKIP:
            return []
        out = []
        if n in STRUCT:
            num = el.find("{*}Number")
            title = el.find("{*}Title")
            if title is None:
                tb = el.find("{*}TitleBlock")
                if tb is not None:
                    title = tb.find("{*}Title")
            parts = []
            if num is not None:
                parts.append(self.clean(self.inline(num)))
            if title is not None:
                parts.append(self.clean(self.inline(title)))
            h = " — ".join(p for p in parts if p) if num is not None and title is not None else " ".join(p for p in parts if p)
            if el.get("Status") == "Prospective":
                h += " (prospective)"
            out += self.heading(level, h)
            ref = el.find("{*}Reference")
            if ref is not None:
                out.append("*" + self.clean(self.inline(ref)) + "*")
            if n == "Schedule":
                self.in_schedule += 1
            for c in el:
                out += self.blocks(c, level + 1 if h.strip() else level)
            if n == "Schedule":
                self.in_schedule -= 1
            return out
        if n == "P1group":
            title = el.find("{*}Title")
            p1s = [c for c in el if ln(c) == "P1"]
            ttl = self.clean(self.inline(title)) if title is not None else ""
            prosp = " (prospective)" if (el.get("Status") == "Prospective" or any(p.get("Status") == "Prospective" for p in p1s)) else ""
            if len(p1s) == 1 and not self.in_schedule:
                lab = self.label_of(p1s[0])
                out += self.heading(level, (lab + " " + ttl).strip() + prosp)
                for c in el:
                    if ln(c) == "P1":
                        out += self.p_content(c, level + 1)
                    else:
                        out += self.blocks(c, level + 1)
            else:
                out += self.heading(level, ttl + prosp)
                for c in el:
                    out += self.blocks(c, level + 1)
            return out
        if n == "P1":
            lab = self.label_of(el)
            if not self.in_schedule and level <= 6 and lab:
                out += self.heading(level, lab + (" (prospective)" if el.get("Status") == "Prospective" else ""))
                out += self.p_content(el, level + 1)
                return out
            return self.p_content(el, level, label=f"**{lab}**" if lab else "")
        if n in LEVELS or n == "P":
            lab = self.label_of(el)
            if lab and n in LEVELS:
                lab = paren_label(lab)
            return self.p_content(el, level, label=lab)
        if n in ("Text",):
            t = self.clean(self.inline(el))
            return [t] if t else []
        if n in ("UnorderedList", "OrderedList"):
            return self.list_blocks(el, level)
        if n == "Tabular":
            return self.table_blocks(el)
        if n in ("table",):
            return self.table_blocks(el.getparent()) if False else self.table_from(el)
        if n == "Figure":
            for c in el:
                out += self.blocks(c, level)
            return out
        if n == "Image":
            uri = self.res.get(el.get("ResourceRef"), "")
            return [f"![image]({uri})"] if uri else []
        if n in ("BlockAmendment", "BlockExtract"):
            inner = []
            for c in el:
                inner += self.blocks(c, 99)
            q = []
            for b in inner:
                q.append("\n".join("> " + line if line else ">" for line in b.split("\n")))
            return ["\n>\n".join(q)] if q else []
        if n == "AppendText":
            t = self.clean(self.inline(el))
            return [t] if t else []
        if n == "Formula":
            t = self.clean(self.inline(el))
            return [t] if t else []
        if n in ("LongTitle", "DateOfEnactment", "IntroductoryText", "EnactingText",
                 "EnactingTextOmitted", "SignedSection", "Signee"):
            if len(el) == 0 or all(ln(c) in ("CommentaryRef", "DateText", "Emphasis", "Strong", "Citation", "Addition", "Substitution", "Repeal") for c in el):
                t = self.clean(self.inline(el))
                return [t] if t else []
        # generic container (Primary, Body, Schedules, ScheduleBody, Para, P1para, BlockText, ...)
        if el.text and el.text.strip():
            out.append(self.clean(esc(norm_ws(el.text))))
        for c in el:
            out += self.blocks(c, level)
            if c.tail and c.tail.strip() and ln(c) not in ("CommentaryRef",):
                out.append(self.clean(esc(norm_ws(c.tail))))
        return out

    def p_content(self, el, level, label=""):
        """Content of a numbered paragraph; prefix the first block with its label."""
        out = []
        for c in el:
            n = ln(c)
            if n in ("Pnumber", "Title"):
                if n == "Title":
                    t = self.clean(self.inline(c))
                    if t:
                        out.append(f"*{t}*")
                continue
            out += self.blocks(c, level)
        if label:
            if out and not out[0].startswith(("#", ">", "|", "<table", "- ", "**")):
                out[0] = f"{label} {out[0]}"
            else:
                out.insert(0, label)
        return out

    def list_blocks(self, el, level):
        items = []
        dec = el.get("Decoration", "none")
        for li in el:
            if ln(li) != "ListItem":
                continue
            inner = []
            for c in li:
                inner += self.blocks(c, 99)
            num = li.get("NumberOverride")
            lab = ""
            if num:
                lab = {"parens": f"({num})", "brackets": f"[{num}]", "parenRight": f"{num})",
                       "period": f"{num}.", "colon": f"{num}:"}.get(dec, num) + " "
            if not inner:
                inner = [""]
            first = "- " + lab + inner[0].replace("\n", "\n  ")
            rest = ["  " + b.replace("\n", "\n  ") for b in inner[1:]]
            items.append("\n\n".join([first] + rest) if rest else first)
        return ["\n".join(items) if all("\n\n" not in i for i in items) else "\n\n".join(items)] if items else []

    # ---------- tables ----------
    def table_blocks(self, el):
        out = []
        for c in el.iter():
            if ln(c) == "table":
                out += self.table_from(c)
                break
        return out

    def cell_text(self, cell):
        parts = []
        if cell.text and cell.text.strip():
            parts.append(esc(norm_ws(cell.text)))
        for c in cell:
            n = ln(c)
            if n in ("Para", "P", "Text", "BlockText", "UnorderedList", "OrderedList", "P2", "P3", "P4", "P1", "Tabular", "Footnote"):
                if n == "Footnote":
                    pass
                else:
                    bl = self.blocks(c, 99)
                    parts.append("<br>".join(b.replace("\n", "<br>") for b in bl))
            else:
                parts.append(self.inline_el(c))
            if c.tail and c.tail.strip():
                parts.append(esc(norm_ws(c.tail)))
        return self.clean(" ".join(p for p in parts if p))

    def table_from(self, table):
        rows = []
        complex_ = False
        for sect in ("thead", "tbody", "tfoot"):
            for s in table.iter("{*}" + sect):
                for tr in s.iter("{*}tr"):
                    cells = []
                    for td in tr:
                        if ln(td) not in ("td", "th"):
                            continue
                        if int(td.get("colspan", "1") or 1) > 1 or int(td.get("rowspan", "1") or 1) > 1:
                            complex_ = True
                        cells.append((ln(td), td))
                    rows.append((sect, cells))
        if not rows:
            for tr in table.iter("{*}tr"):
                rows.append(("tbody", [(ln(td), td) for td in tr if ln(td) in ("td", "th")]))
        # footnotes inside tables
        for f in table.iter("{*}Footnote"):
            pass
        if not rows:
            return []
        widths = {len(c) for _, c in rows}
        if len(widths) > 1:
            complex_ = True
        if not complex_:
            texts = [[self.cell_text(td).replace("|", "\\|") for _, td in cells] for _, cells in rows]
            ncol = max(len(r) for r in texts)
            if ncol == 0:
                return []
            head_rows = [i for i, (s, _) in enumerate(rows) if s == "thead"]
            if head_rows:
                head = texts[head_rows[-1]]
                body = [t for i, t in enumerate(texts) if i not in head_rows[:-1] and i != head_rows[-1]]
                pre = [texts[i] for i in head_rows[:-1]]
                body = pre + body if pre else body
            else:
                head = [""] * ncol
                body = texts
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * ncol]
            for r in body:
                lines.append("| " + " | ".join(r + [""] * (ncol - len(r))) + " |")
            return ["\n".join(lines)]
        # complex table -> HTML
        h = ["<table>"]
        cur = None
        for sect, cells in rows:
            if sect != cur:
                if cur:
                    h.append(f"</{cur}>")
                h.append(f"<{sect}>")
                cur = sect
            tds = []
            for tag, td in cells:
                attrs = ""
                for a in ("colspan", "rowspan"):
                    v = td.get(a)
                    if v and v != "1":
                        attrs += f' {a}="{v}"'
                txt = self.cell_text(td)
                txt = txt.replace("\\*", "*").replace("\\_", "_").replace("\\\\", "\\")
                txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
                txt = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<i>\1</i>", txt)
                tds.append(f"<{tag}{attrs}>{txt}</{tag}>")
            h.append("<tr>" + "".join(tds) + "</tr>")
        if cur:
            h.append(f"</{cur}>")
        h.append("</table>")
        return ["\n".join(h)]

    # ---------- notes rendering ----------
    def render_notes(self):
        out = []
        i = 0
        while i < len(self.notes):  # notes may reference further notes
            label, kind, el = self.notes[i]
            if kind == "f":
                body = [b for c in el if ln(c) == "FootnoteText" for b in self.blocks(c, 99)]
            else:
                body = []
                for c in el:
                    body += self.blocks(c, 99)
            txt = " ".join(b.replace("\n", " ") for b in body)
            out.append(f"[^{label}]: {self.clean(txt)}")
            i += 1
        return out


def wrap(t, mark):
    core = t.strip()
    if not core:
        return t
    lead = t[: len(t) - len(t.lstrip())]
    trail = t[len(t.rstrip()):]
    return f"{lead}{mark}{core}{mark}{trail}"


def paren_label(lab):
    m = re.match(r"^((?:\[(?:\[\^\w+\])*)*)(.*?)(\]*)$", lab)
    pre, core, post = m.groups()
    if not core or core.startswith("(") or not re.match(r"^[\w.]", core):
        return lab
    return f"{pre}({core}){post}"


def slugify(s, maxlen):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s


def file_name(t, it):
    parts = it["path"].split("/")
    year = it["year"] or ""
    title = re.sub(r"\s*\(repealed\)\s*$", "", it["title"])
    if len(parts) == 3 and parts[1].isdigit():
        num = parts[2]
        base = f"{parts[1]}-{NUM_PREFIX.get(t, 'c')}{num}"
        year = year or parts[1]
    else:
        reg = slugify("-".join(parts[1:-1]), 40)
        base = f"{year}-{reg}-c{parts[-1]}" if year else f"{reg}-c{parts[-1]}"
    slug = slugify(title, max(20, 96 - len(base)))
    return year or "unknown", f"{base}-{slug}" if slug else base


def yq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def convert(job):
    t, it, lang = job
    src = os.path.join(RAW, "xml", lang, it["path"] + ".xml.gz")
    if not os.path.exists(src):
        return (t, lang, it["path"], "missing", None)
    try:
        root = etree.fromstring(gzip.open(src).read(), etree.XMLParser(huge_tree=True, recover=True))
    except Exception as e:  # noqa: BLE001
        return (t, lang, it["path"], f"parse-error {e}", None)
    md = root.find("{*}Metadata")

    def mtext(tag):
        if md is None:
            return None
        e = md.find(".//{*}" + tag)
        return e.text.strip() if e is not None and e.text else None

    def mattr(tag, attr="Value"):
        if md is None:
            return None
        e = md.find(".//{*}" + tag)
        return e.get(attr) if e is not None else None

    doc = Doc(root, lang)
    title = mtext("title") or it["title"]
    title = norm_ws(re.sub(r"\s*\(repealed\)\s*$", "", title)).strip()
    status_doc = mattr("DocumentStatus") or ""
    repealed = it["title"].rstrip().endswith("(repealed)")
    if repealed:
        status = "repealed"
    elif status_doc == "revised":
        status = "in_force"
    else:
        status = "unknown"
    enact = mattr("EnactmentDate", "Date") or it.get("published") or ""
    valid = mtext("valid") if status_doc == "revised" else None
    modified = mtext("modified")
    prelims = root.find(".//{*}PrimaryPrelims")
    citation = None
    if prelims is not None and prelims.find("{*}Number") is not None:
        citation = doc.clean(norm_ws("".join(prelims.find("{*}Number").itertext())))
    extent = root.get("RestrictExtent")

    body_blocks = []
    main = root.find("{*}Primary")
    if main is None:
        main = root.find("{*}Secondary")
    if main is None:
        main = root.find("{*}EURetained")
    if main is not None:
        for c in main:
            n = ln(c)
            if n in ("PrimaryPrelims", "SecondaryPrelims"):
                for cc in c:
                    nn = ln(cc)
                    if nn in ("Title",):
                        continue
                    if nn == "Number":
                        body_blocks.append("**" + doc.clean(doc.inline(cc)) + "**")
                    elif nn in ("PrimaryPreamble", "SecondaryPreamble"):
                        body_blocks += doc.blocks(cc, 2)
                    else:
                        body_blocks += doc.blocks(cc, 2)
            else:
                body_blocks += doc.blocks(c, 2)
    if not any(b.strip() for b in body_blocks):
        return (t, lang, it["path"], "empty", None)
    notes = doc.render_notes()

    year, fname = file_name(t, it)
    rel = os.path.join(*( ["cy"] if lang == "cy" else []), t, year, fname + ".md")
    src_url = f"https://www.legislation.gov.uk/{it['path']}" + ("/welsh" if lang == "cy" else "")
    fm = ["---", f"title: {yq(title)}",
          f"identifier: {yq(it['path'])}"]
    if citation:
        fm.append(f"citation: {yq(citation)}")
    fm += [f"type: {DOC_TYPE.get(t, 'act')}",
           f"legislation_type: {t}",
           "jurisdiction: gb",
           f"language: {(mtext('language') or lang)}"]
    if extent:
        fm.append(f"extent: {yq(extent)}")
    if enact:
        fm.append(f"date: {enact}")
    if valid:
        fm.append(f"last_amended: {valid}")
    fm.append(f"version: {'revised' if status_doc == 'revised' else 'enacted'}")
    fm.append(f"status: {status}")
    fm.append(f"source: {yq(src_url)}")
    if modified:
        fm.append(f"source_modified: {modified}")
    fm.append(f"retrieved: {TODAY}")
    fm.append("---")
    text = "\n".join(fm) + "\n\n# " + title + "\n\n" + "\n\n".join(b for b in body_blocks if b.strip()) + "\n"
    if notes:
        text += "\n---\n\n" + "\n".join(notes) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    dst = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return (t, lang, it["path"], "ok", rel)


def main(types):
    jobs = []
    for t in types:
        items = json.load(open(os.path.join(RAW, "index", f"{t}.json")))
        for it in items:
            if it["has_xml"]:
                jobs.append((t, it, "en"))
                if os.path.exists(os.path.join(RAW, "xml", "cy", it["path"] + ".xml.gz")):
                    jobs.append((t, it, "cy"))
    results = []
    with Pool(int(os.environ.get("LAWCODEX_PROCS", "6"))) as p:
        for r in p.imap_unordered(convert, jobs, chunksize=4):
            results.append(r)
            if r[3] != "ok":
                print("\t".join(r[:4]), file=sys.stderr)
    seen = {}
    for r in results:
        if r[4]:
            if r[4] in seen:
                print(f"COLLISION {r[4]}: {seen[r[4]]} vs {r[2]}", file=sys.stderr)
            seen[r[4]] = r[2]
    stats = {}
    for r in results:
        k = (r[0], r[1], r[3].split()[0])
        stats[k] = stats.get(k, 0) + 1
    for k in sorted(stats):
        print(*k, stats[k], file=sys.stderr)
    os.makedirs(os.path.join(RAW, "reports"), exist_ok=True)
    with open(os.path.join(RAW, "reports", "convert-" + "-".join(types) + ".json"), "w") as f:
        json.dump([r[:4] for r in results], f)


if __name__ == "__main__":
    main(sys.argv[1:] or TYPES)
