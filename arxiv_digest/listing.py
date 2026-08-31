"""Crawl ``arxiv.org/list/{cat}/recent`` and pull out paper ids by date.

Page shape (as of 2026-08)::

    <dl id='articles'>
      <h3>Wed, 26 Aug 2026 (showing 2 of 2 entries )</h3>
      <dt> <a href ="/abs/2608.24449" ...> ... </dt>
      <dd> <div class='meta'> ... </div> </dd>
      ...
    </dl>

One ``<dl id='articles'>`` block repeats *per date* — there is not a single one
for the whole document. Days with nothing new carry only a
"No updates for this time period." paragraph, so they must be skipped when
counting "the two most recent dates".
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import requests

from .config import CATEGORIES, LISTING_URL, RECENT_DAYS, USER_AGENT

_H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
_DATE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})")
_ENTRY_RE = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
# Note the whitespace before '=': the markup really is `href ="/abs/ID"`.
_ABS_RE = re.compile(r"""href\s*=\s*["']/abs/(\d{4}\.\d{4,6})(v\d+)?["']""")
_CROSS_RE = re.compile(r"\(cross-list from ([\w.\-]+)\)")
_TITLE_RE = re.compile(r"""<div class=['"]list-title[^>]*>(.*?)</div>""", re.S)
_DESCRIPTOR_RE = re.compile(r"""<span class=['"]descriptor['"]>.*?</span>""", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    """Strip the descriptor label and all tags, leaving plain text."""
    fragment = _DESCRIPTOR_RE.sub("", fragment)
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


@dataclass
class ListedPaper:
    """What the listing page alone tells us about a paper."""

    id: str
    listed_date: date
    src_cats: list[str] = field(default_factory=list)
    cross_from: str | None = None
    title_hint: str = ""

    def merge(self, other: "ListedPaper") -> None:
        for cat in other.src_cats:
            if cat not in self.src_cats:
                self.src_cats.append(cat)
        # If it shows up again under a newer date, prefer that date.
        if other.listed_date > self.listed_date:
            self.listed_date = other.listed_date
        if not self.title_hint:
            self.title_hint = other.title_hint


def fetch_listing(cat: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(LISTING_URL.format(cat=cat), headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.text


def parse_listing(page: str, cat: str) -> dict[date, list[ListedPaper]]:
    """date -> papers listed that day. Empty days are left out entirely."""
    out: dict[date, list[ListedPaper]] = {}
    heads = list(_H3_RE.finditer(page))
    for i, head in enumerate(heads):
        match = _DATE_RE.search(_text(head.group(1)))
        if not match:
            continue
        try:
            day = datetime.strptime(match.group(1), "%d %b %Y").date()
        except ValueError:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(page)
        segment = page[head.end():end]

        papers: list[ListedPaper] = []
        for dt_html, dd_html in _ENTRY_RE.findall(segment):
            abs_match = _ABS_RE.search(dt_html)
            if not abs_match:
                continue
            cross = _CROSS_RE.search(dt_html)
            title = _TITLE_RE.search(dd_html)
            papers.append(ListedPaper(
                id=abs_match.group(1),
                listed_date=day,
                src_cats=[cat],
                cross_from=cross.group(1) if cross else None,
                title_hint=_text(title.group(1)) if title else "",
            ))
        if papers:
            out[day] = papers
    return out


def collect_recent(categories: list[str] | None = None, recent_days: int = RECENT_DAYS,
                   session: requests.Session | None = None,
                   verbose: bool = True) -> tuple[dict[str, ListedPaper], list[date]]:
    """Union of the most recent non-empty dates, taken **per category**.

    Categories drift apart: q-fin.PM may last have updated two days before
    q-fin.ST does. Taking a global top-2 would drop a whole category.
    """
    cats = categories or list(CATEGORIES)
    sess = session or requests.Session()
    merged: dict[str, ListedPaper] = {}
    all_days: set[date] = set()

    for cat in cats:
        by_day = parse_listing(fetch_listing(cat, sess), cat)
        picked = sorted(by_day, reverse=True)[:recent_days]
        if verbose:
            shown = ", ".join(d.isoformat() for d in picked) or "(none)"
            total = sum(len(by_day[d]) for d in picked)
            print(f"  [{cat}] dates: {shown} — {total} papers")
        for day in picked:
            all_days.add(day)
            for paper in by_day[day]:
                if paper.id in merged:
                    merged[paper.id].merge(paper)
                else:
                    merged[paper.id] = paper

    return merged, sorted(all_days, reverse=True)
