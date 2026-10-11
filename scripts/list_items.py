#!/usr/bin/env python3
"""Step 1: enumerate every item of each primary-legislation type via the Atom search feeds.

Writes RAW/index/<type>.json : list of dicts
  {id, path, title, year, number, regnal, has_xml, published}
`path` is the legislation.gov.uk path (e.g. "ukpga/1998/42", "ukpga/Vict/56-57/71").
`has_xml` is False for items for which legislation.gov.uk only holds a scanned PDF.
"""
import json
import os
import re
import sys

from lxml import etree

from common import BASE, RAW, TYPES, get

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "leg": "http://www.legislation.gov.uk/namespaces/legislation",
    "ukm": "http://www.legislation.gov.uk/namespaces/metadata",
}
PER_PAGE = 500


def list_type(t):
    feeddir = os.path.join(RAW, "feeds", t)
    os.makedirs(feeddir, exist_ok=True)
    items, page = [], 1
    while True:
        fn = os.path.join(feeddir, f"{page:04d}.xml")
        if os.path.exists(fn):
            data = open(fn, "rb").read()
        else:
            r = get(f"{BASE}/{t}/data.feed?results-count={PER_PAGE}&page={page}")
            data = r.content if r is not None else b""
            open(fn, "wb").write(data)
        if not data:
            break
        root = etree.fromstring(data)
        entries = root.findall("a:entry", NS)
        for e in entries:
            idu = e.findtext("a:id", namespaces=NS)
            path = re.sub(r"^https?://www\.legislation\.gov\.uk/id/", "", idu)
            types = {l.get("type") for l in e.findall("a:link", NS) if l.get("rel") == "alternate"}
            g = lambda tag: (e.find(tag, NS).get("Value") if e.find(tag, NS) is not None else None)
            reg = [x.get("Value") for x in e.findall("ukm:AlternativeNumber", NS) if x.get("Category") == "Regnal"]
            te = e.find("a:title", NS)
            title = " ".join("".join(te.itertext()).split()) if te is not None else ""
            spans = {sp.get("{http://www.w3.org/XML/1998/namespace}lang"): " ".join("".join(sp.itertext()).split())
                     for sp in (te.iter("{http://www.w3.org/1999/xhtml}span") if te is not None else [])}
            if spans.get("en"):
                title = spans["en"]
            items.append({
                "id": idu,
                "path": path,
                "title": title,
                "title_cy": spans.get("cy"),
                "year": g("ukm:Year"),
                "number": g("ukm:Number"),
                "regnal": reg[0] if reg else None,
                "has_xml": "application/xml" in types,
                "published": (e.findtext("a:published", namespaces=NS) or "")[:10],
            })
        more = root.findtext("leg:morePages", namespaces=NS)
        print(f"{t} page {page}: {len(entries)} entries (morePages={more})", file=sys.stderr)
        if not entries or not more or int(more) <= page:
            break
        page += 1
    # dedupe by path
    seen, out = set(), []
    for it in items:
        if it["path"] not in seen:
            seen.add(it["path"])
            out.append(it)
    os.makedirs(os.path.join(RAW, "index"), exist_ok=True)
    json.dump(out, open(os.path.join(RAW, "index", f"{t}.json"), "w"), indent=0)
    print(f"{t}: {len(out)} items, {sum(i['has_xml'] for i in out)} with XML text", file=sys.stderr)


if __name__ == "__main__":
    for t in sys.argv[1:] or TYPES:
        list_type(t)
