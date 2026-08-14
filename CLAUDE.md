# CLAUDE.md

Instructions for Claude (and other AI coding assistants) when working in this repository. Human contributors should read `README.md` instead.

## What this repo is

Personal academic website for Thi Ngoc Trang Tran, hosted at https://thingoctrangtran.github.io. Forked from Viet-Man Le's `manleviet.github.io` (itself forked from `RubenBranco/rubenbranco.github.io`, an al-folio-inspired Jekyll theme), then re-customized for Trang:

- Migrated `publications.md` and `index.md` Featured block to **jekyll-scholar** with a single source of truth at `assets/bibliography/papers.bib`.
- Custom `_layouts/pub_card.html` template consumes both standard BibTeX fields and four custom fields (`html_venue`, `rank`, `selected`, `featured`).
- Dark/light theme support in `_sass/`.
- Deploys via GitHub Actions (not vanilla GH Pages) because jekyll-scholar isn't on the Pages plugin whitelist. See `.github/workflows/`.

## Critical: use the CLI, don't edit `papers.bib` by hand

`scripts/papers_bib.py` is the canonical way to manage `assets/bibliography/papers.bib`. It handles citekey generation (al-folio short form `lastnameYEARfirstword`), CrossRef/DBLP metadata fetch, `html_venue` auto-generation, idempotent DOI-based merging, and field-order normalization. **Always check this script before proposing manual edits or "let me build a CLI for this."**

```bash
# Add a new published paper (DOI preferred, title also works)
python3 scripts/papers_bib.py add 10.1613/jair.xxxxx
python3 scripts/papers_bib.py add "Paper Title Here"

# Re-fetch an existing entry by its stored DOI, merging fresh metadata
# while preserving user-curated selected/featured/rank/month/html_venue
python3 scripts/papers_bib.py update tran2026when

# Toggle selected or featured flag
python3 scripts/papers_bib.py toggle featured tran2026when

# Regenerate html_venue from current fields (for one entry or all)
python3 scripts/papers_bib.py venue tran2026when
python3 scripts/papers_bib.py venue-all

# List all entries with their flags + ranks
python3 scripts/papers_bib.py list

# Interactive curses browser (no args)
python3 scripts/papers_bib.py
```

Stdlib only, Python 3.10+. Run from repo root.

### Edit by hand only when

- The paper has been **accepted but not yet published** with no DOI / preprint URL → manually insert a minimal entry (see "Accepted, to appear" workflow below).
- An anomalous field the script doesn't model (rare).
- The script doesn't recognize a venue's metadata format.

In those cases, after manual edit, run `python3 scripts/papers_bib.py venue <citekey>` to normalize `html_venue`.

## Bibliography conventions

**Custom fields consumed by `_layouts/pub_card.html`:**
- `selected = {true}` — show on `publications.html`. Required for every entry meant to be visible.
- `featured = {true}` — also show in the Featured Publications block on `index.html` (subset of selected).
- `rank` — venue ranking tag rendered to the right of the venue line. Values: `CORE A*`, `CORE A`, `CORE B`, `SCIMAGO Q1`, `SCIMAGO Q2`. Omit for workshops / CEUR / unranked venues.
- `html_venue` — pre-rendered HTML for the venue line. Used **instead of** auto-building from booktitle/journal/series/volume/number/publisher (no single rule handles all the variety across CEUR / FAIA / LNNS / SCI / AAAI / SPLC / VaMoS / Software Impacts / JAIR / etc.).
- `month` (1–12) — within-year sort key, descending. Set even for journal articles so within-year ordering is stable.

**Author rendering:** the template splits `entry.author` on " and ", normalizes `Last, First` → `First Last`, and wraps the literal string `Thi Ngoc Trang Tran` in `<strong>`. No `author_html` override needed. Both BibTeX author formats (`Last, First and Last, First` or `First Last and First Last`) are supported, but be consistent within an entry.

**Citekey style:** al-folio short form, lowercase, no dots: `lastnameYEARfirstword` (e.g. `tran2026when`, `lubos2025towards`). The script generates these automatically when you use `add`. This is **different** from the master `references.bib` in the Obsidian vault, which uses JabRef format (`AuthorEtAl.YEAR.Keyword`).

**Theses** live as hand-curated markdown blocks under the `## Theses` heading in `publications.md`, NOT in the .bib. They have biographical content (supervisors, French original titles, scores, descriptions) that doesn't map cleanly to standard BibTeX fields.

## Workflow: "Accepted, to appear" → published

When a paper is accepted but not yet published, there's no DOI and the script's `add` can't fetch metadata. Manual insert:

```bibtex
@article{firstauthorYEARkeyword,
  title      = {Full title},
  author     = {Last, First and Last, First and ...},
  journal    = {Full Journal Name},
  year       = {2026},
  month      = {12},
  publisher  = {Publisher Name},
  rank       = {SCIMAGO Q1},
  selected   = {true},
  featured   = {true},
  html_venue = {<em>Full Journal Name</em> (to appear)}
}
```

When the paper actually publishes and gets a DOI, run:

```bash
python3 scripts/papers_bib.py add <doi>
```

The script will detect the DOI matches the existing entry, merge fresh CrossRef metadata (volume, issue, pages, doi, url), and **preserve** the user-curated `selected`, `featured`, `rank`, `month`, and `html_venue`. Then run `venue <citekey>` to regenerate `html_venue` so `(to appear)` is replaced with the actual volume/pages.

Don't forget to update `index.md` News with a new entry. The News list is hand-curated markdown — no CLI for it.

## What the script does NOT manage

- `index.md` News section (manual markdown)
- `index.md` bio paragraphs
- `research.md`
- Theses block in `publications.md`
- `_layouts/`, `_sass/`, `_config.yml`

## Don't

- Don't propose migrating away from jekyll-scholar back to hand-written `.pub` blocks. That migration was completed on 2026-05-12 and the script-driven workflow replaces the earlier hand-curation preference.
- Don't add entries to `references.bib` in the Obsidian vault directly when adding website-only entries (e.g. accepted-to-appear before the paper is in JabRef). Add to `papers.bib` here first; the user back-ports to JabRef later.
- Don't reformat `html_venue` strings across many entries at once — they were carefully crafted per-venue. Use `venue-all` only when the schema has actually changed and the diff is small and reviewable.
- Don't commit `__pycache__/` (it's already gitignored implicitly via the `*.pyc` patterns).

## Build / deploy

Deploy is fully automated via `.github/workflows/`. Pushes to `main` trigger Jekyll build under GitHub Actions; the Pages site is updated automatically. Local preview (optional):

```bash
bundle install
bundle exec jekyll serve
```

The sandbox in Claude Code Cowork may not have a Ruby toolchain capable of running Jekyll. Verify changes statically when full build isn't possible: BibTeX brace balance, citekey uniqueness, Liquid syntax in templates, YAML in `_config.yml` and workflow files.
