# Working notes

A running log of decisions, dead ends and measurements. [DESIGN.md](DESIGN.md)
describes the system as it stands now; this file records *how it got there* and
what was tried and rejected, so the same ground is not re-covered later.

Newest entries first.

---

## 2026-08-31 — Aggregator overlap, and three more blogs

Added Alpha Architect, Macrosynergy and Quantocracy.

| Site | Route | Note |
|---|---|---|
| Alpha Architect | `/feed/` | The **blog page is Cloudflare-blocked but the feed is not.** Always try the feed first. |
| Macrosynergy | `/feed/` after a browser warm-up | Page *and* feed both 403. Clearing the challenge once in a real Chrome leaves `cf_clearance`, after which the plain feed returns 200 with 10 items. |
| Quantocracy | homepage scrape | 50 `<article class='qo-entry'>` blocks: outbound link, `Title [Origin Blog]`, an excerpt, a timestamp. |

**Quantocracy overlaps the others by design** — its first entry was literally
"Boundaries of Time Series Momentum [Quantpedia]", already collected directly.
Resolution: keep the direct source, drop the aggregator's copy. Quantocracy
truncates excerpts with `(...)` while the origin feed carries the whole thing, so
the direct entry is strictly better. Two guards, because one is not enough:

1. `blogs.AGGREGATED_DOMAINS` — skip Quantocracy entries whose host is a site
   collected directly *in the same run*.
2. `run._fetch_blogs` — compare against the store by normalized URL, and delete
   stale aggregator copies left behind by an earlier run with a narrower
   `--source`. This mattered in practice: a run of `--source macrosynergy,quantocracy`
   let a Quantpedia link in, and only the store-level pass could remove it.

`norm_url()` strips scheme, `www.`, trailing slash and query. The aggregator and
the origin differed by exactly a trailing slash, so naive string equality missed it.

**Session contamination bit twice.** Sharing one `requests.Session` across sites
made Macrosynergy return 403 and Quantocracy 400, while identical standalone
requests worked. The failed challenge leaves its own `__cf_bm` on the session,
which then conflicts with the cleared cookie. Both listers now issue isolated
requests. Worth remembering for any future Cloudflare-adjacent source.

## 2026-08-31 — Bilingual everything

Code, comments and `DESIGN.md` are English now. `README.md` is English with
`README.ko.md` alongside and links both ways.

Summaries are Korean **and** English, produced by a single `claude -p` call
returning both blocks. Two calls would let `relevance` drift between languages
and cost twice as much. The two versions are written natively, not translated,
with separate style rules.

`seen.json` grew a nesting level:

```
summary: {relevance, keywords, ko: {...}, en: {...}}
```

`store._migrate()` lifts old flat Korean summaries into `summary.ko` on load, so
no manual migration was needed.

The digest page ships both languages in one document. Language-specific nodes are
`data-l="ko"` / `data-l="en"`, CSS shows only the one matching `<html data-lang>`.
Attribute-bound chrome (placeholders, `<option>` text) comes from a small JS
dictionary. Switching is instant; the choice persists in `localStorage`.

Deep reports get one button per language and land at
`report/paper/{id}.{lang}.html`. Existing `{id}.html` files were renamed to
`{id}.ko.html`.

## 2026-08-31 — Cloud updates without a machine running

`.github/workflows/update-digest.yml`: `workflow_dispatch` plus a weekday
06:00 KST schedule. Needs an `ANTHROPIC_API_KEY` secret — a CI runner has no
interactive Claude login to fall back on.

Two limits worth stating plainly:

- **Only people with write access can trigger it.** GitHub does not expose
  workflow triggers to anonymous visitors. A stranger wanting their own copy
  forks or clones and runs locally; the READMEs carry a quick start for that.
- **SSRN is best-effort in CI.** Its challenge is usually refused from datacentre
  IPs, so the default source list is `arxiv,quantpedia,man`. `cmd_fetch` now
  isolates each source in a try/except so one failure cannot lose the others.

`--source` accepts a comma-separated list, which the workflow inputs rely on.

## 2026-08-31 — Git setup on a locked-down machine

Git was not installed and `winget install Git.Git` failed with **exit 12**: the
installer needs elevation and the UAC prompt went unanswered. PortableGit and the
gh CLI zip unpacked into `%LOCALAPPDATA%\Programs`, with the user PATH updated,
need no admin rights at all. `run.py publish` looks there as well as on PATH.

Repository is public because Pages on the free plan requires it. That publishes
the abstracts in `seen.json` too — fine for arXiv, a grey area for SSRN. Going
private turns Pages off; that is the lever if it ever matters.

`state/chrome_profile/` must never be committed: 150 MB of cache **and the
`cf_clearance` session cookie**.

## 2026-08-31 — One-click deep reports

The localStorage queue plus copy-a-command was the most annoying part of using
the tool. `run.py serve` hosts `report/` with `api/ping`, `api/report`,
`api/status` bolted on; the page probes `api/ping` on load and silently falls
back to the old flow when there is no answer. One HTML file therefore works
served, opened as a file, and on Pages.

- One worker only — parallel `claude` calls and Chrome windows interfere.
- The SSRN browser is started once and reused for the server's life; per-job
  startup adds ~7s of Chrome launch plus challenge clearing every time.
- Measured: one SSRN paper, PDF fetch through finished report, ~140s.

## 2026-08-31 — Star rating rewritten

The first rubric asked for "practical relevance" and produced nothing useful:
almost everything landed on 3 or 4. Replaced with **systematic-trading
implementability** — can this be coded into rules a machine trades, and nothing
about academic merit.

Key constraints that made it work:

- Data you cannot obtain caps the score at 2 regardless of results.
- Every score carries a one-line justification that **must mention data
  availability**. That single requirement is what stops the model rating on
  prestige.
- +1 for refuting a popular belief, improving backtest methodology, or being
  original enough to read anyway.

Re-scored 43 papers: 5×2, 4×11, 3×12, 2×7, 1×11, mean 2.67. Law, policy and
survey papers dropped to 1; satellite-imagery and survey-data work dropped to 2.

## 2026-08-31 — Math was garbage, and why

arXiv's LaTeXML output stores the source LaTeX in
`<math alttext="A_{id}(p,r)=\sum...">`. Stripping tags first turned that into
`A id p r`, so every formula in the first deep reports was mangled.

Restore `alttext` into `\( ... \)` **before** removing tags, tell the model to
emit `\( \)` and `\[ \]`, and load MathJax on the page. MathJax is the only
external dependency in any output; offline the LaTeX source still reads fine.

## 2026-08-31 — SSRN behind Cloudflare

SSRN splits in two and only one half is defended: the listing API
(`api.ssrn.com/content/v1/bindings/{jid}/papers`) answers plain requests, while
`papers.ssrn.com` does not. The listing API gives everything except the abstract.

What was tried, in order:

| Approach | Result |
|---|---|
| `requests` with full browser headers | 403 |
| Playwright bundled Chromium, headless | still challenged after 60s |
| Playwright bundled Chromium, headed | same |
| Playwright `channel="chrome"` | same |
| **Chrome we launch ourselves, attached over CDP** | **cleared in ~4s** |

Anything Playwright `launch()`es is flagged as automation; a plain Chrome started
with `--remote-debugging-port` and attached via `connect_over_cdp` is not.

Aggregators were checked as a way to avoid the browser entirely — Crossref,
OpenAlex and Semantic Scholar all 404 on SSRN working papers approved in the last
day or two, which is exactly the set this tool cares about.

**Never detect the challenge by page title.** It is localised: a Korean Chrome
shows "잠시만 기다리십시오…". Wait for the target selector instead.

## 2026-08-31 — arXiv listing gotchas

- One `<dl id='articles'>` block **per date**, not one per document.
- Quiet days still emit a heading plus "No updates for this time period.", so
  empty dates must be skipped when counting "the two most recent dates".
- The markup is `href ="/abs/ID"` — space before `=`. A tidy `href="` pattern
  matches nothing.
- Take dates **per category**. Measured: q-fin.PM was on 08-26/08-25 while
  q-fin.ST and q-fin.TR were on 08-31/08-28. A global top-2 drops q-fin.PM.
- stdlib `urllib` fails TLS verification on this machine; `requests` (certifi)
  works. Use `requests` everywhere.
