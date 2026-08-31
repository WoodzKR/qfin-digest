"""퀀트 논문 다이제스트 CLI (arXiv q-fin + SSRN eJournal).

    python run.py all                    # 크롤 → 요약 → 리포트 (기본)
    python run.py fetch                  # 크롤 + 초록 수집만
    python run.py summarize              # 미요약 논문 요약
    python run.py report                 # HTML 리포트 생성
    python run.py paper 2608.24449 ssrn-7375498   # 논문별 상세 리포트
    python run.py status                 # 현재 상태 확인

    --source arxiv | ssrn | all(기본)
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections import Counter

import requests

from arxiv_digest import api, listing, render, store
from arxiv_digest.config import (CATEGORIES, RECENT_DAYS, SSRN_JOURNALS, USER_AGENT, ensure_dirs)


def _session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    return sess


def _sources(args) -> list[str]:
    return ["arxiv", "ssrn"] if args.source == "all" else [args.source]


# ── fetch ────────────────────────────────────────────────────────────────

def _fetch_arxiv(args, seen: dict) -> list[str]:
    print(f"[arXiv] 목록 크롤 (최근 {args.days}개 날짜 / 카테고리당)")
    papers, days = listing.collect_recent(recent_days=args.days, session=_session())
    if not papers:
        print("  대상 논문이 없습니다.")
        return []
    day_strs = [d.isoformat() for d in days]
    print(f"  → 중복 제거 후 {len(papers)}건")

    need_meta = [p for p in papers if args.force or not seen.get(p, {}).get("abstract")]
    print(f"  메타데이터: 기보유 {len(papers) - len(need_meta)}건, 신규 조회 {len(need_meta)}건")
    meta = api.fetch_metadata(need_meta, session=_session()) if need_meta else {}

    for pid, listed in papers.items():
        fields = {
            "src": "arxiv", "ext_id": pid,
            "listed_date": listed.listed_date.isoformat(),
            "src_cats": listed.src_cats, "cross_from": listed.cross_from,
        }
        info = meta.get(pid)
        if info:
            fields.update(title=info["title"], authors=info["authors"], abstract=info["abstract"],
                          primary=info["primary"], categories=info["categories"],
                          published=info["published"], updated=info["updated"],
                          comment=info["comment"])
        elif pid not in seen:
            fields["title"] = listed.title_hint
        store.upsert(seen, pid, fields)
    return day_strs


def _fetch_ssrn(args, seen: dict) -> list[str]:
    from arxiv_digest import ssrn

    print(f"[SSRN] 목록 조회 (최근 {args.days}개 승인일 / 저널당)")
    papers, days = ssrn.collect_recent(recent_days=args.days)
    if not papers:
        print("  대상 논문이 없습니다.")
        return []
    print(f"  → 중복 제거 후 {len(papers)}건")

    for pid, paper in papers.items():
        store.upsert(seen, pid, paper)

    need_abs = [seen[p] for p in papers if args.force or not seen[p].get("abstract")]
    print(f"  초록: 기보유 {len(papers) - len(need_abs)}건, 신규 수집 {len(need_abs)}건")
    if need_abs:
        print("  Chrome 을 띄워 Cloudflare 를 통과합니다 (창은 화면 밖에 있습니다)")
        with ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome) as browser:
            ok, fail = ssrn.fetch_abstracts(need_abs, browser=browser)
        print(f"  초록 수집: 성공 {ok}건, 실패 {fail}건")
    return days


def cmd_fetch(args) -> list[str]:
    ensure_dirs()
    seen = store.load()
    days: list[str] = []
    try:
        if "arxiv" in _sources(args):
            days += _fetch_arxiv(args, seen)
        if "ssrn" in _sources(args):
            days += _fetch_ssrn(args, seen)
    finally:
        store.save(seen)

    days = sorted(set(days), reverse=True)
    targets = [e for e in seen.values()
               if e.get("listed_date") in set(days) and e.get("src", "arxiv") in _sources(args)]
    pending = [e for e in targets if store.needs_summary(e) and e.get("abstract")]
    print(f"저장 완료 — 요약 대기 {len(pending)}건 / 이미 요약됨 {len(targets) - len(pending)}건")
    return days


# ── summarize / report / paper ───────────────────────────────────────────

def cmd_summarize(args, day_filter: list[str] | None = None) -> None:
    from arxiv_digest import summarize

    seen = store.load()
    srcs = set(_sources(args))
    targets = [e for e in seen.values()
               if e.get("abstract") and e.get("src", "arxiv") in srcs
               and (args.force or store.needs_summary(e))
               and (not day_filter or e.get("listed_date") in set(day_filter))]
    if not targets:
        print("요약할 논문이 없습니다. (모두 처리됨)")
        return
    print(f"요약 {len(targets)}건 — 로컬 claude CLI, 동시 {args.workers}개")
    ok, fail = summarize.summarize_many(targets, workers=args.workers, timeout=args.timeout)
    store.save(seen)
    print(f"요약 완료: 성공 {ok}건, 실패 {fail}건")


def _build_report(args, day_filter: list[str] | None = None):
    seen = store.load()
    days = day_filter if (day_filter and not args.all) else None
    out = render.build(seen, days=days, sources=_sources(args) if args.source != "all" else None)
    render.build_index(seen)
    return out


def cmd_report(args, day_filter: list[str] | None = None) -> None:
    out = _build_report(args, day_filter)
    print(f"리포트 생성: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


def cmd_deep(args, day_filter: list[str] | None = None) -> None:
    """★ 상위 N편의 상세 리포트를 미리 만들어 둔다."""
    from arxiv_digest import paper, ssrn
    from arxiv_digest.config import PAPER_DIR

    if args.deep <= 0:
        return
    seen = store.load()
    srcs = set(_sources(args))
    pool = [e for e in seen.values()
            if (e.get("summary") or {}).get("one_liner") and e.get("src", "arxiv") in srcs
            and (not day_filter or e.get("listed_date") in set(day_filter))
            and not (PAPER_DIR / f"{e['id']}.html").exists()]
    pool.sort(key=lambda e: (e["summary"].get("relevance", 3), e.get("listed_date", "")),
              reverse=True)
    targets = pool[:args.deep]
    if not targets:
        print("상세 리포트를 새로 만들 논문이 없습니다.")
        return

    print(f"★ 상위 {len(targets)}편 상세 리포트 생성")
    browser = None
    try:
        if any(e.get("src") == "ssrn" for e in targets):
            browser = ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome)
            browser.__enter__()
        for i, entry in enumerate(targets, 1):
            star = entry["summary"].get("relevance", 3)
            print(f"  [{i}/{len(targets)}] ★{star} {entry['id']} {entry.get('title', '')[:50]}")
            try:
                out = paper.build_paper_report(entry, session=_session(), timeout=args.timeout,
                                               ssrn_browser=browser)
                entry["report_path"] = out.name
            except Exception as exc:  # noqa: BLE001
                print(f"      실패: {str(exc)[:140]}", file=sys.stderr)
    finally:
        if browser:
            browser.__exit__(None, None, None)
        store.save(seen)


def cmd_serve(args) -> None:
    """report/ 를 서빙하면서 '보고서 생성' 버튼을 원클릭으로 만든다."""
    from arxiv_digest import server

    out = _build_report(args, None)
    rel = out.name

    def rebuild():
        _build_report(args, None)

    httpd = server.serve(port=args.port, timeout=args.timeout,
                         show_browser=args.show_browser, chrome=args.chrome, on_done=rebuild)
    url = f"http://127.0.0.1:{args.port}/{rel}"
    print(f"로컬 서버 실행 중 — {url}")
    print("  카드의 '📄 보고서 생성' 을 누르면 바로 생성됩니다. 종료는 Ctrl+C.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        httpd.manager.close()
        httpd.server_close()


def cmd_paper(args) -> None:
    from arxiv_digest import paper, ssrn

    seen = store.load()
    ids = [i.strip().strip(",") for i in args.ids if i.strip().strip(",")]
    missing = [i for i in ids if i not in seen]
    for i in missing:
        print(f"! {i}: seen.json 에 없습니다. 먼저 `python run.py fetch` 를 실행하세요.")
    ids = [i for i in ids if i in seen]
    if not ids:
        return

    sess = _session()
    browser = None
    try:
        if any(seen[i].get("src") == "ssrn" for i in ids):
            print("Chrome 을 띄워 SSRN PDF 를 받습니다 (창은 화면 밖에 있습니다)")
            browser = ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome)
            browser.__enter__()
        for pid in ids:
            entry = seen[pid]
            print(f"상세 리포트 생성 중: {pid} — {entry.get('title', '')[:60]}")
            try:
                out = paper.build_paper_report(entry, session=sess, timeout=args.timeout,
                                               ssrn_browser=browser)
            except Exception as exc:  # noqa: BLE001
                print(f"! {pid} 실패: {exc}", file=sys.stderr)
                continue
            entry["report_path"] = out.name
            print(f"  → {out}")
            if not args.no_open:
                webbrowser.open(out.resolve().as_uri())
    finally:
        if browser:
            browser.__exit__(None, None, None)
        store.save(seen)


def cmd_status(_args) -> None:
    seen = store.load()
    done = [e for e in seen.values() if not store.needs_summary(e)]
    by_day = Counter(e.get("listed_date", "?") for e in seen.values())
    by_cat = Counter(c for e in seen.values() for c in (e.get("src_cats") or []))
    by_src = Counter(e.get("src", "arxiv") for e in seen.values())
    print(f"총 {len(seen)}건 · 요약 완료 {len(done)}건 · 미요약 {len(seen) - len(done)}건")
    print("출처별:", ", ".join(f"{s} {n}" for s, n in by_src.items()))
    print("날짜별:", ", ".join(f"{d} {n}" for d, n in sorted(by_day.items(), reverse=True)[:8]))
    print("arXiv:", ", ".join(f"{c} {by_cat.get(c, 0)}" for c in CATEGORIES))
    print("SSRN :", ", ".join(f"{s} {by_cat.get(s, 0)}" for s, _ in SSRN_JOURNALS.values()))


def main() -> None:
    ap = argparse.ArgumentParser(description="퀀트 논문 다이제스트 (arXiv + SSRN)")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "fetch", "summarize", "report", "deep", "serve",
                             "paper", "status"])
    ap.add_argument("ids", nargs="*", help="paper 명령에 넘길 논문 ID")
    ap.add_argument("--source", default="all", choices=["all", "arxiv", "ssrn"])
    ap.add_argument("--days", type=int, default=RECENT_DAYS, help="출처별 최근 N개 날짜 (기본 2)")
    ap.add_argument("--workers", type=int, default=3, help="요약 동시 실행 수 (기본 3)")
    ap.add_argument("--timeout", type=int, default=900, help="claude 호출 타임아웃 초")
    ap.add_argument("--force", action="store_true", help="이미 처리한 논문도 다시 처리")
    ap.add_argument("--all", action="store_true", help="report 시 날짜 필터 없이 전체 출력")
    ap.add_argument("--no-open", action="store_true", help="생성 후 브라우저를 열지 않음")
    ap.add_argument("--show-browser", action="store_true",
                    help="SSRN 용 Chrome 창을 화면 안에 표시 (디버깅용)")
    ap.add_argument("--chrome", default=None, help="Chrome/Edge 실행 파일 경로 지정")
    ap.add_argument("--deep", type=int, default=0, metavar="N",
                    help="★ 상위 N편의 상세 리포트를 미리 생성 (기본 0)")
    ap.add_argument("--port", type=int, default=8765, help="serve 포트 (기본 8765)")
    args = ap.parse_args()

    if args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "summarize":
        cmd_summarize(args)
    elif args.cmd == "report":
        cmd_report(args)
    elif args.cmd == "deep":
        cmd_deep(args)
    elif args.cmd == "serve":
        cmd_serve(args)
    elif args.cmd == "paper":
        if not args.ids:
            ap.error("paper 명령에는 논문 ID 가 필요합니다.")
        cmd_paper(args)
    elif args.cmd == "status":
        cmd_status(args)
    else:
        days = cmd_fetch(args)
        cmd_summarize(args, day_filter=days)
        cmd_deep(args, day_filter=days)
        cmd_report(args, day_filter=days)


if __name__ == "__main__":
    main()
