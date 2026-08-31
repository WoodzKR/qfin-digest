"""arXiv Atom API 로 제목·저자·초록·카테고리를 가져온다.

목록 HTML 의 접힌 초록을 긁는 대신 공식 API 를 쓴다 — 마크업 변경에 강하고
한 번에 100건까지 받을 수 있다.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

from .config import API_BATCH, API_SLEEP, API_URL, USER_AGENT

NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def _parse_entry(entry: ET.Element) -> dict | None:
    raw_id = _norm(entry.findtext("a:id", "", NS))
    if not raw_id:
        return None
    base = raw_id.rsplit("/", 1)[-1]
    version = ""
    if "v" in base:
        base, _, version = base.partition("v")
    if entry.find("a:title", NS) is None:
        return None

    primary_el = entry.find("arxiv:primary_category", NS)
    return {
        "id": base,
        "version": version,
        "title": _norm(entry.findtext("a:title", "", NS)),
        "abstract": _norm(entry.findtext("a:summary", "", NS)),
        "authors": [_norm(a.findtext("a:name", "", NS)) for a in entry.findall("a:author", NS)],
        "primary": primary_el.get("term") if primary_el is not None else "",
        "categories": [c.get("term") for c in entry.findall("a:category", NS) if c.get("term")],
        "published": _norm(entry.findtext("a:published", "", NS)),
        "updated": _norm(entry.findtext("a:updated", "", NS)),
        "comment": _norm(entry.findtext("arxiv:comment", "", NS)),
    }


def fetch_metadata(
    ids: list[str],
    session: requests.Session | None = None,
    verbose: bool = True,
) -> dict[str, dict]:
    """arXiv ID 리스트 → {id: 메타데이터}."""
    if not ids:
        return {}
    sess = session or requests.Session()
    out: dict[str, dict] = {}
    batches = [ids[i: i + API_BATCH] for i in range(0, len(ids), API_BATCH)]

    for n, batch in enumerate(batches, 1):
        if n > 1:
            time.sleep(API_SLEEP)
        resp = sess.get(
            API_URL,
            params={"id_list": ",".join(batch), "max_results": len(batch)},
            headers={"User-Agent": USER_AGENT},
            timeout=90,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        got = 0
        for entry in root.findall("a:entry", NS):
            meta = _parse_entry(entry)
            if meta:
                out[meta["id"]] = meta
                got += 1
        if verbose:
            print(f"  API 배치 {n}/{len(batches)}: {got}/{len(batch)}건")

    missing = [i for i in ids if i not in out]
    if missing and verbose:
        print(f"  ! 메타데이터 누락 {len(missing)}건: {', '.join(missing[:5])}")
    return out
