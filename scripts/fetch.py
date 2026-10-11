#!/usr/bin/env python3
"""Step 2: download the latest available CLML XML (data.xml) of every item that has XML text.

legislation.gov.uk serves the latest revised (consolidated) version at /<path>/data.xml and
redirects to /<path>/enacted/data.xml when no revised version exists. Welsh-language versions of
Senedd/Assembly legislation are fetched from /<path>/welsh/data.xml.

Files are cached gzip-compressed in RAW/xml/<lang>/<path>.xml.gz; existing files are skipped.
Usage: fetch.py [type ...]   (default: all types in common.TYPES)
"""
import gzip
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import BASE, RAW, TYPES, get

WELSH_TYPES = {"asc", "anaw", "mwa"}
WORKERS = int(os.environ.get("LAWCODEX_WORKERS", "3"))


def target(path, lang):
    return os.path.join(RAW, "xml", lang, path + ".xml.gz")


def fetch_one(path, lang):
    out = target(path, lang)
    if os.path.exists(out):
        return "cached"
    url = f"{BASE}/{path}/{'welsh/' if lang == 'cy' else ''}data.xml"
    r = get(url, timeout=600)
    if r is None:
        return "404"
    data = r.content
    if b"<Legislation" not in data[:2000]:
        return "not-xml"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        f.write(data)
    os.replace(tmp, out)
    return "ok"


def main(types):
    jobs = []
    for t in types:
        items = json.load(open(os.path.join(RAW, "index", f"{t}.json")))
        for it in items:
            if not it["has_xml"]:
                continue
            jobs.append((it["path"], "en"))
            if t in WELSH_TYPES:
                jobs.append((it["path"], "cy"))
    print(f"{len(jobs)} jobs", file=sys.stderr)
    stats = {}
    failures = []
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(fetch_one, p, l): (p, l) for p, l in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            p, l = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = "error"
                failures.append(f"{l}\t{p}\t{e}")
            stats[res] = stats.get(res, 0) + 1
            if res not in ("cached",):
                print(f"[{n}/{len(jobs)}] {l} {p}: {res}", file=sys.stderr, flush=True)
    print(stats, file=sys.stderr)
    with open(os.path.join(RAW, "fetch_failures.tsv"), "a") as f:
        for x in failures:
            f.write(x + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] or TYPES)
