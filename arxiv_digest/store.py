"""state/seen.json 입출력. ID 를 키로 하는 단일 사전이 전부다.

`summary` 키가 있으면 이미 요약된 논문 → 다음 실행에서 건너뛴다.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import SEEN_PATH, ensure_dirs


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load(path: Path = SEEN_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        backup = path.with_suffix(".json.bak")
        print(f"! {path.name} 를 읽지 못했습니다 ({exc}). 백업에서 복구를 시도합니다.")
        if backup.exists():
            with backup.open(encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            return {}
    return _migrate(data) if isinstance(data, dict) else {}


def _migrate(data: dict[str, dict]) -> dict[str, dict]:
    """SSRN 도입 전(v0.1)에 저장된 항목에 src/ext_id 를 채워 넣는다."""
    for pid, entry in data.items():
        if not isinstance(entry, dict):
            continue
        entry.setdefault("src", "ssrn" if pid.startswith("ssrn-") else "arxiv")
        entry.setdefault("ext_id", pid.split("-", 1)[1] if pid.startswith("ssrn-") else pid)
    return data


def save(data: dict, path: Path = SEEN_PATH) -> None:
    """임시 파일 → os.replace 로 원자적 교체. 직전 버전은 .bak 로 남긴다."""
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def upsert(seen: dict[str, dict], paper_id: str, fields: dict) -> dict:
    """기존 요약을 덮어쓰지 않으면서 메타데이터만 갱신한다."""
    entry = seen.setdefault(paper_id, {"id": paper_id, "first_seen": now_iso()})
    for key, value in fields.items():
        if key == "summary":
            continue
        if value in (None, "", [], {}) and entry.get(key):
            continue
        entry[key] = value
    return entry


def needs_summary(entry: dict) -> bool:
    summary = entry.get("summary")
    return not (isinstance(summary, dict) and summary.get("one_liner"))
