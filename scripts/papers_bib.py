#!/usr/bin/env python3
"""
papers_bib.py — manage assets/bibliography/papers.bib

Run with no arguments to enter an interactive curses browser:

    python3 scripts/papers_bib.py

In the browser you can ↑/↓ through every entry, ENTER one to view its
fields, toggle selected/featured with s/f, regenerate html_venue with v,
re-fetch from the web with u, and pick the trailing "[+ Add new]" item
to insert a new publication. Changes are auto-saved on exit.

Non-interactive subcommands (for scripting):

  add  <DOI|URL|TITLE>      Fetch via CrossRef (DOI given) or DBLP search
                            (interactive picker). If the DOI matches an
                            existing entry, merge — preserving user-curated
                            fields (selected, featured, rank, month,
                            html_venue). Otherwise insert a new entry with
                            an al-folio citekey (lastnameYEARfirstword),
                            `selected = {true}`, and auto html_venue.

  update <citekey>          Re-fetch the entry via its stored DOI, merge.

  toggle <selected|featured> <citekey>
                            Flip the named boolean field on/off.

  venue  <citekey>          Regenerate html_venue from current fields.
  venue-all                 Regenerate html_venue for every entry that
                            would change; prints a diff.

  list                      List all entries with flags + ranks.

Stdlib only. Python 3.10+.
"""
import argparse
import json
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

BIB_PATH = Path(__file__).resolve().parent.parent / "assets/bibliography/papers.bib"

STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "for", "in", "on",
             "with", "is", "are", "as", "at", "by", "from", "into"}

SUPPRESS_PUBLISHERS = {"CEUR-WS.org", "AAAI Press", "AAAI", "IEEE", "Elsevier"}
ACK_PUBLISHERS_NO_VOL = {"ACM"}

USER_FIELDS = {"selected", "featured", "rank", "month", "html_venue"}

STANDARD_FIELD_ORDER = [
    "title", "author",
    "booktitle", "journal",
    "year", "month",
    "series", "volume", "number", "pages",
    "publisher", "doi", "url",
    "rank", "selected", "featured",
    "html_venue",
]

UA = "papers_bib.py (https://thingoctrangtran.github.io; mailto:trang.tran@tugraz.at)"


# ─────────────────────────────────────────────────────────────── BibTeX I/O ──

class Entry:
    __slots__ = ("type", "key", "fields")

    def __init__(self, type_: str, key: str, fields: "OrderedDict[str, str]"):
        self.type = type_
        self.key = key
        self.fields = fields


def parse_bib(text: str):
    entries = []
    trailing_buf = []
    pos = 0
    n = len(text)

    while pos < n:
        header_start = pos
        while pos < n:
            ch = text[pos]
            if ch in " \t\r\n":
                pos += 1
            elif ch == "%":
                nl = text.find("\n", pos)
                pos = n if nl == -1 else nl + 1
            elif text[pos:pos + 8].lower() == "@comment":
                br = text.find("{", pos)
                if br == -1:
                    pos = n
                    break
                d, i = 1, br + 1
                while i < n and d > 0:
                    if text[i] == "{":
                        d += 1
                    elif text[i] == "}":
                        d -= 1
                    i += 1
                pos = i
            else:
                break
        header = text[header_start:pos]

        if pos >= n:
            trailing_buf.append(header)
            break

        m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text[pos:])
        if not m:
            pos += 1
            continue
        type_, key = m.group(1).lower(), m.group(2)
        i = pos + m.end()

        fields = OrderedDict()
        while i < n:
            while i < n and text[i] in " \t\r\n,":
                i += 1
            if i >= n:
                break
            if text[i] == "}":
                i += 1
                break
            fm = re.match(r"(\w+)\s*=\s*", text[i:])
            if not fm:
                i = text.find("}", i)
                i = n if i == -1 else i + 1
                break
            fname = fm.group(1).lower()
            i += fm.end()
            if text[i] == "{":
                d, j = 1, i + 1
                while j < n and d > 0:
                    if text[j] == "{":
                        d += 1
                    elif text[j] == "}":
                        d -= 1
                        if d == 0:
                            break
                    j += 1
                fvalue = text[i + 1:j]
                i = j + 1
            elif text[i] == '"':
                j = i + 1
                while j < n and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
                fvalue = text[i + 1:j]
                i = j + 1
            else:
                j = i
                while j < n and text[j] not in ",}\n":
                    j += 1
                fvalue = text[i:j].strip()
                i = j
            fields[fname] = fvalue.strip()
        entries.append((header, Entry(type_, key, fields)))
        pos = i

    return entries, "".join(trailing_buf)


def format_entry(entry: Entry, indent: str = "  ") -> str:
    items = list(entry.fields.items())
    if not items:
        return f"@{entry.type}{{{entry.key},\n}}"
    width = max(len(k) for k, _ in items)
    lines = [f"@{entry.type}{{{entry.key},"]
    for i, (k, v) in enumerate(items):
        sep = "," if i < len(items) - 1 else ""
        lines.append(f"{indent}{k.ljust(width)} = {{{v}}}{sep}")
    lines.append("}")
    return "\n".join(lines)


def order_fields(fields: "OrderedDict[str, str]") -> "OrderedDict[str, str]":
    out = OrderedDict()
    remaining = OrderedDict(fields)
    for f in STANDARD_FIELD_ORDER:
        if f in remaining:
            out[f] = remaining.pop(f)
    for f, v in remaining.items():
        out[f] = v
    return out


# ───────────────────────────────────────────────────────────── Web fetching ──

def http_get(url: str, headers=None, timeout: int = 25) -> str:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_crossref_bibtex(doi: str):
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/')}/transform/application/x-bibtex"
    try:
        return http_get(url, headers={"Accept": "application/x-bibtex"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_dblp_hits(query: str, limit: int = 8) -> list:
    url = f"https://dblp.org/search/publ/api?q={urllib.parse.quote(query)}&format=json&h={limit}"
    raw = http_get(url)
    data = json.loads(raw)
    return data.get("result", {}).get("hits", {}).get("hit", []) or []


def fetch_dblp_bibtex_from_record(record_url: str):
    bib_url = record_url[:-5] + ".bib" if record_url.endswith(".html") else record_url + ".bib"
    return http_get(bib_url)


def normalize_doi(s: str):
    m = re.search(r"10\.\d{4,9}/[^\s)>\"<]+", s)
    return m.group(0).rstrip("/.") if m else None


def fetch_bib(arg: str):
    doi = normalize_doi(arg)
    if doi:
        sys.stderr.write(f"→ DOI detected: {doi}\n→ CrossRef…\n")
        bib = fetch_crossref_bibtex(doi)
        if bib:
            return bib, f"crossref ({doi})"
        sys.stderr.write("  (CrossRef miss, falling back to DBLP)\n")

    sys.stderr.write(f"→ Searching DBLP for: {arg!r}\n")
    hits = fetch_dblp_hits(arg)
    if not hits:
        return None, "no DBLP hits"

    if doi:
        for h in hits:
            if h.get("info", {}).get("doi", "").lower() == doi.lower():
                rec = h["info"].get("url", "")
                if rec:
                    return fetch_dblp_bibtex_from_record(rec), f"dblp ({doi})"

    sys.stderr.write("\nDBLP candidates:\n")
    for i, h in enumerate(hits[:8], 1):
        info = h.get("info", {})
        sys.stderr.write(f"  [{i}] {info.get('title', '')[:78]}\n")
        sys.stderr.write(f"      {info.get('venue', '')} {info.get('year', '')}  doi={info.get('doi', '')}\n")
    sys.stderr.write("Pick number (or s to skip): ")
    pick = input().strip().lower()
    if pick == "s":
        return None, "skipped by user"
    try:
        idx = int(pick) - 1
        rec = hits[idx]["info"].get("url", "")
    except (ValueError, IndexError, KeyError):
        return None, "invalid pick"
    if not rec:
        return None, "DBLP hit has no record URL"
    return fetch_dblp_bibtex_from_record(rec), f"dblp #{idx + 1}"


# ──────────────────────────────────────────────────── html_venue generation ──

def gen_html_venue(entry: Entry) -> str:
    f = entry.fields
    t = entry.type.lower()
    head = f.get("journal", "") if t == "article" else f.get("booktitle", "")
    out = f"<em>{head}</em>"
    series = f.get("series")
    volume = f.get("volume")
    number = f.get("number")
    publisher = f.get("publisher")
    if series:
        out += f". {series}"
        if volume:
            out += f", vol. {volume}"
        if publisher and publisher not in SUPPRESS_PUBLISHERS:
            out += f". {publisher}"
    elif volume:
        out += f", vol. {volume}"
        if number:
            out += f", no. {number}"
    elif publisher and publisher in ACK_PUBLISHERS_NO_VOL:
        out += f". {publisher}"
    pages = f.get("pages", "")
    if pages:
        norm = pages.replace("--", "–").strip()
        out += f", pp. {norm}" if "–" in norm else f", p. {norm}"
    return out


def gen_citekey(entry: Entry) -> str:
    author = entry.fields.get("author", "")
    year = entry.fields.get("year", "XXXX").strip()
    title = entry.fields.get("title", "")
    first = author.split(" and ")[0].strip()
    if "," in first:
        surname = first.split(",")[0].strip()
    elif first.split():
        surname = first.split()[-1]
    else:
        surname = "unknown"
    surname = re.sub(r"[^A-Za-z]", "", surname).lower()
    words = re.findall(r"\w+", re.sub(r"[{}\\']", "", title))
    fw = next((w for w in words if w.lower() not in STOPWORDS), "paper")
    fw = re.sub(r"[^A-Za-z0-9]", "", fw).lower()
    return f"{surname}{year}{fw}"


# ───────────────────────────────────────────────────────────────── Merging ──

def merge(existing: Entry, fetched: Entry) -> Entry:
    merged = OrderedDict()
    for k, v in fetched.fields.items():
        if k not in USER_FIELDS:
            merged[k] = v
    for k in USER_FIELDS:
        if k in existing.fields:
            merged[k] = existing.fields[k]
        elif k in fetched.fields:
            merged[k] = fetched.fields[k]
    merged = order_fields(merged)
    merged.setdefault("selected", "true")
    if "html_venue" not in merged:
        merged["html_venue"] = gen_html_venue(Entry(fetched.type, existing.key, merged))
    return Entry(fetched.type, existing.key, merged)


# ───────────────────────────────────────────────────────────────── File I/O ──

def load_bib():
    if not BIB_PATH.exists():
        return [], ""
    return parse_bib(BIB_PATH.read_text(encoding="utf-8"))


def save_bib(entries, trailing: str):
    # Each parsed entry carries the whitespace BEFORE it as its `header`
    # (including section dividers, @comment blocks, and blank lines).
    # Emit header verbatim then the entry — do NOT add extra whitespace
    # between entries, otherwise inter-entry blank lines will double on
    # every save cycle.
    parts = []
    for header, entry in entries:
        if header:
            parts.append(header)
        parts.append(format_entry(entry))
    # Ensure file ends with a single newline.
    if parts and not parts[-1].endswith("\n"):
        parts.append("\n")
    if trailing:
        parts.append(trailing if trailing.endswith("\n") else trailing + "\n")
    BIB_PATH.write_text("".join(parts), encoding="utf-8")


def find(entries, citekey=None, doi=None):
    doi_norm = doi.lower().rstrip("/.") if doi else None
    for i, (_, e) in enumerate(entries):
        if citekey and e.key == citekey:
            return i, e
        if doi_norm and e.fields.get("doi", "").lower().rstrip("/.") == doi_norm:
            return i, e
    return None, None


def insert_in_year_section(entries, new_entry: Entry):
    year = new_entry.fields.get("year", "")
    last = -1
    for i, (_, e) in enumerate(entries):
        if e.fields.get("year", "") == year:
            last = i
    if last >= 0:
        entries.insert(last + 1, ("", new_entry))
    else:
        entries.append((f"\n% =========== {year} (new section, please add divider) ===\n\n", new_entry))


def replace_entry(entries, idx: int, new_fields: OrderedDict, type_=None, key=None):
    header, old = entries[idx]
    entries[idx] = (header, Entry(type_ or old.type, key or old.key, order_fields(new_fields)))


def toggle_field(entry: Entry, field: str):
    """Flip a boolean-ish field on/off. Returns the new state ('true'|'false')."""
    current = entry.fields.get(field, "false") == "true"
    if current:
        # turn off — `selected` stays as 'false' (semantic flag); `featured`
        # is removed (absence = off, keeps file cleaner).
        if field == "selected":
            entry.fields["selected"] = "false"
        else:
            entry.fields.pop(field, None)
        return "false"
    else:
        entry.fields[field] = "true"
        return "true"


# ────────────────────────────────────────────────────────────── Subcommands ──

def cmd_add(arg: str):
    raw, source = fetch_bib(arg)
    if not raw:
        sys.exit(f"✗ Could not fetch BibTeX: {source}")
    fetched_list, _ = parse_bib(raw)
    if not fetched_list:
        sys.exit("✗ Fetched data has no valid BibTeX entries")
    _, fetched = fetched_list[0]
    sys.stderr.write(f"✓ Fetched from {source}\n")
    sys.stderr.write(f"  title : {fetched.fields.get('title', '')[:80]}\n")
    sys.stderr.write(f"  author: {fetched.fields.get('author', '')[:80]}\n")

    entries, trailing = load_bib()
    fetched_doi = fetched.fields.get("doi", "")
    idx, existing = find(entries, doi=fetched_doi) if fetched_doi else (None, None)
    if existing:
        sys.stderr.write(f"  ↪ Existing entry found: {existing.key} — merging\n")
        entries[idx] = (entries[idx][0], merge(existing, fetched))
    else:
        key = gen_citekey(fetched)
        keys = {e.key for _, e in entries}
        if key in keys:
            base, suffix = key, "b"
            while key in keys:
                key, suffix = base + suffix, chr(ord(suffix) + 1)
        new_fields = order_fields(fetched.fields)
        new_fields.setdefault("selected", "true")
        if "html_venue" not in new_fields:
            new_fields["html_venue"] = gen_html_venue(Entry(fetched.type, key, new_fields))
        insert_in_year_section(entries, Entry(fetched.type, key, new_fields))
        sys.stderr.write(f"  ↪ New entry inserted: {key}\n")

    save_bib(entries, trailing)
    sys.stderr.write("✓ papers.bib written\n")


def cmd_update(citekey: str):
    entries, trailing = load_bib()
    idx, existing = find(entries, citekey=citekey)
    if existing is None:
        sys.exit(f"✗ No entry with citekey {citekey}")
    doi = existing.fields.get("doi") or normalize_doi(existing.fields.get("url", ""))
    if not doi:
        sys.exit(f"✗ {citekey} has no DOI to re-fetch")
    sys.stderr.write(f"→ Re-fetching {citekey} via DOI {doi}\n")
    raw = fetch_crossref_bibtex(doi)
    if not raw:
        sys.exit(f"✗ CrossRef has no record for {doi}")
    fetched_list, _ = parse_bib(raw)
    if not fetched_list:
        sys.exit("✗ Fetched data has no valid BibTeX entries")
    _, fetched = fetched_list[0]
    entries[idx] = (entries[idx][0], merge(existing, fetched))
    save_bib(entries, trailing)
    sys.stderr.write(f"✓ {citekey} updated\n")


def cmd_toggle(field: str, citekey: str):
    if field not in {"selected", "featured"}:
        sys.exit("✗ field must be 'selected' or 'featured'")
    entries, trailing = load_bib()
    idx, e = find(entries, citekey=citekey)
    if e is None:
        sys.exit(f"✗ No entry: {citekey}")
    new = toggle_field(e, field)
    replace_entry(entries, idx, e.fields)
    save_bib(entries, trailing)
    sys.stderr.write(f"✓ {citekey}: {field} = {new}\n")


def cmd_venue(citekey: str):
    entries, trailing = load_bib()
    idx, e = find(entries, citekey=citekey)
    if e is None:
        sys.exit(f"✗ No entry: {citekey}")
    new_venue = gen_html_venue(e)
    old_venue = e.fields.get("html_venue", "<missing>")
    sys.stderr.write(f"  old: {old_venue}\n  new: {new_venue}\n")
    if old_venue == new_venue:
        sys.stderr.write("  (no change)\n")
        return
    e.fields["html_venue"] = new_venue
    replace_entry(entries, idx, e.fields)
    save_bib(entries, trailing)
    sys.stderr.write(f"✓ {citekey} html_venue regenerated\n")


def cmd_venue_all():
    entries, trailing = load_bib()
    changed = 0
    for i, (header, entry) in enumerate(entries):
        nv = gen_html_venue(entry)
        ov = entry.fields.get("html_venue", "")
        if nv != ov:
            entry.fields["html_venue"] = nv
            entries[i] = (header, Entry(entry.type, entry.key, order_fields(entry.fields)))
            sys.stderr.write(f"  {entry.key}\n    old: {ov}\n    new: {nv}\n")
            changed += 1
    if changed:
        save_bib(entries, trailing)
    sys.stderr.write(f"✓ {changed} entries regenerated\n")


def cmd_list():
    entries, _ = load_bib()
    for _, e in entries:
        flags = ("S" if e.fields.get("selected") == "true" else ".") + \
                ("F" if e.fields.get("featured") == "true" else ".")
        year = e.fields.get("year", "????")
        rank = e.fields.get("rank", "")
        title = re.sub(r"[{}\\]", "", e.fields.get("title", ""))[:72]
        rank_str = f"  [{rank}]" if rank else ""
        print(f"  {flags} {year}  {e.key:30s}  {title}{rank_str}")


# ─────────────────────────────────────────────────────────── Interactive TUI ──

def cmd_interactive():
    """Curses-based browser for papers.bib."""
    try:
        import curses
    except ImportError:
        sys.exit("✗ curses module not available — run a subcommand instead.")

    def main_loop(stdscr):
        curses.curs_set(0)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_BLUE, -1)
            curses.init_pair(5, curses.COLOR_MAGENTA, -1)
        except curses.error:
            pass

        state = {
            "entries": None,
            "trailing": "",
            "cursor": 0,
            "scroll": 0,
            "dirty": False,
            "msg": "",
        }
        state["entries"], state["trailing"] = load_bib()

        while True:
            view = list_view(stdscr, state)
            if view == "quit":
                break
            elif view == "add":
                add_view(stdscr, state)
            else:
                detail_view(stdscr, state, view)
            if state["dirty"]:
                save_bib(state["entries"], state["trailing"])
                state["dirty"] = False
                state["msg"] = "saved"

    def list_view(stdscr, state):
        """Returns 'quit', 'add', or an int index of the entry to open."""
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            entries = state["entries"]
            total = len(entries) + 1  # +1 for "[+ Add new]"

            header = f" papers.bib  ({len(entries)} entries) "
            stdscr.addstr(0, 0, header.center(w - 1, "─")[:w - 1], curses.A_BOLD)

            list_h = h - 2
            if state["cursor"] < state["scroll"]:
                state["scroll"] = state["cursor"]
            if state["cursor"] >= state["scroll"] + list_h:
                state["scroll"] = state["cursor"] - list_h + 1

            for row in range(list_h):
                idx = state["scroll"] + row
                if idx >= total:
                    break
                y = row + 1
                is_cur = (idx == state["cursor"])
                attr = curses.A_REVERSE if is_cur else 0
                if idx < len(entries):
                    _, e = entries[idx]
                    draw_entry_row(stdscr, y, w, e, attr)
                else:
                    label = " [+ Add new publication]"
                    stdscr.addstr(y, 0, label.ljust(w - 1)[:w - 1], attr | curses.A_BOLD)

            footer = " ↑/↓ navigate   ENTER open   q quit "
            if state["msg"]:
                footer += "   ✓ " + state["msg"]
                state["msg"] = ""
            stdscr.addstr(h - 1, 0, footer.ljust(w - 1)[:w - 1], curses.A_DIM)
            stdscr.refresh()

            k = stdscr.getch()
            if k in (curses.KEY_UP, ord("k")):
                state["cursor"] = max(0, state["cursor"] - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                state["cursor"] = min(total - 1, state["cursor"] + 1)
            elif k == curses.KEY_HOME or k == ord("g"):
                state["cursor"] = 0
            elif k == curses.KEY_END or k == ord("G"):
                state["cursor"] = total - 1
            elif k == curses.KEY_PPAGE:
                state["cursor"] = max(0, state["cursor"] - list_h)
            elif k == curses.KEY_NPAGE:
                state["cursor"] = min(total - 1, state["cursor"] + list_h)
            elif k in (10, 13, curses.KEY_ENTER):
                if state["cursor"] < len(entries):
                    return state["cursor"]
                return "add"
            elif k in (ord("q"), 27):
                return "quit"

    def draw_entry_row(stdscr, y, w, e, base_attr):
        sel = e.fields.get("selected") == "true"
        feat = e.fields.get("featured") == "true"
        year = e.fields.get("year", "????")
        rank = e.fields.get("rank", "")
        title = re.sub(r"[{}\\]", "", e.fields.get("title", ""))

        # ▎column markers
        s_flag = "S" if sel else "."
        f_flag = "F" if feat else "."

        # Compose with flag coloring
        prefix = f" {s_flag}{f_flag}  {year}  "
        rank_str = f"  [{rank}]" if rank else ""
        avail = max(10, w - len(prefix) - len(rank_str) - 4)
        title_short = title[:avail]
        line = f"{prefix}{e.key:32s}  {title_short}{rank_str}"

        stdscr.addstr(y, 0, line.ljust(w - 1)[:w - 1], base_attr)
        # Overlay flag colors when not on cursor
        if not (base_attr & curses.A_REVERSE):
            if sel:
                try:
                    stdscr.addstr(y, 1, "S", curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass
            if feat:
                try:
                    stdscr.addstr(y, 2, "F", curses.color_pair(2) | curses.A_BOLD)
                except curses.error:
                    pass

    def detail_view(stdscr, state, idx):
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            _, e = state["entries"][idx]
            stdscr.addstr(0, 0, f" {e.key} ".center(w - 1, "─")[:w - 1], curses.A_BOLD)

            y = 2
            display_fields = [
                "title", "author", "booktitle", "journal",
                "year", "month", "series", "volume", "number",
                "pages", "publisher", "doi", "url", "rank",
            ]
            for fname in display_fields:
                if fname not in e.fields:
                    continue
                val = e.fields[fname]
                wrap_width = w - 14
                wrapped = textwrap.wrap(val, wrap_width) or [""]
                stdscr.addstr(y, 2, fname.ljust(10), curses.A_BOLD)
                stdscr.addstr(y, 12, wrapped[0][:w - 13])
                y += 1
                for cont in wrapped[1:]:
                    if y >= h - 7:
                        break
                    stdscr.addstr(y, 12, cont[:w - 13])
                    y += 1
                if y >= h - 7:
                    break

            # Toggle indicators
            y += 1
            if y < h - 6:
                sel = e.fields.get("selected") == "true"
                feat = e.fields.get("featured") == "true"
                stdscr.addstr(y, 2, "selected ", curses.A_BOLD)
                stdscr.addstr(y, 12, "✓ on " if sel else "✗ off",
                              curses.color_pair(1) if sel else curses.A_DIM)
                y += 1
                stdscr.addstr(y, 2, "featured ", curses.A_BOLD)
                stdscr.addstr(y, 12, "✓ on " if feat else "✗ off",
                              curses.color_pair(2) if feat else curses.A_DIM)
                y += 2

            # html_venue
            if y < h - 5:
                stdscr.addstr(y, 2, "html_venue", curses.A_BOLD)
                y += 1
                for line in textwrap.wrap(e.fields.get("html_venue", ""), w - 6):
                    if y >= h - 3:
                        break
                    stdscr.addstr(y, 4, line[:w - 5], curses.color_pair(5))
                    y += 1

            footer = " s sel   f feat   e edit venue   v regen venue   u re-fetch   b/Esc back   q quit "
            stdscr.addstr(h - 1, 0, footer.ljust(w - 1)[:w - 1], curses.A_DIM)
            stdscr.refresh()

            k = stdscr.getch()
            if k == ord("s"):
                toggle_field(e, "selected")
                replace_entry(state["entries"], idx, e.fields)
                state["dirty"] = True
                state["msg"] = "selected toggled"
            elif k == ord("f"):
                toggle_field(e, "featured")
                replace_entry(state["entries"], idx, e.fields)
                state["dirty"] = True
                state["msg"] = "featured toggled"
            elif k == ord("v"):
                nv = gen_html_venue(e)
                if nv != e.fields.get("html_venue", ""):
                    e.fields["html_venue"] = nv
                    replace_entry(state["entries"], idx, e.fields)
                    state["dirty"] = True
                    state["msg"] = "html_venue regenerated"
                else:
                    state["msg"] = "html_venue already up to date"
            elif k == ord("e"):
                new_venue = edit_field_value(stdscr, "html_venue",
                                             e.fields.get("html_venue", ""))
                if new_venue is not None and new_venue != e.fields.get("html_venue", ""):
                    if new_venue == "":
                        e.fields.pop("html_venue", None)
                    else:
                        e.fields["html_venue"] = new_venue
                    replace_entry(state["entries"], idx, e.fields)
                    state["dirty"] = True
                    state["msg"] = "html_venue edited"
            elif k == ord("u"):
                if state["dirty"]:
                    save_bib(state["entries"], state["trailing"])
                    state["dirty"] = False
                run_outside_curses(stdscr, lambda: cmd_update(e.key))
                state["entries"], state["trailing"] = load_bib()
                # Re-resolve idx (entry may have moved)
                for i, (_, x) in enumerate(state["entries"]):
                    if x.key == e.key:
                        idx = i
                        break
                state["msg"] = "re-fetched"
            elif k in (ord("b"), ord("h"), 27, curses.KEY_LEFT):
                return
            elif k == ord("q"):
                if state["dirty"]:
                    save_bib(state["entries"], state["trailing"])
                    state["dirty"] = False
                # bubble quit up by re-entering list with quit flag
                state["_quit"] = True
                return

    def add_view(stdscr, state):
        # Save any pending edits before going offline.
        if state["dirty"]:
            save_bib(state["entries"], state["trailing"])
            state["dirty"] = False

        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.addstr(0, 0, " Add new publication ".center(w - 1, "─")[:w - 1], curses.A_BOLD)
        stdscr.addstr(2, 2, "Enter DOI / URL / arXiv URL / paper title.")
        stdscr.addstr(3, 2, "(Esc / empty input to cancel.)")
        stdscr.addstr(5, 2, "> ", curses.A_BOLD)
        curses.echo()
        curses.curs_set(1)
        stdscr.refresh()
        try:
            raw = stdscr.getstr(5, 4, w - 8).decode("utf-8", errors="replace").strip()
        except KeyboardInterrupt:
            raw = ""
        # `getstr` toggles to cooked / echo mode internally. Restore the
        # curses mode explicitly — without this, subsequent `stdscr.getch()`
        # calls (including in the detail view) become line-buffered, forcing
        # the user to press Enter after every key.
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        curses.curs_set(0)
        if not raw:
            state["msg"] = "add cancelled"
            return
        run_outside_curses(stdscr, lambda: cmd_add(raw))
        state["entries"], state["trailing"] = load_bib()
        state["msg"] = "added"

    def edit_field_value(stdscr, label, current):
        """Pop up a single-line editable text box pre-filled with `current`.

        Returns the new string (without trailing whitespace), "" if the user
        cleared the field, or None if cancelled with Esc.

        Keybindings (via curses.textpad.Textbox):
          ← / →  Ctrl-B / Ctrl-F   cursor left / right
          Home / End  Ctrl-A / Ctrl-E
          Backspace  Ctrl-H        delete char before cursor
          Ctrl-K  kill to end of line
          Enter   save and exit
          Esc     cancel
        """
        import curses.textpad as tp

        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.addstr(0, 0, f" Edit {label} ".center(w - 1, "─")[:w - 1], curses.A_BOLD)
        stdscr.addstr(2, 2, "Edit the value, then Enter to save / Esc to cancel.")
        stdscr.addstr(3, 2, "(← → Home End Backspace Ctrl-K all work as expected)",
                      curses.A_DIM)

        # Editor box dimensions. We need enough lines to fit the wrapped
        # value plus room to type; cap at ~half the screen.
        box_w = max(20, w - 6)
        # Estimate wrapped line count for the current value.
        approx_lines = max(1, (len(current) + box_w - 2) // (box_w - 1))
        box_h = max(3, min(h - 8, approx_lines + 2))
        box_y, box_x = 5, 3

        try:
            tp.rectangle(stdscr, box_y - 1, box_x - 1, box_y + box_h, box_x + box_w)
        except curses.error:
            pass
        stdscr.refresh()

        win = curses.newwin(box_h, box_w, box_y, box_x)

        # Pre-fill with `current`, broken into chunks fitting the box width.
        # We deliberately use HARD wraps at box_w-1 (no word-aware wrapping)
        # so the gathered text can be re-flattened deterministically.
        chunks, rest = [], current
        while rest:
            chunks.append(rest[: box_w - 1])
            rest = rest[box_w - 1:]
        if not chunks:
            chunks = [""]
        for i, line in enumerate(chunks[:box_h]):
            try:
                win.addstr(i, 0, line)
            except curses.error:
                pass

        # Park cursor at end of content so the user can keep typing.
        last_y = min(len(chunks) - 1, box_h - 1)
        last_x = min(len(chunks[last_y]), box_w - 2)
        try:
            win.move(last_y, last_x)
        except curses.error:
            pass

        cancelled = [False]

        def validate(ch):
            # Esc cancels; trap before Textbox eats it.
            if ch == 27:
                cancelled[0] = True
                return 7  # Ctrl-G terminates Textbox
            # Enter (LF or CR) on a single logical field means save.
            if ch in (10, 13, curses.KEY_ENTER):
                return 7  # Ctrl-G
            # macOS sometimes sends 0x7F for Backspace.
            if ch == 127:
                return curses.KEY_BACKSPACE
            return ch

        curses.curs_set(1)
        box = tp.Textbox(win, insert_mode=True)
        try:
            box.edit(validate)
        except KeyboardInterrupt:
            cancelled[0] = True
        curses.curs_set(0)

        if cancelled[0]:
            return None

        # Flatten the multi-line gather back into a single line: strip
        # trailing whitespace from each row, then join with no separator
        # (the hard-wrap above introduced no real newlines).
        raw = box.gather()
        flat = "".join(line.rstrip(" \t") for line in raw.split("\n"))
        return flat.strip()

    def run_outside_curses(stdscr, fn):
        """Suspend curses, run a normal-IO function, wait for keypress, resume.

        After `endwin()` the terminal is back to canonical/echo mode. Coming
        back into curses we must re-set cbreak/noecho/keypad explicitly,
        otherwise `getch()` in the next view returns line-buffered input
        (every keystroke needs Enter).
        """
        curses.endwin()
        print()
        try:
            fn()
        except SystemExit as ex:
            print(f"\n{ex}")
        except Exception as ex:
            print(f"\n✗ {type(ex).__name__}: {ex}")
        input("\nPress Enter to return to the list… ")
        stdscr.clear()
        curses.cbreak()
        curses.noecho()
        stdscr.keypad(True)
        stdscr.refresh()

    try:
        curses.wrapper(main_loop)
    except KeyboardInterrupt:
        print("\n✗ Interrupted")


# ─────────────────────────────────────────────────────────────────── main ──

def main():
    p = argparse.ArgumentParser(
        description="Manage assets/bibliography/papers.bib",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="Fetch + insert a new entry")
    a.add_argument("arg", help="DOI / URL / arXiv URL / paper title")

    u = sub.add_parser("update", help="Re-fetch + merge an existing entry by citekey")
    u.add_argument("citekey")

    t = sub.add_parser("toggle", help="Toggle selected or featured for an entry")
    t.add_argument("field", choices=["selected", "featured"])
    t.add_argument("citekey")

    v = sub.add_parser("venue", help="Regenerate html_venue for one entry")
    v.add_argument("citekey")

    sub.add_parser("venue-all", help="Regenerate html_venue for every entry that would change")
    sub.add_parser("list", help="List all entries with flags + ranks")

    args = p.parse_args()

    try:
        if args.cmd is None:
            cmd_interactive()
        elif args.cmd == "add":
            cmd_add(args.arg)
        elif args.cmd == "update":
            cmd_update(args.citekey)
        elif args.cmd == "toggle":
            cmd_toggle(args.field, args.citekey)
        elif args.cmd == "venue":
            cmd_venue(args.citekey)
        elif args.cmd == "venue-all":
            cmd_venue_all()
        elif args.cmd == "list":
            cmd_list()
    except KeyboardInterrupt:
        sys.exit("\n✗ Interrupted")


if __name__ == "__main__":
    main()
