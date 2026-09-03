"""Quant paper digest CLI (arXiv q-fin + SSRN eJournals).

    python run.py all                    # crawl -> summarize -> report (default)
    python run.py fetch                  # listings and abstracts only
    python run.py summarize              # summarize whatever is missing one
    python run.py deep --deep 5          # deep reports for the top 5 by star
    python run.py report                 # rebuild the HTML digest
    python run.py serve                  # one-click mode on http://127.0.0.1:8765
    python run.py paper 2608.24449 ssrn-7375498 --lang en
    python run.py publish                # commit generated files and push
    python run.py status                 # what is in the store

    --source arxiv | ssrn | all (default)
    --lang   ko | en | both
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from collections import Counter

import requests

# The output is Korean and uses em-dashes; a default Windows console is cp949
# and would raise UnicodeEncodeError mid-report. update.bat sets this too, but
# `python run.py` typed directly into cmd must not crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from arxiv_digest import api, listing, render, store
from arxiv_digest.config import (BLOG_LABELS, BLOG_LIMIT, BLOG_SOURCES, CATEGORIES, LANGS,
                                 RECENT_DAYS, REPORT_VERSION, SOURCES, SSRN_JOURNALS,
                                 SUMMARY_VERSION, USER_AGENT, ensure_dirs, report_name)


def _session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    return sess


def _sources(args) -> list[str]:
    """`--source` takes `all`, one name, or a comma-separated list."""
    if args.source == "all":
        return list(SOURCES)
    picked = [s.strip() for s in args.source.split(",") if s.strip()]
    unknown = [s for s in picked if s not in SOURCES]
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)}. "
                         f"Choose from: all, {', '.join(SOURCES)}")
    return picked


def _langs(args) -> list[str]:
    return list(LANGS) if args.lang == "both" else [args.lang]


# ── fetch ────────────────────────────────────────────────────────────────

def _fetch_arxiv(args, seen: dict) -> list[str]:
    print(f"[arXiv] listings (most recent {args.days} dates per category)")
    papers, days = listing.collect_recent(recent_days=args.days, session=_session())
    if not papers:
        print("  nothing listed.")
        return []
    day_strs = [d.isoformat() for d in days]
    print(f"  -> {len(papers)} after de-duplication")

    need_meta = [p for p in papers if args.force or not seen.get(p, {}).get("abstract")]
    print(f"  metadata: {len(papers) - len(need_meta)} cached, {len(need_meta)} to fetch")
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

    print(f"[SSRN] listings (most recent {args.days} approval dates per journal)")
    papers, days = ssrn.collect_recent(recent_days=args.days)
    if not papers:
        print("  nothing listed.")
        return []
    print(f"  -> {len(papers)} after de-duplication")

    for pid, paper in papers.items():
        store.upsert(seen, pid, paper)

    need_abs = [seen[p] for p in papers if args.force or not seen[p].get("abstract")]
    print(f"  abstracts: {len(papers) - len(need_abs)} cached, {len(need_abs)} to fetch")
    if need_abs:
        print("  starting Chrome to clear Cloudflare (window is parked off-screen)")
        with ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome) as browser:
            ok, fail = ssrn.fetch_abstracts(need_abs, browser=browser)
        print(f"  abstracts: {ok} ok, {fail} failed")
    return days


def _fetch_blogs(args, seen: dict, names: list[str]) -> list[str]:
    from arxiv_digest import blogs

    print(f"[blogs] newest {args.blog_limit} posts per site")
    posts, days = blogs.collect_recent(sources=names, limit=args.blog_limit,
                                       chrome=args.chrome, offscreen=not args.show_browser)
    from arxiv_digest.blogs import AGGREGATED_DOMAINS, norm_url

    # Quantocracy aggregates sites we also read directly, and a run can cover a
    # different set of sources than the previous one did, so the same article can
    # already be in the store under an aggregator id.
    covered = {d for d, s in AGGREGATED_DOMAINS.items() if s in names}
    stale = [pid for pid, e in seen.items()
             if e.get("src") == "quantocracy"
             and norm_url(e.get("abs_url", "")).split("/")[0] in covered]
    for pid in stale:
        del seen[pid]

    known = {norm_url(e["abs_url"]): pid for pid, e in seen.items() if e.get("abs_url")}
    dropped = 0
    for pid, post in posts.items():
        owner = known.get(norm_url(post.get("abs_url", "")))
        if owner and owner != pid:
            dropped += 1
            continue
        store.upsert(seen, pid, post)

    notes = []
    if dropped:
        notes.append(f"{dropped} duplicate(s) skipped")
    if stale:
        notes.append(f"{len(stale)} aggregator copy(ies) removed")
    print(f"  -> {len(posts) - dropped} posts" + (f" ({', '.join(notes)})" if notes else ""))
    return days


def cmd_fetch(args) -> list[str]:
    ensure_dirs()
    seen = store.load()
    srcs = _sources(args)
    days: list[str] = []
    # One source failing (SSRN's browser most often) must not lose the others.
    steps = []
    if "arxiv" in srcs:
        steps.append(("arXiv", lambda: _fetch_arxiv(args, seen)))
    if "ssrn" in srcs:
        steps.append(("SSRN", lambda: _fetch_ssrn(args, seen)))
    blog_names = [s for s in BLOG_SOURCES if s in srcs]
    if blog_names:
        steps.append(("blogs", lambda: _fetch_blogs(args, seen, blog_names)))
    try:
        for name, step in steps:
            try:
                days += step()
            except Exception as exc:  # noqa: BLE001
                print(f"! {name} fetch failed — {str(exc)[:200]}", file=sys.stderr)
    finally:
        store.save(seen)

    days = sorted(set(days), reverse=True)
    targets = [e for e in seen.values()
               if e.get("listed_date") in set(days) and e.get("src", "arxiv") in _sources(args)]
    pending = [e for e in targets if store.needs_summary(e) and e.get("abstract")]
    print(f"saved — {len(pending)} to summarize, {len(targets) - len(pending)} already done")
    return days


# ── summarize / deep / report / serve ────────────────────────────────────

def cmd_summarize(args, day_filter: list[str] | None = None) -> None:
    from arxiv_digest import summarize

    seen = store.load()
    srcs = set(_sources(args))
    targets = [e for e in seen.values()
               if e.get("abstract") and e.get("src", "arxiv") in srcs
               and (args.force or store.needs_summary(e)
                    or (args.stale and store.summary_stale(e)))
               and (not day_filter or e.get("listed_date") in set(day_filter))]
    if not targets:
        print("nothing to summarize.")
        return
    print(f"summarizing {len(targets)} (ko+en) via claude CLI, {args.workers} at a time")
    ok, fail = summarize.summarize_many(targets, workers=args.workers, timeout=args.timeout)
    store.save(seen)
    print(f"summaries: {ok} ok, {fail} failed")


def _build_report(args, day_filter: list[str] | None = None, all_sources: bool = False):
    """Render the digest. `all_sources` ignores --source, which is a fetch filter."""
    seen = store.load()
    days = day_filter if (day_filter and not args.all) else None
    sources = None if (all_sources or args.source == "all") else _sources(args)
    out = render.build(seen, days=days, sources=sources)
    render.build_index(seen)
    return out


def cmd_report(args, day_filter: list[str] | None = None) -> None:
    out = _build_report(args, day_filter)
    print(f"report: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


def cmd_deep(args, day_filter: list[str] | None = None) -> None:
    """Pre-build deep reports for the highest-scoring papers."""
    from arxiv_digest import paper, ssrn
    from arxiv_digest.config import PAPER_DIR

    if args.deep <= 0:
        return
    langs = _langs(args)
    seen = store.load()
    srcs = set(_sources(args))
    pool = [e for e in seen.values()
            if store.is_summarized(e) and e.get("src", "arxiv") in srcs
            and (not day_filter or e.get("listed_date") in set(day_filter))
            and any(not (PAPER_DIR / report_name(e["id"], lang)).exists()
                    or (args.stale and store.report_stale(e, lang)) for lang in langs)]
    pool.sort(key=lambda e: ((e.get("summary") or {}).get("relevance", 3),
                             e.get("listed_date", "")), reverse=True)
    targets = pool[:args.deep]
    if not targets:
        print("no deep reports left to build.")
        return

    print(f"deep reports for the top {len(targets)} ({', '.join(langs)})")
    browser = None
    try:
        if any(e.get("src") == "ssrn" for e in targets):
            browser = ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome)
            browser.__enter__()
        for i, entry in enumerate(targets, 1):
            star = (entry.get("summary") or {}).get("relevance", 3)
            print(f"  [{i}/{len(targets)}] *{star} {entry['id']} {entry.get('title', '')[:48]}")
            for lang in langs:
                if (PAPER_DIR / report_name(entry["id"], lang)).exists() and not (
                        args.stale and store.report_stale(entry, lang)):
                    continue
                try:
                    out = paper.build_paper_report(entry, session=_session(), timeout=args.timeout,
                                                   ssrn_browser=browser, lang=lang,
                                                   review=args.review)
                    entry.setdefault("report_paths", {})[lang] = out.name
                    entry.setdefault("report_versions", {})[lang] = REPORT_VERSION
                    print(f"      {lang}: {out.name}")
                except Exception as exc:  # noqa: BLE001
                    print(f"      {lang}: FAILED {str(exc)[:130]}", file=sys.stderr)
    finally:
        if browser:
            browser.__exit__(None, None, None)
        store.save(seen)


def cmd_serve(args) -> None:
    from arxiv_digest import server

    out = _build_report(args, None)

    httpd = server.serve(port=args.port, timeout=args.timeout, show_browser=args.show_browser,
                         chrome=args.chrome, on_done=lambda: _build_report(args, None))
    url = f"http://127.0.0.1:{args.port}/report/{out.name}"
    print(f"serving {url}")
    print("  the report buttons build on click. Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.manager.close()
        httpd.server_close()


def cmd_paper(args) -> None:
    from arxiv_digest import paper, ssrn

    seen = store.load()
    langs = _langs(args)
    ids = [i.strip().strip(",") for i in args.ids if i.strip().strip(",")]
    for missing in [i for i in ids if i not in seen]:
        print(f"! {missing} is not in seen.json — run `python run.py fetch` first.")
    ids = [i for i in ids if i in seen]
    if not ids:
        return

    sess = _session()
    browser = None
    try:
        if any(seen[i].get("src") == "ssrn" for i in ids):
            print("starting Chrome for SSRN PDFs (window is parked off-screen)")
            browser = ssrn.SsrnBrowser(offscreen=not args.show_browser, chrome=args.chrome)
            browser.__enter__()
        for pid in ids:
            entry = seen[pid]
            print(f"deep report: {pid} — {entry.get('title', '')[:56]}")
            for lang in langs:
                try:
                    out = paper.build_paper_report(entry, session=sess, timeout=args.timeout,
                                                   ssrn_browser=browser, lang=lang,
                                                   review=args.review)
                except Exception as exc:  # noqa: BLE001
                    print(f"! {pid} ({lang}) failed: {exc}", file=sys.stderr)
                    continue
                entry.setdefault("report_paths", {})[lang] = out.name
                entry.setdefault("report_versions", {})[lang] = REPORT_VERSION
                print(f"  {lang}: {out}")
                if not args.no_open:
                    webbrowser.open(out.resolve().as_uri())
    finally:
        if browser:
            browser.__exit__(None, None, None)
        store.save(seen)


# ── publish / status ─────────────────────────────────────────────────────

def _git_exe() -> str | None:
    import shutil
    from pathlib import Path

    found = shutil.which("git")
    if found:
        return found
    # winget's Git installer needs admin, so PortableGit under the user profile
    # is a common fallback on locked-down machines.
    portable = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\PortableGit\cmd\git.exe"))
    return str(portable) if portable.exists() else None


def cmd_publish(args) -> None:
    """Commit the generated files and push, refreshing GitHub Pages."""
    import subprocess
    from datetime import date

    from arxiv_digest.config import PAPER_DIR, ROOT

    git = _git_exe()
    if not git:
        print("! git not found. Check PATH.", file=sys.stderr)
        return

    def run(*cmd, check=True):
        return subprocess.run([git, *cmd], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=check)

    if run("rev-parse", "--git-dir", check=False).returncode != 0:
        print("! not a git repository; run `git init` first.", file=sys.stderr)
        return

    run("add", "-A")
    if not run("diff", "--cached", "--name-only").stdout.strip():
        print("nothing to publish.")
        return

    seen = store.load()
    done = sum(1 for e in seen.values() if store.is_summarized(e))
    papers = len(list(PAPER_DIR.glob("*.html")))
    message = args.message or f"digest {date.today():%Y-%m-%d} — {done} summaries, {papers} reports"
    run("commit", "-m", message)
    print(f"committed: {message}")

    if run("remote", "get-url", "origin", check=False).returncode != 0:
        print("no origin remote; skipping push.")
        return
    push = run("push", check=False)
    if push.returncode != 0:
        print(f"! push failed:\n{push.stderr.strip()[:500]}", file=sys.stderr)
        return
    print("pushed.")
    url = run("remote", "get-url", "origin").stdout.strip()
    if "github.com" in url:
        owner, _, repo = url.split("github.com")[-1].lstrip(":/").removesuffix(".git").partition("/")
        print(f"  https://{owner.lower()}.github.io/{repo}/  (live in a minute or two)")


def cmd_status(_args) -> None:
    seen = store.load()
    done = [e for e in seen.values() if store.is_summarized(e)]
    both = [e for e in seen.values() if not store.needs_summary(e)]
    by_day = Counter(e.get("listed_date", "?") for e in seen.values())
    by_cat = Counter(c for e in seen.values() for c in (e.get("src_cats") or []))
    by_src = Counter(e.get("src", "arxiv") for e in seen.values())
    print(f"{len(seen)} papers · {len(done)} summarized · {len(both)} in both languages")
    print("sources:", ", ".join(f"{s} {n}" for s, n in by_src.items()))
    print("dates:  ", ", ".join(f"{d} {n}" for d, n in sorted(by_day.items(), reverse=True)[:8]))
    print("arXiv:  ", ", ".join(f"{c} {by_cat.get(c, 0)}" for c in CATEGORIES))
    print("SSRN:   ", ", ".join(f"{s} {by_cat.get(s, 0)}" for s, _ in SSRN_JOURNALS.values()))
    print("blogs:  ", ", ".join(f"{s} {by_cat.get(s, 0)}" for s in BLOG_LABELS))

    from arxiv_digest.config import PAPER_DIR

    print()
    print(f"current prompts — summary {SUMMARY_VERSION}, report {REPORT_VERSION}")

    def _tally(values):
        counts = Counter(v or "unrecorded" for v in values)
        return ", ".join(f"{v} {n}" for v, n in sorted(counts.items()))

    summarized = [e for e in seen.values() if store.is_summarized(e)]
    print("  summaries   :", _tally(store.summary_version(e) for e in summarized))

    reports = [(e, lang) for e in seen.values() for lang in LANGS
               if (PAPER_DIR / report_name(e["id"], lang)).exists()]
    if reports:
        print("  deep reports:", _tally(store.report_version(e, lang) for e, lang in reports))

    stale_sum = sum(1 for e in summarized if store.summary_stale(e))
    stale_rep = sum(1 for e, lang in reports if store.report_stale(e, lang))
    if not (stale_sum or stale_rep):
        print("  everything is on the current prompts")
        return
    # The two stamps are independent: a deep-report change never asks you to
    # redo a hundred summaries, and vice versa.
    if stale_sum:
        print(f"  {stale_sum} summaries predate SUMMARY_VERSION:")
        print(f"     python run.py summarize --stale        ({stale_sum} calls)")
    if stale_rep:
        print(f"  {stale_rep} deep reports predate REPORT_VERSION:")
        print(f"     python run.py deep --deep {stale_rep} --stale --lang both")


def main() -> None:
    ap = argparse.ArgumentParser(description="Quant paper digest (arXiv + SSRN)")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "fetch", "summarize", "report", "deep", "serve",
                             "paper", "publish", "status"])
    ap.add_argument("ids", nargs="*", help="paper ids for the `paper` command")
    ap.add_argument("--source", default="all",
                    help=f"all (default), one of {', '.join(SOURCES)}, or a comma-separated list")
    ap.add_argument("--blog-limit", type=int, default=BLOG_LIMIT,
                    help=f"newest N posts per blog (default {BLOG_LIMIT})")
    ap.add_argument("--lang", default="ko", choices=["ko", "en", "both"],
                    help="language for deep reports (default ko)")
    ap.add_argument("--days", type=int, default=RECENT_DAYS,
                    help="how many recent dates per source (default 2)")
    ap.add_argument("--workers", type=int, default=3, help="parallel summaries (default 3)")
    ap.add_argument("--timeout", type=int, default=900, help="claude call timeout in seconds")
    ap.add_argument("--force", action="store_true", help="redo work that is already done")
    ap.add_argument("--stale", action="store_true",
                    help="redo only what an older prompt version produced "
                         "(see `status` for the counts)")
    ap.add_argument("--all", action="store_true", help="report over everything, not just today")
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    ap.add_argument("--show-browser", action="store_true",
                    help="keep the SSRN Chrome window on screen (debugging)")
    ap.add_argument("--chrome", default=None, help="explicit Chrome/Edge executable path")
    ap.add_argument("--deep", type=int, default=0, metavar="N",
                    help="pre-build deep reports for the top N papers")
    ap.add_argument("--port", type=int, default=8765, help="serve port (default 8765)")
    ap.add_argument("--review", action="store_true",
                    help="run a critique pass (academic-paper-reviewer) before writing "
                         "a deep report; adds one call per report")
    ap.add_argument("--push", action="store_true", help="publish after `all`")
    ap.add_argument("-m", "--message", default=None, help="commit message for publish")
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
            ap.error("the `paper` command needs at least one id")
        cmd_paper(args)
    elif args.cmd == "publish":
        cmd_publish(args)
    elif args.cmd == "status":
        cmd_status(args)
    else:
        days = cmd_fetch(args)
        # Only fetching is scoped to this run. Summarizing and rendering heal the
        # whole store: a narrow run must neither leave older entries permanently
        # unsummarized (a blog post can rotate off its landing page and never be
        # fetched again) nor republish a digest containing only what it fetched.
        cmd_summarize(args, day_filter=None)
        cmd_deep(args, day_filter=days)
        out = _build_report(args, day_filter=None, all_sources=True)
        print(f"report: {out}")
        if not args.no_open:
            webbrowser.open(out.resolve().as_uri())
        if args.push:
            cmd_publish(args)


if __name__ == "__main__":
    main()
