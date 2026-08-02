
# manleviet.github.io

Personal academic website of **Viet-Man Le** — PhD candidate at TU Graz, Austria, working on knowledge-based diagnosis, configuration systems, and explanations in AI.

Live site: **<https://manleviet.github.io>**

## Stack

- [Jekyll](https://jekyllrb.com/) static site generator
- [jekyll-scholar](https://github.com/inukshuk/jekyll-scholar) — BibTeX-driven rendering of the publications page and the homepage "Featured Publications" block. Backed by [bibtex-ruby](https://github.com/inukshuk/bibtex-ruby) + [citeproc-ruby](https://github.com/inukshuk/citeproc-ruby).
- [jekyll-seo-tag](https://github.com/jekyll/jekyll-seo-tag) for `<meta>` headers.
- Theme: customized fork of the [Researcher](https://github.com/ankitsultana/researcher) Jekyll theme — see [Credits](#credits).

Because `jekyll-scholar` is not on the GitHub Pages plugin whitelist, the site is **built and deployed via GitHub Actions** rather than the native Pages builder. See `.github/workflows/jekyll.yml`.

## Pages

| File | URL | Content |
|---|---|---|
| `index.md` | `/` | About + bio + News + Featured Publications |
| `research.md` | `/research.html` | Research interests + ongoing projects |
| `publications.md` | `/publications.html` | Selected publications (auto-rendered from BibTeX) + theses |
| `service.md` | `/service.html` | Academic service (reviewing, organizing, chairing) |
| `teaching.md` | `/teaching.html` | Courses taught + thesis supervision |
| `awards.md` | `/awards.html` | Awards & grants |
| `assets/pdf/cv.pdf` | `/CV` | Full CV (PDF) |

## Repository layout

```
manleviet.github.io/
├── _config.yml                       # Jekyll + jekyll-scholar config
├── _layouts/
│   ├── default.html                  # site layout
│   └── pub_card.html                 # jekyll-scholar bibliography_template
├── _sass/                            # SCSS partials (vars, style, typography, tables)
├── assets/
│   ├── bibliography/papers.bib       # ← single source of truth for publications
│   └── pdf/                          # CV + thesis PDFs
├── css/main.scss                     # entry point for compiled CSS
├── scripts/
│   └── papers_bib.py                 # CLI / TUI to manage papers.bib
├── .github/workflows/jekyll.yml      # build + deploy to GitHub Pages
├── index.md, publications.md, …      # page sources
├── Gemfile, Gemfile.lock             # Ruby dependencies
└── README.md
```

## Local development

```bash
# Ruby 3.2 recommended (rbenv install 3.2.5 && rbenv global 3.2.5)
bundle install
bundle exec jekyll serve --livereload
# open http://localhost:4000
```

Edit any `.md` or `.bib` file and the running server regenerates on save.

If the `bundle install` step fails on native extensions, run `xcode-select --install` (macOS) so `gcc` and the Ruby headers are available.

## Deployment

Push to `gh-pages` (or `main`) — the GitHub Actions workflow at `.github/workflows/jekyll.yml` builds with full Bundler/jekyll-scholar support and deploys the rendered `_site/` via `actions/deploy-pages@v4`.

**One-time setup on a fresh fork:** Repo Settings → Pages → **Source: GitHub Actions** (not "Deploy from branch"). Without this the workflow never publishes.

## Features customized in this fork

- **Dark / light mode toggle.** Sun/moon button in the navbar (right of the social icons). Honors `prefers-color-scheme` on first visit; the user's explicit choice persists via `localStorage` and overrides the OS preference thereafter. An inline boot script in `<head>` sets the theme attribute *before* `<body>` renders to prevent a flash of the wrong theme.
- **Theme palette.** GitHub Primer "dimmed" family for dark mode (warmer neutral gray, not slate). All color tokens live as CSS custom properties on `:root` (light) and inside `@mixin dark-palette` (dark), applied to both `[data-theme="dark"]` and `@media (prefers-color-scheme: dark)`. Defined in `_sass/vars.scss`.
- **Social-icons header.** Email, Google Scholar, ORCID, GitHub, LinkedIn rendered as FontAwesome icons in the navbar (right side), replacing the upstream template's plain text links.
- **BibTeX-driven publication lists.** Both `publications.md` (full year-grouped list) and `index.md` (Featured Publications block) render from a single `.bib` file via a `_layouts/pub_card.html` Liquid template that produces the original `.pub` card visual style. Theses are still hand-written markdown — they don't fit BibTeX cleanly.
- **External-link auto-targeting.** A small script in `_layouts/default.html` adds `target="_blank" rel="noopener noreferrer"` to every off-domain link at `DOMContentLoaded`.

## Managing publications

The entire publication list (homepage Featured block + `/publications.html` year-grouped list) is driven by `assets/bibliography/papers.bib`. Theses are an exception — see [Theses](#theses) below.

### Bibliography fields

Each entry uses standard BibTeX fields (`title`, `author`, `booktitle`/`journal`, `year`, `volume`, `number`, `pages`, `publisher`, `doi`, `url`, …) plus five custom fields consumed by `_layouts/pub_card.html`:

| Field | Purpose |
|---|---|
| `selected = {true}` | Entry appears on `/publications.html`. Set to `{false}` (or remove) to hide without deleting. |
| `featured = {true}` | Entry ALSO appears in the homepage Featured Publications block (subset of `selected`). |
| `rank = {CORE A*}` | Optional ranking tag rendered to the right of the venue line. Common values: `CORE A*`, `CORE A`, `CORE B`, `SCIMAGO Q2`. |
| `month = {3}` | Numeric 1–12. Used as the within-year sort key (descending). |
| `html_venue = {<em>...</em>, ...}` | Pre-rendered HTML for the venue line. Used instead of auto-building from booktitle/series/volume/etc. because venue formats vary too much across CEUR / FAIA / LNNS / SCI / AAAI / SPLC / VaMoS / Software Impacts. |

Authors are not pre-formatted — the template splits `entry.author` on `" and "`, normalizes `"Last, First"` → `"First Last"`, and wraps `"Viet-Man Le"` in `<strong>` automatically.

### `papers_bib.py` — interactive manager

`scripts/papers_bib.py` is a stdlib-only Python tool for adding, updating, and editing entries.

**Interactive TUI** — run with no arguments:

```bash
python3 scripts/papers_bib.py
```

| View | Keys |
|---|---|
| List | `↑`/`↓` or `j`/`k` navigate · `PgUp`/`PgDn` page · `g`/`G` top/bottom · `Enter` open · `q`/`Esc` quit |
| Detail | `s` toggle `selected` · `f` toggle `featured` · `e` edit `html_venue` · `v` regenerate `html_venue` from current fields · `u` re-fetch from CrossRef via DOI · `b`/`Esc` back · `q` quit (saves) |
| Add new | The trailing `[+ Add new publication]` row opens a text input — paste a DOI, DOI URL, arXiv URL, or paper title. CrossRef is tried first (when a DOI is detected), then DBLP search with an interactive picker. |
| Edit venue | `←`/`→` cursor · `Home`/`End` line ends · `Backspace` delete · `Ctrl-K` kill to end · `Enter` save · `Esc` cancel |

Changes are auto-saved on quit.

**Non-interactive subcommands** (also useful from scripts / shell aliases):

```bash
# Fetch and insert a new entry. If the DOI matches an existing one,
# the entry is merged in place (preserving selected/featured/rank/month
# and any manually edited html_venue).
python3 scripts/papers_bib.py add 10.1609/aaai.v40i23.38995
python3 scripts/papers_bib.py add https://doi.org/10.1145/3715340.3715438
python3 scripts/papers_bib.py add "FastDiagP parallelized direct diagnosis"

# Re-fetch an existing entry via its stored DOI and merge.
python3 scripts/papers_bib.py update le2024informedqx

# Flip a flag on or off.
python3 scripts/papers_bib.py toggle selected le2024informedqx
python3 scripts/papers_bib.py toggle featured le2026robust

# Regenerate the html_venue field from current standard fields.
python3 scripts/papers_bib.py venue le2026sac
python3 scripts/papers_bib.py venue-all        # whole file, prints a diff

# Plain text listing of every entry with flags + rank.
python3 scripts/papers_bib.py list
```

The script handles citekey generation (al-folio style: `lastnameYEARfirstword`), DOI deduplication, html_venue auto-generation (covers 7 venue patterns: AAAI-style vol+no, CEUR series+vol, FAIA/LNNS/SCI series+vol+publisher, SPLC vol-only, VaMoS publisher-only, Software Impacts single-page, plain booktitle+pages), and field re-ordering. It is stdlib-only — no `pip install` needed.

### Manual edits

If you'd rather edit the bib file directly, the conventions are:

- One entry per `@inproceedings` / `@article` block; use blank lines between entries for readability (the TUI/CLI preserves your spacing on save).
- Section dividers like `% =========== 2026 ===` are kept verbatim by the parser.
- `_config.yml` `scholar.sort_by: year,month` + `scholar.group_by: year` controls grouping/ordering on the published page — no need to manually sort entries inside `papers.bib`.

After editing, run `bundle exec jekyll serve --livereload` (or rely on the Action build after push) to see the result.

### Theses

The three theses on `/publications.html` are hand-curated `.pub` blocks at the bottom of `publications.md` — they're not in `papers.bib`. The rationale: theses include biographical content (supervisor link, French original title, score, description paragraph) that doesn't map cleanly to standard BibTeX fields, and the list rarely changes (oldest 2004, newest 2011).

## Credits

This site is a customized fork of:

- [Ruben Branco's personal site](https://github.com/RubenBranco/rubenbranco.github.io), which itself customizes
- The [Researcher Jekyll theme](https://github.com/ankitsultana/researcher) by [Ankit Sultana](http://ankitsultana.com) — *"A clean, single-column, monospace resume template built for Jekyll"* — originally derived from
- [bk2dcradle/researcher](https://github.com/bk2dcradle/researcher).

The Researcher theme provides the underlying single-column layout, the Inconsolata monospace typography, and the configuration conventions (`_config.yml` keys: `title`, `tagline`, `nav`, `tracking_id`, `favicon`, `ins_logo`, `footer`, etc.). For the upstream README and theme-level customization options, see the [Researcher repository](https://github.com/ankitsultana/researcher#readme).

## License

[GNU GPL v3](https://github.com/bk2dcradle/researcher/blob/gh-pages/LICENSE) — inherited from upstream.
