# Quant Paper Digest — arXiv q-fin + SSRN

**[한국어 README](README.ko.md)** · **[Live digest →](https://woodzkr.github.io/qfin-digest/)**

Collects new work from arXiv q-fin.PM/ST/TR, seven SSRN eJournals and five practitioner
blogs; summarizes each item in Korean *and* English with a local Claude Code CLI; and
renders one self-contained HTML digest. Anything already summarized is skipped on the
next run.

[DESIGN.md](DESIGN.md) describes the system; [NOTES.md](NOTES.md) is the running log of
decisions, dead ends and measurements.

## Requirements

```powershell
npm i -g @anthropic-ai/claude-code     # the summarizer
pip install requests playwright pypdf  # SSRN path
python -m playwright install chromium
```

SSRN sits behind Cloudflare, so an installed **Chrome (or Edge)** is required. The
script starts a throwaway-profile Chrome, parks it off-screen, and closes it when done.
With `--source arxiv` nothing but Python is needed.

## Usage

```powershell
python run.py                      # crawl -> summarize -> report, then open it
python run.py --deep 5             # same, but also pre-build the top 5 deep reports
python run.py serve                # one-click mode (see below)

python run.py --source arxiv       # arXiv only
python run.py --source ssrn        # SSRN only

python run.py fetch                # listings and abstracts only
python run.py summarize            # summarize whatever is missing one
python run.py deep --deep 3        # deep reports for the top 3
python run.py report --all         # rebuild the digest over everything
python run.py status               # what is in the store
python run.py paper 2608.28399 --lang en
python run.py publish              # commit generated files and push
```

| Flag | Meaning |
|---|---|
| `--source` | `all` (default), one source, or a list: `arxiv,quantpedia,man` |
| `--blog-limit N` | newest N posts per blog (default 8) |
| `--lang ko\|en\|both` | language for deep reports (default `ko`) |
| `--days N` | recent listing dates per source (default 2) |
| `--workers N` | parallel summaries (default 3) |
| `--deep N` | pre-build deep reports for the top N by star |
| `--force` | redo work that is already done |
| `--all` | build the digest over everything, not just today |
| `--push` | run `publish` after `all` |
| `--port N` | `serve` port (default 8765) |
| `--no-open` | do not open a browser |
| `--show-browser` | keep the SSRN Chrome window on screen |
| `--chrome <path>` | explicit Chrome/Edge executable |

### One-click mode — `python run.py serve`

A static page cannot call Claude, so the plain file has to fall back to copying a
command into a terminal. `serve` hosts `report/` with a small API attached, and the
buttons then build on click:

```
📄 한국어 / 📄 English  →  ⏳ fetching PDF…  →  ⏳ writing report…  →  📄 (opens)
```

The digest HTML is rebuilt automatically when a report finishes, and the SSRN Chrome
instance is started once and reused for the server's life. Opened as a file or on
GitHub Pages, the page probes `api/ping`, gets nothing, and silently reverts to the
copy-a-command flow. A green `local server connected` badge shows which mode you are in.

## Sources

**arXiv** — q-fin.PM (Portfolio Management), q-fin.ST (Statistical Finance),
q-fin.TR (Trading & Market Microstructure). Abstracts come from the arXiv Atom API.

**SSRN** — badges on each card:

| Badge | eJournal |
|---|---|
| QM | Quantitative Methods in Investing & Financial Statement Analysis |
| TI | Technology & Investing |
| GIS | Global Investment Strategy |
| GEX | Global Equities, Exchanges & Investment Indices |
| APV | Capital Markets: Asset Pricing & Valuation |
| MEF | Capital Markets: Market Efficiency |
| MMS | Capital Markets: Market Microstructure |

**Blogs** — practitioner writing rather than papers, so they are taken as the newest
N posts instead of "the two most recent dates".

| Badge | Site | How |
|---|---|---|
| QP | [Quantpedia](https://quantpedia.com/blog/) | RSS feed |
| MAN | [Man Group Insights](https://www.man.com/insights) | landing page + one request per article |
| AA | [Alpha Architect](https://alphaarchitect.com/blog/) | RSS feed (the blog page itself is Cloudflare-blocked) |
| MS | [Macrosynergy](https://macrosynergy.com/research/blog/) | RSS feed, after clearing Cloudflare in a real Chrome |
| QC | [Quantocracy](https://quantocracy.com/) | homepage scrape of its curated link list |

Quantocracy is an aggregator, so it overlaps the sites above. Entries pointing at a
site collected directly are dropped, and the direct entry is kept — Quantocracy
truncates its excerpts while the origin's own feed carries the whole thing. The store
is also checked by normalized URL, which catches copies left by an earlier run with a
narrower `--source`.

## The digest page

- **Language switch** — 한국어 / English, applied instantly. Both are in the page.
- **Filters** — source (arXiv / SSRN), field (PM·ST·TR, QM·TI·GIS·GEX·APV·MEF·MMS),
  free-text search over titles, summaries, authors and keywords.
- **Cards** — one-liner plus ★1–5. Expanding shows 3–4 bullets, method, data,
  the trading angle, why it got that score, keywords and the original abstract.
- **Buttons** — `abs`, `PDF`, and one deep-report button per language.

### ★ = systematic-trading implementability

This does not score academic quality. It scores whether the paper can be turned into
rules a machine can trade.

| ★ | Meaning |
|---|---|
| 5 | Explicit entry/exit rules on public, standard data. Backtestable as written. |
| 4 | Gives a signal or method reproducible from standard data; parameters left to you. |
| 3 | Useful features or portfolio techniques, but needs substantial further design. |
| 2 | High barrier — satellite imagery, surveys, proprietary order flow, ultra-low latency. |
| 1 | Theory, policy, law or survey. Nothing to automate. |

**+1** if it refutes a popular belief, improves backtest methodology, or is original
enough to be worth reading anyway. Data you cannot obtain caps the score at 2 no matter
how good the results look. Every score carries a one-line justification that must
mention data availability; expand a card to read it.

## Deep reports

Eight sections: at a glance, the gap, method, data and design, results, limitations,
systematic-trading angle, related concepts.

Body text comes from the arXiv HTML edition or the SSRN PDF. If neither can be had, the
abstract is used and the page says so. Math is preserved as real LaTeX and rendered
with MathJax — arXiv's `<math alttext="...">` is restored before tags are stripped, so
subscripts survive.

Files land at `report/paper/{id}.{lang}.html`.

## Git and GitHub Pages

Code *and* generated files are committed. `state/seen.json` has to travel with the repo,
otherwise a clone on another machine re-summarizes everything.

Excluded in `.gitignore`:

- `state/chrome_profile/` — 150 MB of cache **and the `cf_clearance` session cookie**.
  Never commit this.
- `state/*.bak`, `state/*.tmp`, `__pycache__/`

`index.html` at the repository root is regenerated on every `report` run and is the
GitHub Pages entry point.

```powershell
python run.py --deep 5 --push   # crawl -> summarize -> deep reports -> report -> push
python run.py publish           # publish whatever is already generated
python run.py publish -m "note"
```

`publish` writes a message like `digest 2026-08-31 — 59 summaries, 6 reports` on its own.
Pages picks the change up a minute or two after the push. If `git` is not on PATH,
`%LOCALAPPDATA%\Programs\PortableGit` is also searched.

## Updating from the web, with no machine of your own running

`.github/workflows/update-digest.yml` runs the whole pipeline on GitHub's servers.

- **Actions → Update digest → Run workflow** starts it by hand. That button works from
  a phone, and needs nothing switched on at home.
- It also runs on a schedule: 06:00 KST, weekdays.
- Inputs let you pick sources, how many dates, how many deep reports and which language.

One-time setup: add an `ANTHROPIC_API_KEY` secret under
**Settings → Secrets and variables → Actions**. The summarizer is the Claude Code CLI,
and a CI runner has no interactive login to fall back on, so usage is billed to that
API key.

Two caveats worth knowing:

- **Only people with write access can press that button.** GitHub does not expose
  workflow triggers to anonymous visitors, and it should not. Someone else who wants
  their own copy should fork or clone and run it locally — the Quick start below is
  written for exactly that.
- **SSRN is best-effort in CI.** Its Cloudflare challenge is usually refused from
  datacentre IPs, so the default source list is `arxiv,quantpedia,man`. Opting SSRN
  back in will not fail the run if it gets blocked; the other sources still land.

## Quick start for someone else's machine

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest
pip install requests playwright pypdf
python -m playwright install chromium
npm i -g @anthropic-ai/claude-code
claude login          # or set ANTHROPIC_API_KEY

python run.py --source arxiv,quantpedia,man   # no browser needed
python run.py serve                            # one-click deep reports
```

`state/seen.json` comes with the clone, so nothing already summarized is paid for twice.
Add `--source all` once Chrome is installed to include SSRN.

## Layout

```
run.py                 CLI
arxiv_digest/
  config.py            paths, endpoints, category and journal tables
  listing.py           arXiv /list/{cat}/recent crawler
  api.py               arXiv Atom API
  ssrn.py              SSRN listing API + Chrome/CDP abstract and PDF fetch
  store.py             seen.json I/O, atomic writes, schema migration
  summarize.py         claude CLI calls, bilingual JSON schema
  paper.py             deep reports, math preservation
  render.py            digest and index rendering
  server.py            local one-click server
state/
  seen.json            the store — this is what prevents re-summarizing
  chrome_profile/      SSRN Chrome profile (holds cf_clearance; not committed)
report/                generated output
```

Delete `state/seen.json` to redo everything. To redo one paper, drop its `summary` key
and run `python run.py summarize`.
