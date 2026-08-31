"""SSRN eJournal collection, in two stages.

1. **Listing** — ``api.ssrn.com/content/v1/bindings/{journal_id}/papers`` sits
   outside Cloudflare and answers plain HTTP. It gives title, authors,
   affiliation, ``approved_date`` and ``abstract_id``. It does **not** give the
   abstract, and the per-paper detail endpoints all return 401.
2. **Abstract / full text** — ``papers.ssrn.com`` is behind a Cloudflare JS
   challenge. requests fails, and so does Playwright driving its own bundled
   Chromium *or* a real Chrome it launched itself. The one thing that works is
   attaching over CDP to a Chrome **we started ourselves**, so that is what this
   does. Clearing the challenge once leaves a ``cf_clearance`` cookie in the
   dedicated profile, which makes later runs fast.
"""

from __future__ import annotations

import html
import io
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime

import requests

from .config import (BROWSER_UA, CHROME_PROFILE, SSRN_API_URL, SSRN_CDP_PORT, SSRN_JOURNALS,
                     SSRN_MAX_SCAN, SSRN_NAV_SLEEP, SSRN_PAGE_SIZE, SSRN_PDF_URL)

_TAG_RE = re.compile(r"<[^>]+>")
MAX_CHARS = 90_000

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class SsrnError(RuntimeError):
    pass


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", text or "")).split())


def _parse_date(label: str) -> date | None:
    try:
        return datetime.strptime(label.strip(), "%d %b %Y").date()
    except (ValueError, AttributeError):
        return None


# ── 1. Listing (no Cloudflare) ───────────────────────────────────────────

def _api_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://papers.ssrn.com",
        "Referer": "https://papers.ssrn.com/",
    })
    return sess


def list_journal(jid: str, recent_days: int,
                 session: requests.Session | None = None) -> list[dict]:
    """Papers from the most recent ``recent_days`` approval dates of one journal."""
    sess = session or _api_session()
    short, name = SSRN_JOURNALS.get(jid, (jid, jid))
    picked_days: list[str] = []
    out: list[dict] = []
    index = 0

    while index < SSRN_MAX_SCAN:
        resp = sess.get(SSRN_API_URL.format(jid=jid),
                        params={"index": index, "count": SSRN_PAGE_SIZE, "sort": 0}, timeout=60)
        resp.raise_for_status()
        papers = resp.json().get("papers") or []
        if not papers:
            break
        for paper in papers:
            label = paper.get("approved_date") or ""
            if label not in picked_days:
                if len(picked_days) >= recent_days:
                    return out          # results are date-descending, so we are done
                picked_days.append(label)
            day = _parse_date(label)
            ext_id = str(paper.get("id") or "")
            if not ext_id:
                continue
            authors = [" ".join(x for x in (a.get("first_name"), a.get("last_name")) if x).strip()
                       for a in (paper.get("authors") or [])]
            out.append({
                "id": f"ssrn-{ext_id}",
                "ext_id": ext_id,
                "src": "ssrn",
                "title": _clean(paper.get("title", "")),
                "authors": [a for a in authors if a],
                "affiliations": _clean(paper.get("affiliations", "")),
                "listed_date": day.isoformat() if day else "",
                "src_cats": [short],
                "journals": [name],
                "page_count": paper.get("page_count"),
                "downloads": paper.get("downloads"),
                "abs_url": paper.get("url") or "",
                "pdf_url": SSRN_PDF_URL.format(id=ext_id),
                "categories": [name],
            })
        index += SSRN_PAGE_SIZE
    return out


def collect_recent(journal_ids: list[str] | None = None, recent_days: int = 2,
                   verbose: bool = True) -> tuple[dict[str, dict], list[str]]:
    """Union across journals, de-duplicated. Returns (papers, dates)."""
    jids = journal_ids or list(SSRN_JOURNALS)
    sess = _api_session()
    merged: dict[str, dict] = {}
    days: set[str] = set()

    for jid in jids:
        short, name = SSRN_JOURNALS.get(jid, (jid, jid))
        papers = list_journal(jid, recent_days, sess)
        seen_days = sorted({p["listed_date"] for p in papers if p["listed_date"]}, reverse=True)
        if verbose:
            print(f"  [{short}] {name[:44]} — {', '.join(seen_days) or 'none'} : {len(papers)}")
        days.update(seen_days)
        for paper in papers:
            prev = merged.get(paper["id"])
            if prev:
                for key in ("src_cats", "journals"):
                    for value in paper[key]:
                        if value not in prev[key]:
                            prev[key].append(value)
                prev["categories"] = list(prev["journals"])
            else:
                merged[paper["id"]] = paper
    return merged, sorted(days, reverse=True)


# ── 2. Abstract / full text (Cloudflare — real Chrome over CDP) ──────────

class SsrnBrowser:
    """Launches Chrome ourselves, then attaches to it over CDP. Use as a context manager.

    A browser Playwright ``launch()``es is flagged as automation and never clears
    the challenge; a plain Chrome we started with ``--remote-debugging-port`` does.
    """

    def __init__(self, port: int = SSRN_CDP_PORT, profile=CHROME_PROFILE,
                 offscreen: bool = True, chrome: str | None = None):
        self.port = port
        self.profile = str(profile)
        self.offscreen = offscreen
        self.chrome = chrome or next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
        self._proc = None
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "SsrnBrowser":
        if not self.chrome:
            raise SsrnError("No Chrome or Edge found. Pass --chrome with an explicit path.")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SsrnError("playwright is missing. "
                            "`pip install playwright && playwright install chromium`") from exc

        os.makedirs(self.profile, exist_ok=True)
        args = [self.chrome, f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}", "--no-first-run",
                "--no-default-browser-check", "--disable-features=Translate"]
        if self.offscreen:
            # Parked off-screen so it stays out of the way. Still a real window,
            # so the challenge clears exactly as it would on screen.
            args += ["--window-position=-2400,-2400", "--window-size=1280,900"]
        args.append("about:blank")
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2).read()
                break
            except Exception:
                time.sleep(0.5)
        else:
            self.__exit__(None, None, None)
            raise SsrnError(f"Could not attach to the Chrome debugging port {self.port}.")

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        ctx = self._browser.contexts[0]
        self._page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return self

    def __exit__(self, *_exc) -> None:
        for close in (lambda: self._browser and self._browser.close(),
                      lambda: self._pw and self._pw.stop(),
                      lambda: self._proc and self._proc.terminate()):
            try:
                close()
            except Exception:
                pass

    # -- internals ---------------------------------------------------
    def _wait_content(self, selector: str, timeout: int = 90) -> bool:
        """Wait for real content rather than for the challenge to disappear.

        The interstitial's title is localised by browser language (it reads
        "잠시만 기다리십시오…" on a Korean Chrome), so title matching is unreliable.
        Waiting on the target selector is not.
        """
        for _ in range(timeout):
            try:
                if self._page.locator(selector).count() > 0:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def cookies(self) -> dict[str, str]:
        jar = self._browser.contexts[0].cookies("https://papers.ssrn.com")
        return {c["name"]: c["value"] for c in jar}

    def user_agent(self) -> str:
        try:
            return self._page.evaluate("navigator.userAgent")
        except Exception:
            return BROWSER_UA

    # -- public ------------------------------------------------------
    def fetch_abstract(self, entry: dict, timeout: int = 90) -> dict:
        """Read the abstract, PDF link and keywords off the abstract page."""
        from .config import SSRN_ABS_URL

        url = entry.get("abs_url") or SSRN_ABS_URL.format(id=entry["ext_id"])
        self._page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        if not self._wait_content("div.abstract-text", timeout):
            raise SsrnError("Cloudflare challenge not cleared (no abstract element).")

        text = self._page.locator("div.abstract-text").first.inner_text()
        text = re.sub(r"^\s*abstract\s*\n+", "", text, flags=re.I).strip()
        entry["abstract"] = " ".join(text.split())

        links = self._page.locator("a[href*='Delivery.cfm']")
        if links.count():
            href = links.first.get_attribute("href") or ""
            if href:
                entry["pdf_url"] = (href if href.startswith("http")
                                    else "https://papers.ssrn.com/sol3/" + href.lstrip("/"))
        try:
            kw = self._page.locator("div.keywords-text, p.keywords").first
            if kw.count():
                entry["ssrn_keywords"] = _clean(kw.inner_text())[:400]
        except Exception:
            pass
        time.sleep(SSRN_NAV_SLEEP)
        return entry

    def download_pdf(self, entry: dict) -> bytes:
        """Fetch the PDF using the cf_clearance cookie the browser earned."""
        url = entry.get("pdf_url") or SSRN_PDF_URL.format(id=entry["ext_id"])
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": self.user_agent(),
            "Accept": "application/pdf,*/*",
            "Referer": entry.get("abs_url", "https://papers.ssrn.com/"),
        })
        resp = sess.get(url, cookies=self.cookies(), timeout=180, allow_redirects=True)
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            raise SsrnError(f"PDF download failed (HTTP {resp.status_code}, "
                            f"{len(resp.content)} bytes).")
        return resp.content


def fetch_abstracts(entries: list[dict], browser: SsrnBrowser | None = None,
                    verbose: bool = True) -> tuple[int, int]:
    """Fill in missing abstracts. Returns (succeeded, failed)."""
    todo = [e for e in entries if not e.get("abstract")]
    if not todo:
        return 0, 0
    own = browser is None
    ctx = SsrnBrowser() if own else browser
    ok = fail = 0
    try:
        if own:
            ctx.__enter__()
        for i, entry in enumerate(todo, 1):
            try:
                ctx.fetch_abstract(entry)
                ok += 1
                if verbose:
                    print(f"  [{i}/{len(todo)}] ok   {entry['ext_id']} "
                          f"{entry.get('title', '')[:52]}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"  [{i}/{len(todo)}] FAIL {entry['ext_id']} — {str(exc)[:140]}",
                      file=sys.stderr)
    finally:
        if own:
            ctx.__exit__(None, None, None)
    return ok, fail


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SsrnError("pypdf is missing. `pip install pypdf`") from exc
    chunks = []
    for page in PdfReader(io.BytesIO(data)).pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = re.sub(r"[ \t]+", " ", "\n\n".join(chunks))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_fulltext(entry: dict, browser: SsrnBrowser | None = None) -> tuple[str, str]:
    """(body text, provenance note). Empty body means we fell back to the abstract."""
    own = browser is None
    ctx = SsrnBrowser() if own else browser
    try:
        if own:
            ctx.__enter__()
        if not entry.get("abstract") or not entry.get("pdf_url"):
            ctx.fetch_abstract(entry)
        data = ctx.download_pdf(entry)
    except Exception as exc:  # noqa: BLE001
        return "", f"PDF unavailable — {str(exc)[:90]} (abstract only)"
    finally:
        if own:
            ctx.__exit__(None, None, None)

    try:
        text = pdf_to_text(data)
    except Exception as exc:  # noqa: BLE001
        return "", f"PDF text extraction failed — {str(exc)[:90]} (abstract only)"
    if len(text) < 2000:
        return "", "PDF body too short (abstract only)"
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], f"SSRN PDF full text{' (truncated)' if truncated else ''}"
