# United Kingdom legislation — LawCodex

Primary legislation of the **United Kingdom** (and its predecessor and devolved legislatures) as
plain Markdown, one file per Act, in the latest revised (consolidated) version published on
[legislation.gov.uk](https://www.legislation.gov.uk/) by The National Archives.

Part of [LawCodex](https://github.com/LawCodex): the legislation of every country as Markdown in git.

- Retrieved: {{DATE}}
- Files: {{TOTAL}} Markdown documents

## Coverage

| Directory | Category | Items listed on legislation.gov.uk | Items with XML text | Files here | revised, not repealed | marked repealed | enacted text only | Welsh-language files (`cy/`) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{{TABLE}}

Notes on the columns:

- *Items listed*: every item the legislation.gov.uk search feed lists for that type.
- *Items with XML text*: items for which legislation.gov.uk holds structured text. The remainder
  (mostly pre-1900 Acts long since repealed, and almost all Local and Private Acts) exist on
  legislation.gov.uk only as **scanned PDFs of the original print** and are **not included**.
- *revised, not repealed*: latest revised (consolidated, point-in-time) text, status `in_force`
  (this means the Act is not wholly repealed; individual provisions may be repealed, prospective or
  not yet commenced — see the text and annotations).
- *marked repealed*: legislation.gov.uk lists the Act as "(repealed)"; the file contains whatever
  text legislation.gov.uk still holds for it (often provisions replaced by ". . ." with the repeal
  annotation).
- *enacted text only*: no revised version exists on legislation.gov.uk; the file contains the text
  as originally enacted (`version: enacted`, `status: unknown`). This is the case for most Local
  Acts, Church Measures and many older or newly passed Acts.

## Not covered

- **Secondary legislation** — UK Statutory Instruments (`uksi`, ~109,000 items), Scottish SSIs,
  Welsh SIs, NI Statutory Rules, NI Orders in Council, etc. Mass-volume subordinate legislation is
  out of scope for LawCodex repositories; there is no bulk download, so including it would mean
  >150,000 API requests.
- **Retained / assimilated EU law** (`eur`, `eudr`, `eudn`) — not UK primary legislation.
- **PDF-only items** (see the table above): Local Acts (`ukla`) before ~1991, all
  `ukppa` and `gbla` items, and pre-1900 public Acts that were repealed before the Statute Law
  Database was created. They are only available as scanned images.
- **Annotations**: legislation.gov.uk attaches editorial annotations to the revised text. This
  corpus keeps textual-amendment notes (`F` notes), marginal citations (`M`) and editorial notes
  (`X`) as Markdown footnotes; it omits commencement (`I`), modification (`C`), extent (`E`) and
  subordinate-legislation (`P`) annotations.
- **Alternative versions**: where a provision has several versions in force at once (e.g. a
  different text for Scotland), only the default version legislation.gov.uk shows first is
  included. Images (figures, scanned original text of medieval statutes) are linked, not copied.
- **Explanatory notes**, tables of origins/destinations and impact assessments.

## Structure

```
ukpga/<year>/<year>-c<chapter>-<short-title>.md          UK Public General Acts
ukpga/<year>/<year>-<regnal-year>-c<chapter>-<title>.md   pre-1963 Acts cited by regnal year
asp/<year>/<year>-asp-<n>-<short-title>.md               Acts of the Scottish Parliament
asc/<year>/<year>-asc-<n>-...   anaw/<year>/<year>-anaw-<n>-...   mwa/<year>/<year>-nawm-<n>-...
nia/<year>/<year>-c<n>-...      apni/<year>/<year>-c<n>-...       mnia/<year>/<year>-no-<n>-...
ukcm/<year>/<year>-no-<n>-...   ukla/<year>/<year>-c<n>-...
aep/ aosp/ apgb/ aip/  <year>/<year>-<regnal-or-session>-c<n>-...   pre-Union Acts
cy/<type>/<year>/<same file name>.md                     Welsh-language text of Welsh legislation
```

Directory names are the legislation.gov.uk type codes, so `ukpga/1998/1998-c42-human-rights-act-1998.md`
corresponds to <https://www.legislation.gov.uk/ukpga/1998/42>. The `year` is the calendar year
legislation.gov.uk assigns to the Act.

Each file has YAML front matter:

```yaml
title: "Human Rights Act 1998"
identifier: "ukpga/1998/42"         # legislation.gov.uk path (ID URI: http://www.legislation.gov.uk/id/<identifier>)
citation: "1998 c. 42"
type: act                           # act | measure | church_measure
legislation_type: ukpga
jurisdiction: gb
language: en                        # en | cy | enm (Middle-English-era translations) ...
extent: "E+W+S+N.I."                # territorial extent as given by legislation.gov.uk
date: 1998-11-09                    # Royal Assent / enactment
last_amended: 2026-10-01            # date from which this revised version is valid
version: revised                    # revised (consolidated) | enacted (original text)
status: in_force                    # in_force | repealed | unknown
source: "https://www.legislation.gov.uk/ukpga/1998/42"
source_modified: 2026-10-07
retrieved: 2026-10-11
---
```

Body: the Act's number, long title, date of enactment and enacting formula; then Parts, Chapters,
cross-headings and Schedules as Markdown headings, sections as headings (`## 1 The Convention
Rights.` — deeper when inside Parts/Chapters, bold label beyond `######`), subsections and
paragraphs as `(1)`, `(a)`, `(i)` paragraphs, schedule paragraphs with bold numbers. Amended text
is wrapped in square brackets with a footnote reference at the opening bracket, as on
legislation.gov.uk (`[[^F1]Secretary of State]`); repealed text appears as `. . .`. Quoted
amending text is rendered as a blockquote. Simple tables are Markdown tables, tables with merged
cells are HTML. Mathematical formulae are linearised (`(A)/(B)`, `x<sup>2</sup>`).

## Source and licence

- Source: [legislation.gov.uk](https://www.legislation.gov.uk/) — The National Archives, via its
  [API](https://www.legislation.gov.uk/developer): Atom search feeds
  (`/<type>/data.feed`) for listing and the Crown Legislation Markup Language XML
  (`/<type>/<year>/<number>/data.xml`, plus `/welsh/data.xml` for Welsh texts) for content.
- The texts are Crown copyright (and Senedd Cymru / Scottish Parliament / NI Assembly copyright
  where applicable), reproduced under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  Contains public sector information licensed under the Open Government Licence v3.0.
- Revised legislation on legislation.gov.uk may not be fully up to date: some amendments are
  "yet to be applied" by the editorial team. Check the source page for the list of outstanding
  effects before relying on any text. This repository is not an official publication.

## Regenerating

```sh
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
cd scripts
python list_items.py      # Atom feeds -> ../../_raw/gb/index/<type>.json (feeds cached in _raw/gb/feeds; delete to refresh)
python fetch.py           # data.xml for every item with text -> ../../_raw/gb/xml/ (gzip, cached; delete to refresh)
python convert.py         # CLML -> Markdown into this repository
python make_readme.py     # README.md counts (from scripts/README.template.md)
```

The raw cache directory can be changed with `LAWCODEX_RAW`. The fetcher uses a descriptive
User-Agent, at most 3 concurrent connections and at least 0.4 s between requests (well under
legislation.gov.uk's throttle of 3,000 requests per 5 minutes), with exponential backoff on
errors and `Retry-After`. A full run is about 6,800 requests and 1–2 hours.
