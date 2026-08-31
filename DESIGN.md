# Quant Paper Digest — design notes

Last updated 2026-08-31 · v0.4

Seven sources, one store, one page. Everything here is what the build actually
does, including the parts that took several attempts to get right.
[NOTES.md](NOTES.md) carries the chronological log of decisions and dead ends.

## 1. Pipeline

```
[1] fetch      arXiv listings, SSRN listing API, Quantpedia RSS, Man Group insights
                 -> ids + metadata, and abstracts where the source gives them
                       v
[2] enrich     arXiv Atom API for abstracts; SSRN abstracts via a real browser
                       v
[3] dedup      compare against state/seen.json, drop anything already summarized
                       v
[4] summarize  local Claude Code CLI -> Korean + English in one call
                       v
[5] deep       optional: full-text reports for the highest-scoring items
                       v
[6] report     seen.json -> report/qfin-digest-YYYYMMDD.html + index.html
```

Every stage runs standalone and talks to the next only through `seen.json`, so a
run that dies halfway can be resumed rather than restarted.

## 2. Sources

| Source | What "recent" means | Abstract from | Full text from |
|---|---|---|---|
| arXiv q-fin.PM/ST/TR | 2 most recent listing dates **per category** | Atom API | `arxiv.org/html/{id}v1` |
| SSRN, 7 eJournals | 2 most recent approval dates **per journal** | abstract page (browser) | PDF -> pypdf |
| Quantpedia | newest 8 posts | RSS `<description>` | article page |
| Man Group Insights | newest 8 posts | `<meta name="description">` | article page |
| Alpha Architect | newest 8 posts | RSS `<description>` | article page |
| Macrosynergy | newest 8 posts | RSS, after a browser warm-up | article page |
| Quantocracy | newest 8 curated links | homepage excerpt | linked article page |

### 2.1 arXiv

Request `?skip=0&show=2000` so there is no pagination. The page repeats one
`<dl id='articles'>` block **per date** — there is not a single one wrapping the
document, which is the obvious wrong assumption. Two details cost time:

- Days with nothing new still emit a heading plus
  "No updates for this time period.", so empty dates must be skipped when
  counting "the two most recent dates".
- The markup is `href ="/abs/ID"` — note the space before `=`. A tidy
  `href="` pattern silently matches nothing.

Dates are taken **per category, not globally**. Measured on 2026-08-31, q-fin.PM
last updated 08-26/08-25 while q-fin.ST and q-fin.TR were on 08-31/08-28. A
global top-2 would have dropped q-fin.PM entirely.

Abstracts come from the Atom API rather than the collapsed listing markup: it is
stable, and 100 papers arrive per request.

### 2.2 SSRN

SSRN splits cleanly in two, and only one half is defended.

| Target | Endpoint | Cloudflare |
|---|---|---|
| Listing (title, authors, affiliation, approval date, abstract_id) | `api.ssrn.com/content/v1/bindings/{jid}/papers` | **no** — plain requests works |
| Abstract, PDF | `papers.ssrn.com/sol3/papers.cfm?abstract_id=` | yes |

The listing API is date-descending under `sort=0` and pages with `index`/`count`.
It does not return abstracts, and every per-paper detail endpoint answers 401.

#### Clearing the challenge — what was actually tried

| Approach | Result |
|---|---|
| `requests` with full browser headers | 403 "Just a moment..." |
| Playwright bundled Chromium, headless | still challenged after 60s |
| Playwright bundled Chromium, headed | same |
| Playwright `channel="chrome"` (real Chrome, headed) | same |
| **Chrome we launch, attached over CDP** | **cleared in ~4s** |

Anything Playwright `launch()`es is flagged as automation. A plain Chrome started
with `--remote-debugging-port` and then attached via `connect_over_cdp` is not.
Clearing it once leaves `cf_clearance` in the dedicated profile, so later runs are
fast. The window is parked at `--window-position=-2400,-2400`; it is still a real
window, so the challenge behaves normally. `--show-browser` brings it back on screen.

One trap: the interstitial's title is localised — it reads
"잠시만 기다리십시오…" on a Korean Chrome. Never detect the challenge by title.
Wait for the target selector (`div.abstract-text`) instead.

Aggregators were checked as a way to skip the browser entirely. Crossref,
OpenAlex and Semantic Scholar all return 404 for SSRN working papers approved in
the last day or two — exactly the ones this tool is for.

### 2.3 Blogs

Five sites, four shapes.

- **Quantpedia, Alpha Architect** — `/feed/` is ordinary RSS with title, link,
  `pubDate` and a description that already reads as an abstract. Alpha
  Architect's *blog page* is Cloudflare-protected while its feed is not, which is
  the general lesson: try the feed before the page.
- **Man Group** — `/insights` lists current articles but shows no dates. Each
  article page has the title in `<h1>`, the abstract in
  `<meta name="description">`, and the date as a bare `<p>28 July 2026</p>`. The
  landing page supplies the candidate set; one request per article fills in the
  rest. The listing is not date-ordered, so sort before trimming.
- **Macrosynergy** — page and feed both 403. Clearing the challenge once in a
  real Chrome (§2.2's CDP trick, on its own port) leaves `cf_clearance`, after
  which the plain feed returns 200.
- **Quantocracy** — an aggregator. Its homepage is 50
  `<article class='qo-entry'>` blocks: an outbound link, a title reading
  `Headline [Origin Blog]`, an excerpt and a timestamp.

Blogs publish irregularly, so "two most recent dates" is meaningless for them.
They are taken as "newest N posts" (default 8, `--blog-limit`).

#### Aggregator overlap

Quantocracy links to sites collected directly here — its first entry was
literally "Boundaries of Time Series Momentum [Quantpedia]". The direct entry
wins: Quantocracy truncates excerpts with `(...)` while the origin feed carries
the whole thing. Two guards, because one is not enough:

1. `blogs.AGGREGATED_DOMAINS` skips Quantocracy entries whose host is collected
   directly **in the same run**.
2. `run._fetch_blogs` compares against the store by normalized URL and deletes
   aggregator copies left behind by an earlier run with a narrower `--source`.

`norm_url()` drops scheme, `www.`, trailing slash and query — the aggregator and
the origin differed by exactly a trailing slash, so string equality missed it.

#### One session per site

Sharing a single `requests.Session` across these sites made Macrosynergy return
403 and Quantocracy 400, while identical standalone requests worked: a failed
challenge leaves its own `__cf_bm` on the session, which then conflicts with the
cleared cookie. Both listers issue isolated requests.

## 3. Store

`state/seen.json` — one dict keyed by paper id. A `summary` is what makes the
next run skip an entry.

```json
{
  "2608.28399": {
    "id": "2608.28399", "ext_id": "2608.28399", "src": "arxiv",
    "title": "...", "authors": ["..."], "abstract": "...",
    "src_cats": ["q-fin.TR"], "listed_date": "2026-08-28",
    "summary": {
      "relevance": 3,
      "keywords": ["llm agents", "market timing"],
      "ko": {"one_liner": "...", "bullets": ["..."], "method": "...",
             "data": "...", "takeaway": "...", "relevance_why": "..."},
      "en": {"one_liner": "...", "...": "..."}
    }
  }
}
```

Ids are prefixed per source so they cannot collide and are safe as filenames and
CLI arguments: `2608.28399`, `ssrn-7375498`, `qp-<slug>`, `man-<slug>`.

Writes go through a temp file and `os.replace`, with one `.bak` generation kept.
`store._migrate()` upgrades older entries on load: v0.1 had no `src`/`ext_id`,
v0.3 kept a single Korean summary with its fields at the top of `summary`.

## 4. Summaries

One `claude -p` call returns both languages. Two calls would let `relevance`
drift between them, and cost twice as much. The two versions are written
natively rather than translated, with separate style rules for each.

Per language: `one_liner`, `bullets` (3-4), `method`, `data`, `takeaway`,
`relevance_why`. Shared: `relevance`, `keywords`.

### 4.1 The star rating

`relevance` measures **systematic-trading implementability** and nothing else —
explicitly not academic quality.

| Score | Meaning |
|---|---|
| 5 | Explicit entry/exit rules on public, standard data. Universe and cadence specified. Backtestable as written. |
| 4 | Gives a signal or method reproducible from standard data; some parameters left to the implementer. |
| 3 | Useful features, risk models or portfolio techniques, but needs substantial further design. |
| 2 | High barrier: satellite imagery, proprietary order flow, surveys, hand-labelled data, hard-to-access assets, ultra-low latency. |
| 1 | Theory, policy, law, institutional description, survey. Nothing to automate. |

**+1** (cap 5) when the paper refutes a widely held belief, improves backtesting
methodology, or is original enough to be worth reading regardless. Data that
cannot be obtained caps the score at 2 however strong the results.

Every score carries a one-line justification that must mention data
availability. That constraint is what stops the model from rating on prestige.

Measured on 43 papers when this rubric replaced a vague "practical relevance":

| Score | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| Papers | 2 | 11 | 12 | 7 | 11 |

Mean 2.67. The previous rubric bunched almost everything at 3-4 and separated
nothing. Law, policy and survey papers now fall to 1; work leaning on satellite
imagery, surveys or proprietary data falls to 2, which is what surfaces the top.

## 5. Deep reports

Eight sections, from "at a glance" to "systematic trading angle". Body text is
the arXiv HTML edition, the SSRN PDF, or the blog article page; failing all of
those, the abstract, with the page saying so.

Written per language into `report/paper/{id}.{lang}.html`, from separate
per-language prompts rather than by translating one output.

### 5.1 Math

arXiv's LaTeXML output carries the original LaTeX in
`<math alttext="A_{id}(p,r)=\sum...">`. Stripping tags first turned that into
`A id p r`, and every formula in the first version of these reports was garbage.

The fix is to restore `alttext` into `\( ... \)` **before** removing tags, tell
the model to emit `\( \)` and `\[ \]`, and load MathJax on the page. MathJax is
the only external dependency anywhere in the output; offline, the LaTeX source
still reads fine.

## 6. The page

One HTML file, no build step, no framework.

Both languages ship in the same document. Language-specific nodes carry
`data-l="ko"` / `data-l="en"` and CSS shows only the one matching
`<html data-lang>`, so switching is instant and needs no rebuild. Chrome labels
that live in attributes (placeholder, `<option>` text, button captions) are set
from a small JS dictionary. The choice persists in `localStorage`.

Cards carry both language blocks, star rating, filters by source and field, and
free-text search across both languages plus the original abstract.

### 6.1 One-click deep reports

A static page cannot call Claude. The first design queued ids in `localStorage`
and made you copy a command into a terminal, which turned out to be the most
annoying part of using the thing.

`python run.py serve` hosts `report/` and bolts on a small API:

```
GET  /api/ping                     is anything listening
POST /api/report {id, lang}        queue a deep report
GET  /api/status?id=...&lang=...   poll it
```

The page probes `api/ping` on load. With no answer — opened as a file, or on
GitHub Pages — it silently reverts to the copy-a-command flow, so one HTML file
works in all three places. A green badge shows which mode is active.

- One worker only. Parallel `claude` calls and Chrome windows interfere.
- The SSRN browser is started once and reused for the server's lifetime; per-job
  startup would add ~7s of Chrome launch plus challenge clearing every time.
- When a report finishes, `on_done` rebuilds the digest so the link is there on
  the next load; the live page swaps the button in place immediately.

Measured: one SSRN paper, PDF fetch through finished report, about 140 seconds.

Each card has one button per language, so a report is generated in the language
you ask for rather than translated afterwards.

## 7. Layout

```
run.py                 CLI
arxiv_digest/
  config.py            paths, endpoints, category and journal tables
  listing.py           arXiv listing crawler
  api.py               arXiv Atom API
  ssrn.py              SSRN listing API + Chrome/CDP abstracts and PDFs
  blogs.py             Quantpedia RSS + Man Group Insights
  store.py             seen.json I/O, atomic writes, migrations
  summarize.py         claude CLI, bilingual JSON schema, star rubric
  paper.py             deep reports, math preservation
  render.py            digest and index rendering
  server.py            local one-click server
state/seen.json        the store
state/chrome_profile/  SSRN Chrome profile (not committed)
report/                generated output
index.html             GitHub Pages entry point, regenerated on every report
```

## 8. Git and publishing

Code and generated files are committed together. `state/seen.json` has to travel
with the repo, otherwise a clone re-summarizes everything.

`state/chrome_profile/` is excluded and must stay excluded: 150 MB of cache, and
it holds the `cf_clearance` session cookie.

Two things surfaced while setting this up:

- Git was not installed, and the winget installer needs elevation — it failed
  with exit 12 when the UAC prompt went unanswered. PortableGit and the gh CLI
  zip unpacked into `%LOCALAPPDATA%\Programs` with the user PATH updated need no
  admin rights at all. `run.py publish` looks in that location as well as PATH.
- Pages on the free plan requires a public repository. That means the abstracts
  stored in `seen.json` and the reports are public too. arXiv abstracts are fine
  to redistribute; SSRN abstracts are the authors' and SSRN's, which is a grey
  area. Going private turns Pages off, and that is the lever if it ever matters.
