"""Local report server — makes the digest's report buttons one-click.

A static page cannot call Claude, which is why the first design queued ids in
localStorage and made you paste a command into a terminal. This serves
``report/`` as-is and bolts a tiny API onto it::

    GET  /api/ping                     is anything listening
    POST /api/report {id, lang}        queue a deep report
    GET  /api/status?id=...&lang=...   poll it

The page probes ``api/ping`` on load; with no answer (opened as a file, or on
GitHub Pages) it silently falls back to the copy-a-command flow.
"""

from __future__ import annotations

import json
import queue
import threading
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import store
from .config import LANGS, PAPER_DIR, REPORT_DIR, report_name


class JobManager:
    """Serializes deep-report jobs.

    One worker only: parallel claude calls and Chrome windows fight each other.
    The SSRN browser is started on first need and reused for the server's life,
    which saves the ~7s Chrome start plus Cloudflare pass on every job.
    """

    def __init__(self, timeout: int = 900, show_browser: bool = False, chrome=None):
        self.timeout = timeout
        self.show_browser = show_browser
        self.chrome = chrome
        self.jobs: dict[str, dict] = {}
        self.on_done = None
        self.lock = threading.Lock()
        self.q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._browser = None
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    @staticmethod
    def _key(paper_id: str, lang: str) -> str:
        return f"{paper_id}|{lang}"

    def submit(self, paper_id: str, lang: str) -> dict:
        key = self._key(paper_id, lang)
        with self.lock:
            job = self.jobs.get(key)
            if job and job["state"] in ("queued", "running"):
                return job
            self.jobs[key] = {"state": "queued", "note": "queued", "url": "", "error": ""}
        self.q.put((paper_id, lang))
        return self.jobs[key]

    def status(self, paper_id: str, lang: str) -> dict:
        key = self._key(paper_id, lang)
        with self.lock:
            state = self.jobs.get(key, {}).get("state")
            if state != "running" and (PAPER_DIR / report_name(paper_id, lang)).exists():
                return {"state": "done", "url": f"paper/{report_name(paper_id, lang)}",
                        "note": "", "error": ""}
            return dict(self.jobs.get(key, {"state": "idle", "note": "", "url": "", "error": ""}))

    def _set(self, key: str, **fields) -> None:
        with self.lock:
            self.jobs.setdefault(key, {}).update(fields)

    def _ensure_browser(self):
        if self._browser is None:
            from . import ssrn

            self._browser = ssrn.SsrnBrowser(offscreen=not self.show_browser, chrome=self.chrome)
            self._browser.__enter__()
        return self._browser

    def _run(self) -> None:
        from . import paper as paper_mod

        while True:
            paper_id, lang = self.q.get()
            key = self._key(paper_id, lang)
            seen = store.load()
            entry = seen.get(paper_id)
            if not entry:
                self._set(key, state="error", error=f"{paper_id} is not in seen.json")
                self.q.task_done()
                continue
            try:
                is_ssrn = entry.get("src") == "ssrn"
                self._set(key, state="running", note="fetching PDF" if is_ssrn else "fetching text")
                browser = self._ensure_browser() if is_ssrn else None
                self._set(key, state="running", note="writing report")
                out = paper_mod.build_paper_report(entry, timeout=self.timeout,
                                                   ssrn_browser=browser, lang=lang)
                entry.setdefault("report_paths", {})[lang] = out.name
                store.save(seen)
                self._set(key, state="done", note="", url=f"paper/{out.name}")
                print(f"  [server] built {paper_id} ({lang}) -> {out.name}")
                if self.on_done:
                    try:
                        self.on_done()
                    except Exception:
                        traceback.print_exc()
            except Exception as exc:  # noqa: BLE001
                self._set(key, state="error", note="", error=str(exc)[:300])
                print(f"  [server] failed {paper_id} ({lang}): {exc}")
            finally:
                self.q.task_done()

    def close(self) -> None:
        if self._browser:
            try:
                self._browser.__exit__(None, None, None)
            except Exception:
                pass
            self._browser = None


class Handler(SimpleHTTPRequestHandler):
    manager: JobManager = None  # type: ignore[assignment]

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        if route.path == "/api/ping":
            return self._json({"ok": True})
        if route.path == "/api/status":
            params = parse_qs(route.query)
            paper_id = (params.get("id") or [""])[0]
            lang = (params.get("lang") or ["ko"])[0]
            return self._json(self.manager.status(paper_id, lang))
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/report":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        paper_id = str(payload.get("id") or "").strip()
        lang = str(payload.get("lang") or "ko").strip()
        if not paper_id:
            return self._json({"error": "id is required"}, 400)
        if lang not in LANGS:
            return self._json({"error": f"lang must be one of {LANGS}"}, 400)
        return self._json(self.manager.submit(paper_id, lang))

    def end_headers(self) -> None:
        # Rebuilt reports must not be served from cache.
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args) -> None:  # keep the access log quiet
        return


def serve(port: int = 8765, timeout: int = 900, show_browser: bool = False,
          chrome=None, on_done=None) -> ThreadingHTTPServer:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manager = JobManager(timeout=timeout, show_browser=show_browser, chrome=chrome)
    manager.on_done = on_done
    Handler.manager = manager
    httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                partial(Handler, directory=str(REPORT_DIR)))
    httpd.manager = manager  # type: ignore[attr-defined]
    return httpd
