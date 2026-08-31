"""로컬 리포트 서버 — 다이제스트의 '보고서 생성' 버튼을 원클릭으로 만든다.

정적 HTML 은 스스로 Claude 를 부를 수 없어서, 기존에는 요청 ID 를 클립보드로 복사해
터미널에 붙여넣어야 했다. 이 서버는 `report/` 를 그대로 서빙하면서 작은 API 를 얹는다.

    GET  /api/ping             살아 있는지 (페이지가 이걸로 라이브 모드를 감지한다)
    POST /api/report {id}      상세 리포트 생성을 큐에 넣는다
    GET  /api/status?id=...    생성 상태 조회

페이지는 열릴 때 /api/ping 을 찔러 보고, 응답이 없으면(= GitHub Pages 나 파일 열기)
예전처럼 명령어 복사 방식으로 조용히 되돌아간다.
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
from .config import PAPER_DIR, REPORT_DIR


class JobManager:
    """상세 리포트 생성 작업을 한 줄로 세워 순차 처리한다.

    claude 호출과 Chrome 이 동시에 여러 개 뜨면 서로 방해하므로 워커는 하나만 둔다.
    SSRN 브라우저는 첫 요청에서 띄워 두고 서버가 살아 있는 동안 재사용한다.
    """

    def __init__(self, timeout: int = 900, show_browser: bool = False, chrome=None):
        self.timeout = timeout
        self.show_browser = show_browser
        self.chrome = chrome
        self.jobs: dict[str, dict] = {}
        self.on_done = None
        self.lock = threading.Lock()
        self.q: queue.Queue[str] = queue.Queue()
        self._browser = None
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, paper_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(paper_id)
            if job and job["state"] in ("queued", "running"):
                return job
            self.jobs[paper_id] = {"state": "queued", "note": "대기 중", "url": "", "error": ""}
        self.q.put(paper_id)
        return self.jobs[paper_id]

    def status(self, paper_id: str) -> dict:
        with self.lock:
            if (PAPER_DIR / f"{paper_id}.html").exists() and \
                    self.jobs.get(paper_id, {}).get("state") != "running":
                return {"state": "done", "url": f"paper/{paper_id}.html", "note": "", "error": ""}
            return dict(self.jobs.get(paper_id, {"state": "idle", "note": "", "url": "", "error": ""}))

    def _set(self, paper_id: str, **fields) -> None:
        with self.lock:
            self.jobs.setdefault(paper_id, {}).update(fields)

    def _ensure_browser(self):
        if self._browser is None:
            from . import ssrn

            self._browser = ssrn.SsrnBrowser(offscreen=not self.show_browser, chrome=self.chrome)
            self._browser.__enter__()
        return self._browser

    def _run(self) -> None:
        from . import paper as paper_mod

        while True:
            paper_id = self.q.get()
            seen = store.load()
            entry = seen.get(paper_id)
            if not entry:
                self._set(paper_id, state="error", error="seen.json 에 없는 ID 입니다.")
                continue
            try:
                is_ssrn = entry.get("src") == "ssrn"
                self._set(paper_id, state="running",
                          note="PDF 받는 중" if is_ssrn else "전문 받는 중")
                browser = self._ensure_browser() if is_ssrn else None
                self._set(paper_id, state="running", note="요약 중")
                out = paper_mod.build_paper_report(entry, timeout=self.timeout,
                                                   ssrn_browser=browser)
                entry["report_path"] = out.name
                store.save(seen)
                self._set(paper_id, state="done", note="", url=f"paper/{out.name}")
                print(f"  [서버] 생성 완료 {paper_id} → {out.name}")
                if self.on_done:
                    try:
                        self.on_done()
                    except Exception:
                        traceback.print_exc()
            except Exception as exc:  # noqa: BLE001
                self._set(paper_id, state="error", note="", error=str(exc)[:300])
                print(f"  [서버] 생성 실패 {paper_id}: {exc}")
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
            paper_id = (parse_qs(route.query).get("id") or [""])[0]
            return self._json(self.manager.status(paper_id))
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
        if not paper_id:
            return self._json({"error": "id 가 필요합니다"}, 400)
        return self._json(self.manager.submit(paper_id))

    def end_headers(self) -> None:
        # 리포트를 다시 만들었을 때 브라우저가 옛 파일을 붙들지 않게 한다.
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args) -> None:  # 접근 로그는 조용히
        if "/api/" not in (args[0] if args else ""):
            return


def serve(port: int = 8765, timeout: int = 900, show_browser: bool = False,
          chrome=None, on_done=None) -> ThreadingHTTPServer:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manager = JobManager(timeout=timeout, show_browser=show_browser, chrome=chrome)
    manager.on_done = on_done
    handler = partial(Handler, directory=str(REPORT_DIR))
    Handler.manager = manager
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.manager = manager  # type: ignore[attr-defined]
    return httpd
