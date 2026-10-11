#!/usr/bin/env python3
"""Step 4: regenerate README.md with per-category counts from the files in the repository
and the listing indexes in RAW/index (for the "not available as text" counts)."""
import json
import os
import re
import datetime

from common import RAW, ROOT

CATS = [
    ("ukpga", "UK Public General Acts (1235–present; Parliament of England/GB/UK as revised by legislation.gov.uk)"),
    ("ukla", "UK Local Acts"),
    ("ukppa", "UK Private and Personal Acts"),
    ("ukcm", "Church Measures (Church Assembly / General Synod)"),
    ("aep", "Acts of the English Parliament (to 1707)"),
    ("aosp", "Acts of the Old Scottish Parliament (to 1707)"),
    ("apgb", "Acts of the Parliament of Great Britain (1707–1800)"),
    ("gbla", "Local Acts of the Parliament of Great Britain"),
    ("aip", "Acts of the Old Irish Parliament (to 1800)"),
    ("asp", "Acts of the Scottish Parliament (1999–)"),
    ("asc", "Acts of Senedd Cymru (2020–)"),
    ("anaw", "Acts of the National Assembly for Wales (2012–2020)"),
    ("mwa", "Measures of the National Assembly for Wales (2008–2011)"),
    ("nia", "Acts of the Northern Ireland Assembly (2000–)"),
    ("mnia", "Measures of the Northern Ireland Assembly (1974)"),
    ("apni", "Acts of the Parliament of Northern Ireland (1921–1972)"),
]


def count_files(d):
    n, status = 0, {}
    if not os.path.isdir(d):
        return 0, status
    for dp, _, fs in os.walk(d):
        for f in fs:
            if f.endswith(".md"):
                n += 1
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    head = fh.read(1500)
                m = re.search(r"^status: (\w+)", head, re.M)
                s = m.group(1) if m else "unknown"
                v = re.search(r"^version: (\w+)", head, re.M)
                key = (s, v.group(1) if v else "?")
                status[key] = status.get(key, 0) + 1
    return n, status


def main():
    rows = []
    tot = {"listed": 0, "xml": 0, "files": 0, "cy": 0}
    for t, label in CATS:
        idx = os.path.join(RAW, "index", f"{t}.json")
        items = json.load(open(idx)) if os.path.exists(idx) else []
        listed = len(items)
        xml = sum(1 for i in items if i["has_xml"])
        n, st = count_files(os.path.join(ROOT, t))
        ncy, _ = count_files(os.path.join(ROOT, "cy", t))
        rev_in = st.get(("in_force", "revised"), 0)
        rep = sum(v for (s, _), v in st.items() if s == "repealed")
        enacted = sum(v for (_, ver), v in st.items() if ver == "enacted")
        rows.append(f"| `{t}/` | {label} | {listed} | {xml} | **{n}** | {rev_in} | {rep} | {enacted} | {ncy or ''} |")
        tot["listed"] += listed
        tot["xml"] += xml
        tot["files"] += n
        tot["cy"] += ncy
    rows.append(f"| | **Total** | {tot['listed']} | {tot['xml']} | **{tot['files']}** | | | | {tot['cy']} |")
    table = "\n".join(rows)
    today = os.environ.get("LAWCODEX_DATE", datetime.date.today().isoformat())
    readme = open(os.path.join(ROOT, "scripts", "README.template.md"), encoding="utf-8").read()
    readme = readme.replace("{{TABLE}}", table).replace("{{DATE}}", today)
    readme = readme.replace("{{TOTAL}}", str(tot["files"] + tot["cy"]))
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(readme)


if __name__ == "__main__":
    main()
