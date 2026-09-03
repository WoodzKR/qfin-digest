"""Practitioner blogs.

Four sites, three shapes:

Plain RSS — Quantpedia, Alpha Architect
    ``/feed/`` gives title, link, ``pubDate`` and a description that already
    reads as an abstract. Alpha Architect's *blog page* is Cloudflare-protected
    while its feed is not, which is why the feed is the entry point everywhere.

Behind Cloudflare — Macrosynergy
    Both the blog page and the feed answer 403 to plain requests. Clearing the
    challenge once in a real Chrome (the same CDP trick SSRN needs) leaves a
    ``cf_clearance`` cookie, after which the ordinary feed returns 200.

Link aggregator — Quantocracy
    Its homepage is 50 ``<article class='qo-entry'>`` blocks, each one curated
    link: title with the originating blog in brackets, an excerpt, a timestamp
    and an outbound URL pointing at somebody else's post.

    Because it aggregates, it overlaps the sites collected directly above. Those
    entries are dropped — see ``AGGREGATED_DOMAINS``. The direct source is kept
    rather than the aggregator's copy: Quantocracy truncates its excerpt with
    "(...)", while the origin's own feed carries the full one.

All of these publish irregularly, so "the two most recent dates" is meaningless
here. Each site contributes its newest ``limit`` posts.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

from .config import (ALPHAARCH_FEED_URL, ALPHAARCH_LABEL, BLOG_LIMIT, BROWSER_UA,
                     MACROSYNERGY_CDP_PORT, MACROSYNERGY_FEED_URL, MACROSYNERGY_LABEL,
                     QUANTOCRACY_LABEL, QUANTOCRACY_URL,
                     QUANTPEDIA_FEED_URL, QUANTPEDIA_LABEL)

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_BLOCK_RE = re.compile(r"</(p|div|section|h[1-6]|li|tr|table|figure|blockquote)\s*>", re.I)
_QO_ENTRY_RE = re.compile(r"<article class='qo-entry'>(.*?)</article>", re.S)
_QO_TITLE_RE = re.compile(r"<a class='qo-title' href='([^']+)'[^>]*>(.*?)</a>", re.S)
_QO_DESC_RE = re.compile(r"<summary class='qo-description'>(.*?)</summary>", re.S)
_QO_DATE_RE = re.compile(r'<span class="qo-500-ignore">,\s*(\d{1,2} \w{3} \d{4})')

MAX_CHARS = 90_000

# Sites dropped from collection on purpose. Quantocracy links to them, so the
# aggregator would quietly re-admit what we just excluded.
EXCLUDED_DOMAINS = {"man.com"}

# Quantocracy links to these, and we collect them at the source instead.
AGGREGATED_DOMAINS = {
    "quantpedia.com": "quantpedia",
    "alphaarchitect.com": "alphaarchitect",
    "macrosynergy.com": "macrosynergy",
}


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", text or "")).split())


def _session(session: requests.Session | None = None) -> requests.Session:
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", BROWSER_UA)
    sess.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    return sess


def _slug(url: str) -> str:
    return (urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] or urlsplit(url).netloc)[:80]


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def norm_url(url: str) -> str:
    """Comparable form of a URL: no scheme, no www, no trailing slash, no query.

    The aggregator and the origin blog often differ only by a trailing slash.
    """
    parts = urlsplit(url or "")
    return f"{_host(url)}{parts.path.rstrip('/')}".lower()


# ── Generic RSS ──────────────────────────────────────────────────────────

def _cdata(item: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S)
    return m.group(1).strip() if m else ""


def parse_feed(xml: str, prefix: str, src: str, badge: str, label: str,
               limit: int) -> list[dict]:
    """RSS -> entries. Works for any WordPress-style feed."""
    out: list[dict] = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        link = _cdata(item, "link")
        title = _clean(_cdata(item, "title"))
        if not link or not title:
            continue
        try:
            day = parsedate_to_datetime(_cdata(item, "pubDate")).date().isoformat()
        except (TypeError, ValueError):
            day = ""
        author = _clean(_cdata(item, "dc:creator")) or label
        tags = [_clean(c) for c in re.findall(
            r"<category>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</category>", item, re.S)]
        tags = [t for t in tags if t.lower() != "uncategorized"][:4]
        slug = _slug(link)
        out.append({
            "id": f"{prefix}-{slug}",
            "ext_id": slug,
            "src": src,
            "title": title,
            "authors": [author],
            "abstract": _clean(_cdata(item, "description")),
            "listed_date": day,
            "src_cats": [badge],
            "categories": tags or [label],
            "abs_url": link,
            "pdf_url": "",
        })
    return out


def list_quantpedia(limit: int = BLOG_LIMIT, session: requests.Session | None = None,
                    **_kw) -> list[dict]:
    sess = _session(session)
    resp = sess.get(QUANTPEDIA_FEED_URL, timeout=60)
    resp.raise_for_status()
    return parse_feed(resp.text, "qp", "quantpedia", "QP", QUANTPEDIA_LABEL, limit)


def list_alphaarchitect(limit: int = BLOG_LIMIT, session: requests.Session | None = None,
                        **_kw) -> list[dict]:
    sess = _session(session)
    resp = sess.get(ALPHAARCH_FEED_URL, timeout=60)
    resp.raise_for_status()
    return parse_feed(resp.text, "aa", "alphaarchitect", "AA", ALPHAARCH_LABEL, limit)


# ── Macrosynergy (Cloudflare) ────────────────────────────────────────────

def _macrosynergy_cookies(chrome: str | None = None, offscreen: bool = True) -> tuple[dict, str]:
    """Clear the challenge once in a real Chrome and keep the cookies."""
    from .ssrn import SsrnBrowser

    with SsrnBrowser(port=MACROSYNERGY_CDP_PORT, offscreen=offscreen, chrome=chrome) as browser:
        page = browser._page
        page.goto(MACROSYNERGY_FEED_URL.replace("/feed/", "/research/blog/"),
                  wait_until="domcontentloaded", timeout=120_000)
        browser._wait_content("article, .post, h1", timeout=90)
        jar = {c["name"]: c["value"]
               for c in browser._browser.contexts[0].cookies("https://macrosynergy.com")}
        return jar, browser.user_agent()


def list_macrosynergy(limit: int = BLOG_LIMIT, session: requests.Session | None = None,
                      chrome: str | None = None, offscreen: bool = True, **_kw) -> list[dict]:
    resp = requests.get(MACROSYNERGY_FEED_URL, headers={"User-Agent": BROWSER_UA}, timeout=60)
    if resp.status_code != 200 or "<item>" not in resp.text:
        jar, ua = _macrosynergy_cookies(chrome=chrome, offscreen=offscreen)
        # A fresh request: a session that already holds the challenge's own
        # __cf_bm cookie will not be let through with the cleared one.
        resp = requests.get(MACROSYNERGY_FEED_URL, cookies=jar,
                            headers={"User-Agent": ua, "Accept": "application/rss+xml,*/*"},
                            timeout=60)
    resp.raise_for_status()
    return parse_feed(resp.text, "ms", "macrosynergy", "MS", MACROSYNERGY_LABEL, limit)


# ── Quantocracy (aggregator) ─────────────────────────────────────────────

def list_quantocracy(limit: int = BLOG_LIMIT, session: requests.Session | None = None,
                     skip_domains: set[str] | None = None, **_kw) -> list[dict]:
    resp = requests.get(QUANTOCRACY_URL, headers={"User-Agent": BROWSER_UA}, timeout=60)
    resp.raise_for_status()
    skip = skip_domains or set()

    out: list[dict] = []
    for block in _QO_ENTRY_RE.findall(resp.text):
        title_match = _QO_TITLE_RE.search(block)
        if not title_match:
            continue
        url = html.unescape(title_match.group(1))
        host = _host(url)
        if host in skip or host in EXCLUDED_DOMAINS:
            continue          # collected at the source, or excluded on purpose
        raw_title = _clean(title_match.group(2))
        # Titles read "Some Headline [Originating Blog]".
        origin = ""
        bracket = re.search(r"\[([^\]]+)\]\s*$", raw_title)
        if bracket:
            origin = bracket.group(1).strip()
            raw_title = raw_title[:bracket.start()].strip()

        desc = _QO_DESC_RE.search(block)
        abstract = _clean(desc.group(1)).removesuffix("(...)").strip() if desc else ""
        if not abstract:
            continue

        date_match = _QO_DATE_RE.search(block)
        day = ""
        if date_match:
            try:
                day = datetime.strptime(date_match.group(1), "%d %b %Y").date().isoformat()
            except ValueError:
                day = ""

        slug = f"{_host(url).split('.')[0]}-{_slug(url)}"[:80]
        out.append({
            "id": f"qc-{slug}",
            "ext_id": slug,
            "src": "quantocracy",
            "title": raw_title,
            "authors": [origin or QUANTOCRACY_LABEL],
            "abstract": abstract,
            "listed_date": day,
            "src_cats": ["QC"],
            "categories": [origin] if origin else [QUANTOCRACY_LABEL],
            "abs_url": url,
            "pdf_url": "",
        })
        if len(out) >= limit:
            break
    return out


# ── Shared entry point ───────────────────────────────────────────────────

LISTERS = {
    "quantpedia": (QUANTPEDIA_LABEL, list_quantpedia),
    "alphaarchitect": (ALPHAARCH_LABEL, list_alphaarchitect),
    "macrosynergy": (MACROSYNERGY_LABEL, list_macrosynergy),
    "quantocracy": (QUANTOCRACY_LABEL, list_quantocracy),
}


def collect_recent(sources: list[str] | None = None, limit: int = BLOG_LIMIT,
                   verbose: bool = True, chrome: str | None = None,
                   offscreen: bool = True) -> tuple[dict[str, dict], list[str]]:
    """Newest posts from each blog. Returns (posts, dates).

    Quantocracy runs last so it can skip anything already collected directly.
    """
    names = sources or list(LISTERS)
    ordered = [n for n in names if n != "quantocracy"] + \
              (["quantocracy"] if "quantocracy" in names else [])
    sess = _session()
    merged: dict[str, dict] = {}
    days: set[str] = set()
    covered = {domain for domain, src in AGGREGATED_DOMAINS.items() if src in names}

    for name in ordered:
        label, lister = LISTERS[name]
        try:
            posts = lister(limit, sess, skip_domains=covered, chrome=chrome, offscreen=offscreen)
        except Exception as exc:  # noqa: BLE001 - one blog failing must not stop the rest
            print(f"  [{name}] FAILED — {str(exc)[:140]}")
            continue
        # Never keep the same article twice, whatever route it arrived by.
        known_urls = {norm_url(p["abs_url"]) for p in merged.values()}
        posts = [p for p in posts if norm_url(p["abs_url"]) not in known_urls]

        seen_days = sorted({p["listed_date"] for p in posts if p["listed_date"]}, reverse=True)
        if verbose:
            span = f"{seen_days[-1]} .. {seen_days[0]}" if seen_days else "no dates"
            print(f"  [{name}] {label} — {span} : {len(posts)} posts")
        days.update(seen_days)
        for post in posts:
            merged.setdefault(post["id"], post)
    return merged, sorted(days, reverse=True)


def fetch_fulltext(entry: dict, session: requests.Session | None = None) -> tuple[str, str]:
    """(body text, provenance). Blog posts are plain pages, so this always tries."""
    url = entry.get("abs_url", "")
    if not url:
        return "", "no article url (abstract only)"
    sess = _session(session)
    try:
        resp = sess.get(url, timeout=90)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return "", f"fetch failed — {str(exc)[:80]} (abstract only)"

    page = _SCRIPT_RE.sub(" ", resp.text)
    # Drop the chrome around the article: everything before the first <h1>.
    start = page.find("<h1")
    if start > 0:
        page = page[start:]
    page = _BLOCK_RE.sub("\n", page)
    text = html.unescape(_TAG_RE.sub(" ", page))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) < 1200:
        return "", "article body too short (abstract only)"
    label = LISTERS.get(entry.get("src", ""), ("article", None))[0]
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], f"{label} article{' (truncated)' if truncated else ''}"
