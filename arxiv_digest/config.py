"""공통 설정 및 경로."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
REPORT_DIR = ROOT / "report"
PAPER_DIR = REPORT_DIR / "paper"
CHROME_PROFILE = STATE_DIR / "chrome_profile"

SEEN_PATH = STATE_DIR / "seen.json"

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
# journal_id → (짧은 배지 이름, 정식 이름)
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
SSRN_MAX_SCAN = 300          # 최근 날짜를 찾느라 훑을 최대 논문 수 (저널당)
SSRN_CDP_PORT = 9333         # 사용자의 일반 Chrome 과 겹치지 않게
SSRN_NAV_SLEEP = 1.2         # 초록 페이지 사이 대기(초)

# 카테고리별로 가져올 "최근 N개 날짜"
RECENT_DAYS = 2

USER_AGENT = "arxiv-qfin-digest/0.2 (personal research digest)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

SOURCES = ("arxiv", "ssrn")


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
