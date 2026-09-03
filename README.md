# Quant Paper Digest

**[Read the digest →](https://woodzkr.github.io/qfin-digest/)** · [한국어](README.ko.md)

New research from arXiv q-fin, SSRN and four practitioner blogs, summarized in Korean
and English. One page, switch languages with a click, no sign-in.

Everything runs on your own machine. Git is only how the finished page gets published —
nothing collects or summarizes in the cloud.

## Get it running

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest
setup.bat      # once per machine
update.bat     # every time you want fresh papers
```

`setup.bat` installs Python packages, Chromium, the Claude Code CLI, and signs you in.
It checks each piece and tells you what is missing rather than failing halfway.

`update.bat` is the whole pipeline: collect every source, summarize what is new,
rebuild the page, push. Double-click it or run it from a terminal.

```powershell
update.bat                 # all seven sources, then publish
update.bat --deep 3        # ... and pre-build the top 3 deep reports
update.bat --source ssrn   # just one source
```

On an error nothing is published, and whatever was collected stays in
`state/seen.json`, so re-running picks up where it stopped.

### What you need

| | |
|---|---|
| Python 3.10+, Node.js | `setup.bat` checks both and links to the installers |
| A Claude subscription | The summarizer is the Claude Code CLI. No API key needed. |
| Chrome or Edge | Only for SSRN and Macrosynergy, which sit behind Cloudflare |

## Deep reports

Eight sections, from "at a glance" to the systematic-trading angle, built from the
arXiv HTML edition, the SSRN PDF or the blog article — the abstract only as a fallback,
and the page says so when that happens. Math keeps its original LaTeX and renders with
MathJax.

Double-click **`report.bat`**. It starts the local server and opens the digest with
the report buttons live: click `📄 한국어` or `📄 English` on a card and it builds on the
spot — no terminal. Close the window when done, then `update.bat` to publish.

The button becomes a link to the finished report as soon as it is built, and any other
open tab picks it up when you switch back to it. (`python run.py serve` is the same
thing without the wrapper.)

For a paper you actually care about, add `--review`. A critique pass reads the full
paper first — claims, identifying assumptions, validity threats, the strongest
counterargument — and feeds the results and limitations sections. About 27 minutes.

```powershell
python run.py paper ssrn-7363482 --lang ko --review
```

Korean is written directly in Korean, in one pass over the whole paper, under style
rules distilled from [humanize-korean](https://github.com/epoko77-ai/im-not-ai). There
is no separate rewriting step: a rewriter that only sees the finished fragment cannot
keep terminology consistent across sections.

## Commands

`update.bat` covers the normal case. Underneath:

```powershell
python run.py                  # collect, summarize, rebuild, open
python run.py fetch            # collect only
python run.py summarize        # summarize anything missing one
python run.py report --all     # rebuild the page
python run.py publish          # commit and push
python run.py status           # what is in the store
```

| Flag | |
|---|---|
| `--source` | `all`, one source, or a list: `arxiv,quantpedia,man` |
| `--lang` | `ko`, `en` or `both` — language of deep reports |
| `--deep N` | pre-build deep reports for the top N by star |
| `--days N` | recent listing dates per paper source (default 2) |
| `--review` | critique pass before writing a deep report |
| `--stale` | redo only what an older prompt produced |
| `--force` | redo work that is already done |
| `--push` | publish after a full run |

### When a prompt changes

Existing output is never rebuilt automatically — a wording tweak should not cost a
hundred calls. Each summary and report records which prompt made it, and
`run.py status` shows the split:

```
current prompts — summary 2026-09-01, report 2026-09-01
  summaries   : 2026-09-01 100
  deep reports: 2026-09-01 8
  everything is on the current prompts
```

Bump `SUMMARY_VERSION` or `REPORT_VERSION` in `arxiv_digest/config.py` when a change
is worth applying to old output, then `--stale` redoes only the mismatches. The two
are independent: changing the deep-report prompt flags the reports and leaves the
summaries alone.

## What it reads

| | Source | Recent means |
|---|---|---|
| arXiv | q-fin.PM, q-fin.ST, q-fin.TR | 2 latest listing dates per category |
| SSRN | 6 eJournals — QM, GIS, GEX, APV, MEF, MMS | 2 latest approval dates per journal |
| Blogs | Quantpedia, Alpha Architect, Macrosynergy, Quantocracy | newest 8 posts each |

Quantocracy is an aggregator, so entries duplicating a site read directly are dropped.

Man Group and SSRN's *Technology & Investing* were removed after scoring them: 17 of 17
Man Group pieces and 18 of 23 TI papers came out at ★1. Both publish real work — macro
commentary and non-financial technology research — but nothing this tool can rate, so
they only weighed down the averages and the sort.

## The star rating

★ measures **whether a paper can be traded systematically** — not academic quality.

| ★ | |
|---|---|
| 5 | Explicit entry/exit rules on public, standard data. Backtestable as written. |
| 4 | A signal or method reproducible from standard data; parameters left to you. |
| 3 | Useful features or portfolio techniques, but needs real design work. |
| 2 | High barrier — satellite imagery, surveys, proprietary order flow, low latency. |
| 1 | Theory, policy, law, survey. Nothing to automate. |

**+1** for refuting a popular belief, improving backtest methodology, or being original
enough to read anyway. Data you cannot obtain caps the score at 2. Every score carries a
one-line reason naming the data it needs — expand a card to see it.

## Publishing

`state/seen.json` is committed along with the generated pages. It is what stops a
paper being summarized twice, so a clone on another machine starts where this one left
off. `index.html` at the repository root is the GitHub Pages entry point and is
rebuilt on every run. It links a combined view — every paper, ranked by star,
dates ignored — and one page per listing date holding only that date. Each digest
has a `← Index` link back.

Never commit `state/chrome_profile/` — it holds a `cf_clearance` session cookie.
`.gitignore` already excludes it.

---

[DESIGN.md](DESIGN.md) — how it works · [NOTES.md](NOTES.md) — decisions and dead ends
