# Working notes

## 2026-09-01 — Two SSRN reports were written from the abstract, not the PDF

Asked whether a specific report came from the original PDF. It did not:

```
ssrn-7375498 | PDF unavailable — PDF download failed (HTTP 403, 5988 bytes). (abstract only)
ssrn-7363482 | PDF unavailable — PDF download failed (HTTP 403, 5988 bytes). (abstract only)
2608.28399   | arXiv HTML full text
qp-*         | Quantpedia article
```

5,988 bytes is a Cloudflare block page. `ssrn-7363482` had said "SSRN PDF full
text" when first built on 08-31, so the bulk regeneration on 09-01 **downgraded**
both — the reports got shorter and thinner without anything failing loudly.

Cause, in `fetch_fulltext`:

```python
if not entry.get("abstract") or not entry.get("pdf_url"):
    ctx.fetch_abstract(entry)   # ← the only thing that visits SSRN
data = ctx.download_pdf(entry)  # ← needs the cookie that visit earns
```

The download borrows `cf_clearance` from the browser, but that cookie only
exists once the browser has actually been to SSRN. On the first build the
abstract was missing, so the navigation happened and the cookie was there. On the
rebuild everything was cached, the guard skipped the navigation, and the download
went out with no clearance. **The clearance was a side effect of a step that was
conditional; the step that depended on it was not.**

`download_pdf` now owns its precondition: `warm()` before the request when no
`cf_clearance` is held, and once more on a failed response, since a stale cookie
is indistinguishable from a missing one. Verified against the cached entry that
used to fail — 67,141 characters of PDF text in 16s.

The reports did disclose "abstract only" in the header and in section 1, which is
what the prompt requires. Honest, but the fallback was still silent enough to
survive a regeneration. Worth checking `본문 출처` on any report that reads thin.

## 2026-09-01 — Prompt changes do not reach existing output

Asked directly: when a prompt changes, does old output get rebuilt? No. Both
stages skip finished work — `cmd_summarize` on `needs_summary`, `cmd_deep` on the
report file existing. That is the right default (a prompt tweak should not
silently trigger a hundred calls) but it was invisible, so the store quietly
accumulated output from several prompt generations with nothing to tell them
apart. `summarized_at` recorded *when*, never *by what*.

Added `SUMMARY_VERSION` and `REPORT_VERSION` in config, stamped onto each entry
as it is written, surfaced by `run.py status`, and acted on by `--stale`:

```
current prompts — summary 2026-09-01, report 2026-09-01
  summaries   : unrecorded 100
  deep reports: unrecorded 8
```

Bump the constant when a prompt changes in a way worth redoing; leave it alone
for wording fixes. `--stale` redoes only what does not match. `--force` still
redoes everything.

One distinction worth keeping: **"unrecorded" is not "old"**. Everything already
in the store predates the stamp, so we genuinely cannot tell which prompt made
it. `--stale` includes them because unverifiable is a reason to redo, but the
status text says "may already match" rather than asserting they are behind.
Claiming false staleness would push a pointless hundred-call rerun.

**Resolved the same day.** Everything currently in the store *was* produced by
the prompts as they stand, so the migration now adopts it as current rather than
flagging it. The nag is gone and a future bump means something.

The two stamps are deliberately independent. Changing the deep-report prompt
flags the eight reports and leaves the hundred summaries alone — verified by
bumping `REPORT_VERSION` alone:

```
current prompts — summary 2026-09-01, report 2026-09-02-TEST
  summaries   : 2026-09-01 100
  deep reports: 2026-09-01 8
  8 deep reports predate REPORT_VERSION:
     python run.py deep --deep 8 --stale --lang both
```

`summarize --stale` in that state prints "nothing to summarize", which is the
whole point: deep-report work should never drag summaries into a rerun.

One trap the test caught. The migration first credited legacy entries with
`SUMMARY_VERSION`/`REPORT_VERSION` — *the current constants*. Since it re-runs on
every load and `status` does not save, bumping a version silently re-stamped the
old entries as new, and nothing could ever go stale. The backfill has to use a
fixed literal, `LEGACY_VERSION`, so a bump actually bites.

## 2026-09-01 — Local-only, git as the publishing channel

Deleted `.github/workflows/`. The cloud runner is gone, along with the split
brain it created: two places that could collect and push, one of which could only
reach five of seven sources and needed its own credential in a repository secret.

The model now is one sentence: **everything runs here, git publishes the result.**

- `setup.bat` — once per machine. Python packages, Chromium, the Claude CLI, the
  login. Checks each piece and names what is missing instead of dying halfway.
- `update.bat` — the pipeline. All sources, summarize, rebuild, push.
- `run.py publish` — the distribution step, and now the only writer to the remote.

What this buys, beyond simplicity:

- **No more merge conflicts.** Every conflict this repo has had came from the bot
  pushing generated files while local work was in flight.
- **No credential in a secret.** The CI path needed `CLAUDE_CODE_OAUTH_TOKEN`
  stored on GitHub; a local run just uses the CLI's own login. The secret can be
  deleted from repo settings — nothing reads it now.
- **One source list.** No more "cloud does five, local does seven".

What it costs: no updating from a phone. That was the workflow button's one real
advantage. Reversible — the workflow file is one `git revert` away, and the
secret still exists until deleted.

`state/seen.json` staying committed is what makes "download and run" work: a
clone on a second machine already knows everything summarized so far and pays for
none of it again.

## 2026-09-01 — Manual only, and one entry point

Removed the `schedule:` block. Every run spends Claude subscription quota, and a
06:00 cron spends it whether or not anyone is going to read the result. It also
caused the only merge conflict this repo has had: the bot pushed generated files
while local work was in flight. `workflow_dispatch` stays, so the phone button
still works.

`update.bat` is now the one thing to run at the machine. It exists because the
full update is four steps that are easy to get wrong in the wrong order —
pull, `run.py all --source all`, publish — and because the cloud path covers only
five of seven sources. SSRN and Macrosynergy need a real browser.

Batch, not PowerShell: the execution policy here blocks unsigned `.ps1`, which is
what broke `claude setup-token` earlier. A `.bat` double-clicks and runs.

Details that matter:

- Prepends `%LOCALAPPDATA%\Programs\PortableGit\cmd` when `git` is missing from
  PATH, since a terminal opened before the install has a stale PATH.
- `chcp 65001` and `PYTHONIOENCODING=utf-8`, or the Korean output is mojibake.
- `%*` passes arguments through and *overrides* the default `--source all`,
  so `update.bat --source ssrn` narrows it.
- A failed pull prints the conflict recipe rather than a raw git error, and says
  the plainly true thing: everything under `report/` and `index.html` can be
  thrown away and rebuilt from `seen.json`.
- Ends in `pause` so a double-clicked window does not vanish on error.

## 2026-09-01 — The same scoping bug, one stage earlier

After merging a scheduled run: `88 papers · 81 summarized`. Seven Man Group
articles sat in the store with abstracts and no summary.

Same shape as the digest-shrinking bug, caught one stage earlier in the pipeline.
`run.py all` was calling `cmd_summarize(day_filter=days)` — only the dates *this
run* fetched. Anything already in the store but outside that window stays
unsummarized forever, and blog posts make that permanent: once an article rotates
off Man's landing page it is never fetched again, so its date never reappears in
`days`, so it is never picked up.

Now only **fetching** is scoped to a run. Summarizing and rendering both heal the
whole store. Stated as a rule since it has now bitten twice:

> Scope the step that talks to the network. Never scope the steps that maintain
> the store — they exist to make it whole.

Backfilled the seven by hand with `run.py summarize`, which needed no arguments:
the store already knew what was missing. That is the property worth preserving.

## 2026-09-01 — Dropped the polish pass; translate natively instead

The humanize-korean second pass is gone. It rewrote a finished HTML fragment
without the paper behind it, and it showed: terminology drifted between sections
because the rewriter could not know that "타이밍 알파" in section 3 and the phrase
it reached for in section 6 were the same defined quantity. It also reached for
less common words to sound more native — "비교했다" → "견주었다" — which reads worse,
not better. Both are failure modes of editing text you cannot see the source of.

The taxonomy stays, as **rules in the generation prompt**. Writing the whole
report in one pass means the model has the paper, the reviewer notes and all
eight sections in view while choosing words, which is exactly the context a
standalone rewriter lacks. Two rules added off the back of this:

- Terminology consistency — one translation per concept, held across sections;
  follow the paper's own definitions even when a smoother word exists.
- Prefer common words. Do not pick rarer vocabulary to seem more idiomatic.

`--no-polish` is removed; there is nothing to skip. `--review` stays — that pass
reads the *full paper*, so it has the context this one lacked, and it measurably
sharpened the analysis.

The general lesson: a post-hoc rewriter is the wrong tool when the constraint is
semantic rather than stylistic. Give the rules to whoever is holding the context.

## 2026-09-01 — SSRN in CI: blocked, and slow about it

A workflow run with SSRN in the source list hung. The log:

```
[1/9] FAIL 7370498 — Cloudflare challenge not cleared (no abstract element).
[2/9] FAIL 7370460 — Cloudflare challenge not cleared (no abstract element).
...
```

Being blocked from a datacentre IP was expected and is documented. Waiting **90
seconds per paper** to rediscover it was not — nine papers meant thirteen minutes
of a runner doing nothing, and the run was still going when it got cancelled.

Two fixes, both about failing fast rather than failing differently:

1. **Detect the challenge, do not just time out.** `_challenge_up()` looks for
   `challenges.cloudflare.com` / `cf_chl_opt` in the live DOM. A challenge that
   clears at all clears in seconds, so if the markup is still there after a 25s
   grace, stop waiting. (Still never match on the title — it is localised.)
2. **Circuit breaker.** Two consecutive `SsrnBlocked` and the whole SSRN abstract
   phase raises, skipping the rest. Every remaining paper would fail identically.

Worst case drops from ~13 min to ~50s. Abstracts already fetched are kept, and
`cmd_fetch` isolates sources, so the other five still land.

`SsrnBlocked` is a distinct exception from `SsrnError` precisely so "this network
is refused" can be told apart from "this one page was odd" — only the former
should abort the batch.

Verified the happy path is unharmed: two papers from a residential network, 16s,
both abstracts fetched.

The workflow default now lists `arxiv,quantpedia,man,alphaarchitect,quantocracy`
— everything that works without a real browser. SSRN and Macrosynergy are local-only.

## 2026-08-31 — Two external skills: one wired in, one kept optional

Installed both under `~/.claude/skills`, cloned to `~/.claude/vendor` so updates
are a `git pull`.

### humanize-korean — wired into every Korean deep report

[epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai). Used two ways,
which is the pattern worth repeating:

1. **Distilled into the prompt.** The high-signal patterns from its taxonomy are
   inline rules in `summarize.py` and `paper.py`, so the *first* draft avoids
   them. Costs nothing per call.
2. **As a second pass.** `paper.polish_korean()` runs the actual skill over the
   finished Korean fragment. Only for `lang="ko"`, only for deep reports — 80
   short summaries a day do not justify doubling the calls.

Guardrails, because a rewriter can quietly wreck a document: the result is
rejected and the original kept if the size moves more than ±30% or the `<h2>`
count changes. Failures are non-fatal.

Measured on one arXiv paper (two independent generations, so this mixes
generation variance with the polish effect — treat the direction, not the
magnitude, as the finding):

| | no polish | polished |
|---|---|---|
| AI tells | 3 | **0** |
| comma after connective ending | 12 | **4** |
| `<h2>` sections | 8 | 8 |
| display math | 5 | 5 |

### academic-research-skills — opt-in only

[imbad0202/academic-research-skills](https://github.com/imbad0202/academic-research-skills),
CC-BY-NC-4.0. Four skills, but they are built for *writing and peer-reviewing
manuscripts* with 5-seat and 13-agent panels. Running that per item, 80 times a
day, is the wrong shape.

What is useful is the review *lens*. `paper.review_paper()` runs one critique
pass — claims, identifying assumption, validity threats, counterargument,
numbers not to trust, what a practitioner needs that is missing — and feeds it
into sections 5 and 6 of the Korean report so the analysis is not a paraphrase
of the paper's own framing.

Behind `--review` because it adds a call per report. The full deep-report chain
is then **analyze → write → polish**, three calls.

**It earns its cost.** First run on `2608.28399`: 10,241 characters of reviewer
notes, and the report's results and limitations sections stopped paraphrasing the
paper. Things the critique pass caught that the plain prompt had not:

- The same-day shuffle control is 0 by construction, yet reads −8.7bp with CI
  [−10.4, −7.1] — nine standard errors out. The null distribution the paper leans
  on does not hold, so every timing level carries an unknown offset.
- Scoring sample sizes that must be identical are not: 13,710 / 13,716 / 13,717.
- Look-ahead in three of fourteen headline rows: chart and multimodal features are
  "reconstructed from overlapping forward return labels", including the largest cell.
- Selection on the dependent variable — roughly 54% of stock-days survive the
  constant-action filter, and the survivors skew toward exactly the choppy paths
  where short-term reversal is strongest.
- The 20-minute condition's prompt says 10 minutes.

That is referee-grade reading, not summary.

Cost, measured: about 27 minutes for the chain, and **the polish step timed out**
at its 900s budget because it runs last. Fixed by giving polish its own larger
budget (`max(timeout, 1800)`) — it is non-fatal either way, but silently shipping
an unpolished report is the wrong default.

Batched polish on short summaries was measured and **rejected**: 10 summaries in
one call takes 199s, so 80 would be 8 calls and ~27 minutes — affordable — but 8
of 10 one-liners came back unchanged, and the two that changed were lateral
("비교한" → "견준", which is less common, not clearer). The inline rules already do
the work at that length; a 40-character line has nowhere to accumulate
translationese. Short text also has no slack: one shifted word is a larger share
of the meaning. Long form is where the patterns pile up and the pass pays off.

Note the skill dirs in that repo's `skills/` are git symlinks that Windows
checks out as 0-byte files; the real directories are at the repo root and they
reference `shared/` by relative path. Installing it properly means the plugin
marketplace route, not copying folders.

## 2026-08-31 — Korean style rules, rebuilt from a real taxonomy

The earlier style block was a handful of guesses ("no passive voice", "no
translationese particles"). Replaced with rules taken from
[epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai), a Claude skill
that classifies AI tells in Korean writing — 10 categories, 70+ patterns, graded
S1/S2/S3 against a measured human corpus.

Folded in the high-signal items and skipped the rest, since the prompt ships on
every call:

| Pattern | Rule now given |
|---|---|
| C-11 | **No comma directly after a connective ending** (-고, -며, -지만…). Their strongest single discriminator — 4.84× separation. |
| A-8, A-9 | No double passive; `~에 의해` becomes an actor subject |
| A-7 | `~을 가지고 있다` → `~이 있다 / ~이 강하다` |
| A-15, D-2 | Banned all-purpose verbs 보여준다/제공한다/시사한다 — use a concrete verb and a number |
| D-4 | Banned hype words 혁신적/획기적/압도적/전례 없는 |
| D-14 | Banned dead metaphors 잠식/청사진/적신호/신호탄 — **measured 0 occurrences in human writing** |
| A-21, D-7 | Banned escalation formulas `단순한 X를 넘어 Y`, `X에서 Y로` |
| D-8, I-2 | Banned cleft `핵심은 ~이다` / `주목할 점은` |
| D-10 | Banned inverted closer `~하는 이유다` |
| D-1, D-9, H-1 | Closing lexicon (결론적으로/따라서/이를 통해/결국) capped at two per report; no three fronted connectives in one paragraph |
| E-1, E-2 | Vary sentence length deliberately; no more than three or four identical endings in a row |
| F-4, F-5 | No stacked -적/-성/-화 |

Also kept their **modality-preservation** rule, which matters here: a paper's
hedged claim (`~할 수 있다`) must not harden into an assertion. Summaries make
factual claims about someone else's work, so shifting confidence is a real error,
not just a style issue.

A/B on one SSRN paper, before and after:

> before: 폭락 다음날 반등 효과는 대부분 집계 오류이고, 지수 -7% 이하만 살아남는다.
> after : 급락 후 반등 효과는 대부분 중복 집계가 만든 착시다.

> before: 날짜 단위 집계, 중첩 임계값, 다중검정, 부트스트랩 보정
> after : 날짜 단위 집계, 중첩 임계값, FWER, 블록 부트스트랩 보정

Noun stacking drops and verbs come back. All 80 summaries were regenerated.

## 2026-08-31 — A narrow run deleted the published digest

First real Actions run (`--source arxiv --days 1`) committed
`2 files changed, 38 insertions(+), 1786 deletions(-)`. The store was fine; the
**rendered page** had been rebuilt containing only the 4 papers that run touched,
replacing the 80-item digest.

Cause: `run.py all` passed its own `--source` and the dates it had just fetched
into `render.build()`. Fetching and summarizing *should* be scoped to a run.
Rendering never should — the whole point of `seen.json` is accumulation, and the
page has filters and date sections anyway.

Fix: `all` now renders the entire store (`day_filter=None`, sources ignored).
`_build_report()` grew an `all_sources` flag so `--source` stays a fetch filter
and cannot narrow the output. The standalone `report` command keeps its filters
for ad-hoc use.

Lesson for any future scheduled job here: **a partial input must never produce a
smaller published artifact.** Check the diff stat on the first automated commit.

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

## 2026-08-31 — Who may trigger the workflow: decided, nobody new

`workflow_dispatch` is restricted by GitHub to accounts with **write access**.
On a public repo everyone can read the Actions tab and the run logs, but the
"Run workflow" button simply is not there for them. `repository_dispatch` needs a
PAT, so it is no more open.

Options considered for letting outsiders run it, and why the answer is no:

| Route | Who | Cost |
|---|---|---|
| leave as is | owner + collaborators | — |
| add a collaborator | that person | also grants push |
| `issues` trigger + username allowlist | listed accounts | run-only access, but a list to maintain |
| `issues` trigger, ungated | anyone | **anyone can burn the Claude subscription quota** |
| fork | anyone | on their own token, not ours |

Note that issue-triggered workflows **do** get repository secrets, unlike a pull
request from a fork. Opening one ungated is a known abuse path: one spam issue,
one run, one bite out of the subscription.

Decision: leave it. Reading the digest needs no permissions at all — Pages is
public — and anyone who wants to *run* it forks and brings their own token,
which the READMEs' Quick start already covers.

## 2026-08-31 — CI auth without an API key

No API subscription here, only the Claude Code CLI. That is fine everywhere:

- **Locally** — nothing to change. The whole pipeline already shells out to
  `claude -p`, which uses whatever the CLI is logged in as.
- **In CI** — `claude setup-token` (present in CLI 2.1.251, "requires Claude
  subscription") mints a long-lived token. Verified `CLAUDE_CODE_OAUTH_TOKEN`
  is a real env var by finding the string in the 207 MB native binary, since it
  is not mentioned in `--help`.

The workflow now takes either secret and prefers the token, explicitly
`unset`ting `ANTHROPIC_API_KEY` when both are present so the key cannot quietly
take over. Only `workflow_dispatch` and `schedule` trigger it, so a fork's pull
request can never reach the secrets.

## 2026-08-31 — Cloud updates without a machine running

`.github/workflows/update-digest.yml`: `workflow_dispatch` plus a weekday
06:00 KST schedule.

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
