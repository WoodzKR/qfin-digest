"""SSRN eJournal 수집.

두 단계로 나뉜다.

1. **목록** — `api.ssrn.com/content/v1/bindings/{journal_id}/papers` 는 Cloudflare 뒤에
   있지 않아 평범한 HTTP 로 읽힌다. 제목·저자·소속·승인일(approved_date)·abstract_id 를 준다.
   다만 **초록은 주지 않는다.**
2. **초록/전문** — `papers.ssrn.com` 은 Cloudflare JS 챌린지로 막혀 있다. requests 는 물론
   Playwright 가 직접 띄운 Chromium/Chrome 도 통과하지 못한다. 통과하는 방법은
   *우리가 직접 실행한 진짜 Chrome 에 CDP 로 붙는 것* 하나뿐이라, 그렇게 한다.
   챌린지를 한 번 통과하면 `cf_clearance` 쿠키가 전용 프로필에 남아 다음 실행이 빨라진다.
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


# ── 1. 목록 (Cloudflare 없음) ────────────────────────────────────────────

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


def list_journal(jid: str, recent_days: int, session: requests.Session | None = None) -> list[dict]:
    """저널 하나에서 논문이 실린 최근 `recent_days`개 승인일의 논문을 모은다."""
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
                    return out                       # 날짜 내림차순이므로 여기서 끝
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
    """저널별 최근 N개 날짜를 모아 합집합으로 돌려준다. (중복 제거된 dict, 날짜 목록)"""
    jids = journal_ids or list(SSRN_JOURNALS)
    sess = _api_session()
    merged: dict[str, dict] = {}
    days: set[str] = set()

    for jid in jids:
        short, name = SSRN_JOURNALS.get(jid, (jid, jid))
        papers = list_journal(jid, recent_days, sess)
        seen_days = sorted({p["listed_date"] for p in papers if p["listed_date"]}, reverse=True)
        if verbose:
            print(f"  [{short}] {name[:44]} — {', '.join(seen_days) or '없음'} : {len(papers)}건")
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


# ── 2. 초록/전문 (Cloudflare — 진짜 Chrome + CDP) ────────────────────────

class SsrnBrowser:
    """직접 띄운 Chrome 에 CDP 로 붙는다. with 문으로 쓴다.

    Playwright 가 launch() 한 브라우저는 Cloudflare 가 자동화로 판정해 막는다.
    반면 우리가 별도 프로필로 실행한 Chrome 에 connect_over_cdp 로 붙으면 통과한다.
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
            raise SsrnError("Chrome 또는 Edge 를 찾지 못했습니다. --chrome 으로 경로를 지정하세요.")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SsrnError("playwright 가 없습니다. `pip install playwright && playwright install chromium`") from exc

        os.makedirs(self.profile, exist_ok=True)
        args = [self.chrome, f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}", "--no-first-run",
                "--no-default-browser-check", "--disable-features=Translate"]
        if self.offscreen:
            # 화면 밖에 띄워 작업을 방해하지 않는다. 진짜 창이라 챌린지는 그대로 통과한다.
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
            raise SsrnError(f"Chrome 디버깅 포트 {self.port} 에 붙지 못했습니다.")

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

    # -- 내부 --------------------------------------------------------
    def _wait_content(self, selector: str, timeout: int = 90) -> bool:
        """Cloudflare 챌린지가 끝나고 실제 콘텐츠가 나올 때까지 기다린다.

        챌린지 페이지 제목은 브라우저 언어에 따라 번역되므로 제목으로 판정하지 않고
        목표 셀렉터가 나타나는지로만 판정한다.
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

    # -- 공개 --------------------------------------------------------
    def fetch_abstract(self, entry: dict, timeout: int = 90) -> dict:
        """초록 페이지에서 초록·PDF 링크·키워드를 읽어 entry 를 갱신한다."""
        from .config import SSRN_ABS_URL

        url = entry.get("abs_url") or SSRN_ABS_URL.format(id=entry["ext_id"])
        self._page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        if not self._wait_content("div.abstract-text", timeout):
            raise SsrnError("Cloudflare 챌린지를 통과하지 못했습니다 (초록 영역 없음).")

        text = self._page.locator("div.abstract-text").first.inner_text()
        # 첫 줄의 "Abstract" 라벨을 떼어낸다.
        text = re.sub(r"^\s*abstract\s*\n+", "", text, flags=re.I).strip()
        entry["abstract"] = " ".join(text.split())

        links = self._page.locator("a[href*='Delivery.cfm']")
        if links.count():
            href = links.first.get_attribute("href") or ""
            if href:
                entry["pdf_url"] = ("https://papers.ssrn.com/sol3/" + href.lstrip("/")
                                    if not href.startswith("http") else href)
        try:
            kw = self._page.locator("div.keywords-text, p.keywords").first
            if kw.count():
                entry["ssrn_keywords"] = _clean(kw.inner_text())[:400]
        except Exception:
            pass
        time.sleep(SSRN_NAV_SLEEP)
        return entry

    def download_pdf(self, entry: dict) -> bytes:
        """브라우저가 얻어 둔 cf_clearance 쿠키로 PDF 를 내려받는다."""
        url = entry.get("pdf_url") or SSRN_PDF_URL.format(id=entry["ext_id"])
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": self.user_agent(),
            "Accept": "application/pdf,*/*",
            "Referer": entry.get("abs_url", "https://papers.ssrn.com/"),
        })
        resp = sess.get(url, cookies=self.cookies(), timeout=180, allow_redirects=True)
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            raise SsrnError(f"PDF 를 받지 못했습니다 (HTTP {resp.status_code}, "
                            f"{len(resp.content)}바이트).")
        return resp.content


def fetch_abstracts(entries: list[dict], browser: SsrnBrowser | None = None,
                    verbose: bool = True) -> tuple[int, int]:
    """초록이 없는 entry 들을 채운다. (성공, 실패)."""
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
                    print(f"  [{i}/{len(todo)}] 초록 OK  {entry['ext_id']} "
                          f"{entry.get('title', '')[:55]}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"  [{i}/{len(todo)}] 초록 실패 {entry['ext_id']} — {str(exc)[:140]}",
                      file=sys.stderr)
    finally:
        if own:
            ctx.__exit__(None, None, None)
    return ok, fail


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SsrnError("pypdf 가 없습니다. `pip install pypdf`") from exc
    reader = PdfReader(io.BytesIO(data))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(chunks)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_fulltext(entry: dict, browser: SsrnBrowser | None = None) -> tuple[str, str]:
    """(본문 텍스트, 출처 설명). 실패하면 ('', 사유)."""
    own = browser is None
    ctx = SsrnBrowser() if own else browser
    try:
        if own:
            ctx.__enter__()
        if not entry.get("abstract") or not entry.get("pdf_url"):
            ctx.fetch_abstract(entry)
        data = ctx.download_pdf(entry)
    except Exception as exc:  # noqa: BLE001
        return "", f"PDF 확보 실패 — {str(exc)[:90]} (초록만 사용)"
    finally:
        if own:
            ctx.__exit__(None, None, None)

    try:
        text = pdf_to_text(data)
    except Exception as exc:  # noqa: BLE001
        return "", f"PDF 텍스트 추출 실패 — {str(exc)[:90]} (초록만 사용)"
    if len(text) < 2000:
        return "", "PDF 본문이 너무 짧음 (초록만 사용)"
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], f"SSRN PDF 전문{' (앞부분 발췌)' if truncated else ''}"
