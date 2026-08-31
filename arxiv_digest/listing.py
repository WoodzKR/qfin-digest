"""arXiv /list/{cat}/recent 페이지 크롤 및 날짜별 논문 ID 추출.

페이지 구조 (2026-08 기준)::

    <dl id='articles'>
      <h3>Wed, 26 Aug 2026 (showing 2 of 2 entries )</h3>
      <dt> <a href ="/abs/2608.24449" ...> ... </dt>
      <dd> <div class='meta'> ... </div> </dd>
      ...
    </dl>

날짜별로 <dl id='articles'> 블록이 하나씩 반복되며, 논문이 없는 날은
"No updates for this time period." 문단만 들어 있다.
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
# href 앞뒤로 공백이 붙어 있는 경우가 있어 \s* 를 넣는다.
_ABS_RE = re.compile(r"""href\s*=\s*["']/abs/(\d{4}\.\d{4,6})(v\d+)?["']""")
_CROSS_RE = re.compile(r"\(cross-list from ([\w.\-]+)\)")
_TITLE_RE = re.compile(r"""<div class=['"]list-title[^>]*>(.*?)</div>""", re.S)
_AUTHORS_RE = re.compile(r"""<div class=['"]list-authors['"][^>]*>(.*?)</div>""", re.S)
_SUBJ_RE = re.compile(r"""<div class=['"]list-subjects['"][^>]*>(.*?)</div>""", re.S)
_DESCRIPTOR_RE = re.compile(r"""<span class=['"]descriptor['"]>.*?</span>""", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    """HTML 조각에서 descriptor 라벨을 떼고 순수 텍스트만 뽑는다."""
    fragment = _DESCRIPTOR_RE.sub("", fragment)
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


@dataclass
class ListedPaper:
    """목록 페이지에서 얻은 최소 정보."""

    id: str
    listed_date: date
    src_cats: list[str] = field(default_factory=list)
    cross_from: str | None = None
    title_hint: str = ""

    def merge(self, other: "ListedPaper") -> None:
        for c in other.src_cats:
            if c not in self.src_cats:
                self.src_cats.append(c)
        # 더 최신 날짜에 다시 등장하면 그쪽을 기준으로 삼는다.
        if other.listed_date > self.listed_date:
            self.listed_date = other.listed_date
        if not self.title_hint:
            self.title_hint = other.title_hint


def fetch_listing(cat: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(
        LISTING_URL.format(cat=cat),
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text


def parse_listing(page: str, cat: str) -> dict[date, list[ListedPaper]]:
    """날짜 → 그 날짜에 실린 논문 목록. 빈 날짜는 결과에 넣지 않는다."""
    out: dict[date, list[ListedPaper]] = {}
    heads = list(_H3_RE.finditer(page))
    for i, head in enumerate(heads):
        label = _text(head.group(1))
        m = _DATE_RE.search(label)
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%d %b %Y").date()
        except ValueError:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(page)
        segment = page[head.end():end]

        papers: list[ListedPaper] = []
        for dt_html, dd_html in _ENTRY_RE.findall(segment):
            abs_m = _ABS_RE.search(dt_html)
            if not abs_m:
                continue
            cross_m = _CROSS_RE.search(dt_html)
            title_m = _TITLE_RE.search(dd_html)
            papers.append(
                ListedPaper(
                    id=abs_m.group(1),
                    listed_date=day,
                    src_cats=[cat],
                    cross_from=cross_m.group(1) if cross_m else None,
                    title_hint=_text(title_m.group(1)) if title_m else "",
                )
            )
        if papers:
            out[day] = papers
    return out


def collect_recent(
    categories: list[str] | None = None,
    recent_days: int = RECENT_DAYS,
    session: requests.Session | None = None,
    verbose: bool = True,
) -> tuple[dict[str, ListedPaper], list[date]]:
    """각 카테고리에서 논문이 실린 최근 `recent_days`개 날짜를 모아 합집합으로 돌려준다.

    카테고리마다 갱신일이 어긋날 수 있으므로 전역 상위 2일이 아니라
    **카테고리별** 상위 2일을 취한 뒤 합친다.
    """
    cats = categories or list(CATEGORIES)
    sess = session or requests.Session()
    merged: dict[str, ListedPaper] = {}
    all_days: set[date] = set()

    for cat in cats:
        page = fetch_listing(cat, sess)
        by_day = parse_listing(page, cat)
        picked = sorted(by_day, reverse=True)[:recent_days]
        if verbose:
            shown = ", ".join(d.isoformat() for d in picked) or "(없음)"
            total = sum(len(by_day[d]) for d in picked)
            print(f"  [{cat}] 대상 날짜: {shown} — {total}건")
        for day in picked:
            all_days.add(day)
            for paper in by_day[day]:
                if paper.id in merged:
                    merged[paper.id].merge(paper)
                else:
                    merged[paper.id] = paper

    return merged, sorted(all_days, reverse=True)
