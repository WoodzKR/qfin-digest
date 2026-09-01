# Quant Paper Digest

**[Read the digest →](https://woodzkr.github.io/qfin-digest/)** · [한국어](README.ko.md)

New research from arXiv q-fin, SSRN and five practitioner blogs, summarized in Korean
and English. One page, switch languages with a click, no sign-in.

| | |
|---|---|
| **Just want to read it?** | Open the link above. Nothing to install. |
| **Want to refresh it from any device?** | [Run the workflow](#refresh-it-from-anywhere) — a button, no local setup. |
| **Want to run it yourself?** | [Set it up locally](#run-it-on-your-own-machine). |

---

## Refresh it from anywhere

**[Actions → Update digest → Run workflow](https://github.com/WoodzKR/qfin-digest/actions/workflows/update-digest.yml)**

Runs on GitHub's servers, so nothing of yours has to be switched on. The button works
from a phone. It also runs automatically at 06:00 KST on weekdays.

Inputs: which sources, how many recent dates, how many deep reports, which language.
Defaults are fine.

Signing in as the repository owner is required — GitHub does not offer workflow
triggers to visitors. Anyone else who wants to run it can fork and use their own
credentials.

<details>
<summary>One-time setup (already done for this repo)</summary>

Add one of these under **Settings → Secrets and variables → Actions**:

| Secret | Where it comes from |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` — uses a Claude subscription, no API key needed |
| `ANTHROPIC_API_KEY` | A pay-as-you-go API key, used only if the token is absent |

SSRN is left out of the default source list: its Cloudflare challenge is usually
refused from datacentre IPs. Opting it back in will not fail the run.
</details>

## Run it on your own machine

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest

pip install requests playwright pypdf
python -m playwright install chromium
npm i -g @anthropic-ai/claude-code
claude login

python run.py --source arxiv,quantpedia,man,alphaarchitect,macrosynergy,quantocracy
python run.py serve      # one-click deep reports at http://127.0.0.1:8765
```

SSRN additionally needs Chrome or Edge installed; add `--source all` once you have it.
`state/seen.json` comes with the clone, so nothing already summarized is paid for twice.

To publish your own copy: `python run.py publish`.

## Commands

```powershell
python run.py                  # collect, summarize, build the page, open it
python run.py --deep 5 --push  # ... plus deep reports for the top 5, then publish
python run.py serve            # one-click mode
python run.py status           # what is in the store
python run.py paper <id> --lang en
```

| Flag | |
|---|---|
| `--source` | `all`, one source, or a list: `arxiv,quantpedia,man` |
| `--lang` | `ko`, `en` or `both` — language of deep reports |
| `--deep N` | pre-build deep reports for the top N by star |
| `--days N` | recent listing dates per paper source (default 2) |
| `--review` | critique pass before writing a deep report (one extra call) |
| `--force` | redo work that is already done |
| `--push` | publish after a full run |

## What it reads

| | Source | Recent means |
|---|---|---|
| arXiv | q-fin.PM, q-fin.ST, q-fin.TR | 2 latest listing dates per category |
| SSRN | 7 eJournals — QM, TI, GIS, GEX, APV, MEF, MMS | 2 latest approval dates per journal |
| Blogs | Quantpedia, Man Group, Alpha Architect, Macrosynergy, Quantocracy | newest 8 posts each |

Quantocracy is an aggregator, so entries duplicating a site read directly are dropped.

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

## Deep reports

Eight sections, from "at a glance" to the systematic-trading angle, built from the
arXiv HTML edition, the SSRN PDF or the blog article — the abstract only as a fallback,
and the page says so when that happens. Math keeps its original LaTeX and renders with
MathJax.

Korean reports are written directly in Korean, in one pass over the whole paper, under
style rules distilled from [humanize-korean](https://github.com/epoko77-ai/im-not-ai).
There is no separate rewriting step: a rewriter that only sees the finished fragment
cannot keep terminology consistent across sections.

Add `--review` to run a critique pass first — claims, identifying assumptions, validity
threats, the strongest counterargument — which feeds the results and limitations
sections. That pass reads the full paper, so it has the context a rewriter lacks.

---

[DESIGN.md](DESIGN.md) — how it works · [NOTES.md](NOTES.md) — decisions and dead ends
