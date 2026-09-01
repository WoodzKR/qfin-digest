"""Shared paths, endpoints and source definitions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
REPORT_DIR = ROOT / "report"
PAPER_DIR = REPORT_DIR / "paper"
CHROME_PROFILE = STATE_DIR / "chrome_profile"

SEEN_PATH = STATE_DIR / "seen.json"

# Languages every summary and deep report is produced in.
LANGS = ("ko", "en")
LANG_LABEL = {"ko": "한국어", "en": "English"}

# Two independent version stamps, so a change to one never drags the other into
# a rerun. Bump only the one you actually changed:
#
#   SUMMARY_VERSION  summarize.py — the card summaries and the star rubric.
#                    100 calls to redo.
#   REPORT_VERSION   paper.py — the eight deep-report sections and their style.
#                    A handful of calls to redo, since reports are on-demand.
#
# Bump for a change that makes older output worth redoing; leave it alone for
# wording fixes. Nothing is redone automatically — `--stale` acts on a bump and
# `run.py status` shows what does not match.
SUMMARY_VERSION = "2026-09-01"   # bilingual + trading rubric + style rules
REPORT_VERSION = "2026-09-01"    # native Korean, no rewrite pass

# What output written before version stamping existed is credited with. A fixed
# literal, never the constants above: adopting "whatever is current" would
# re-stamp legacy entries on every load and they could never go stale.
LEGACY_VERSION = "2026-09-01"

# ── arXiv ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "q-fin.PM": "Portfolio Management",
    "q-fin.ST": "Statistical Finance",
    "q-fin.TR": "Trading & Market Microstructure",
}

LISTING_URL = "https://arxiv.org/list/{cat}/recent?skip=0&show=2000"
API_URL = "https://export.arxiv.org/api/query"
ABS_URL = "https://arxiv.org/abs/{id}"
PDF_URL = "https://arxiv.org/pdf/{id}"
HTML_URL = "https://arxiv.org/html/{id}v1"

API_BATCH = 100
API_SLEEP = 3.0

# ── SSRN ─────────────────────────────────────────────────────────────────
# journal_id -> (badge, full journal name)
SSRN_JOURNALS = {
    "4058861": ("QM", "Quantitative Methods in Investing & Financial Statement Analysis"),
    "4058853": ("TI", "Technology & Investing"),
    "4058857": ("GIS", "Global Investment Strategy"),
    "4058865": ("GEX", "Global Equities, Exchanges & Investment Indices"),
    "1508951": ("APV", "Capital Markets: Asset Pricing & Valuation"),
    "1504403": ("MEF", "Capital Markets: Market Efficiency"),
    "1504404": ("MMS", "Capital Markets: Market Microstructure"),
}

SSRN_API_URL = "https://api.ssrn.com/content/v1/bindings/{jid}/papers"
SSRN_ABS_URL = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id={id}"
SSRN_PDF_URL = "https://papers.ssrn.com/sol3/Delivery.cfm/{id}.pdf?abstractid={id}&mirid=1"
SSRN_JOURNAL_URL = ("https://papers.ssrn.com/sol3/JELJOUR_Results.cfm"
                    "?form_name=journalBrowse&journal_id={jid}")
SSRN_PAGE_SIZE = 50
SSRN_MAX_SCAN = 300          # max papers to scan per journal while hunting recent dates
SSRN_CDP_PORT = 9333         # kept away from a user's own Chrome debugging port
SSRN_NAV_SLEEP = 1.2         # seconds between abstract page loads

# ── Practitioner blogs ───────────────────────────────────────────────────
QUANTPEDIA_FEED_URL = "https://quantpedia.com/feed/"
QUANTPEDIA_BLOG_URL = "https://quantpedia.com/blog/"
QUANTPEDIA_LABEL = "Quantpedia"
MAN_INSIGHTS_URL = "https://www.man.com/insights"
MAN_LABEL = "Man Group"
ALPHAARCH_FEED_URL = "https://alphaarchitect.com/feed/"
ALPHAARCH_LABEL = "Alpha Architect"
MACROSYNERGY_FEED_URL = "https://macrosynergy.com/feed/"
MACROSYNERGY_BLOG_URL = "https://macrosynergy.com/research/blog/"
MACROSYNERGY_LABEL = "Macrosynergy"
QUANTOCRACY_URL = "https://quantocracy.com/"
QUANTOCRACY_LABEL = "Quantocracy"

# Macrosynergy is behind the same kind of challenge as SSRN, so it borrows the
# browser trick on its own debugging port.
MACROSYNERGY_CDP_PORT = 9334

# Blogs publish irregularly, so they are taken as "newest N posts" rather than
# "the two most recent listing dates".
BLOG_LIMIT = 8

BLOG_SOURCES = ("quantpedia", "man", "alphaarchitect", "macrosynergy", "quantocracy")

# Blog badge -> full site name, used for chips and card badges.
BLOG_LABELS = {
    "QP": QUANTPEDIA_LABEL,
    "MAN": MAN_LABEL,
    "AA": ALPHAARCH_LABEL,
    "MS": MACROSYNERGY_LABEL,
    "QC": QUANTOCRACY_LABEL,
}

# How many recent listing dates to take, per paper source.
RECENT_DAYS = 2

USER_AGENT = "qfin-digest/0.4 (personal research digest)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

SOURCES = ("arxiv", "ssrn", "quantpedia", "man", "alphaarchitect", "macrosynergy",
           "quantocracy")
PAPER_SOURCES = ("arxiv", "ssrn")


def report_name(paper_id: str, lang: str) -> str:
    """Deep report filename for a paper in a given language."""
    return f"{paper_id}.{lang}.html"


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
