"""Read/write ``state/seen.json`` — a single dict keyed by paper id.

An entry carries a summary once it has been written; that is what makes the
next run skip it. Summaries are bilingual::

    "summary": {
      "relevance": 4,
      "keywords": ["kelly criterion", ...],
      "ko": {"one_liner": ..., "bullets": [...], ...},
      "en": {"one_liner": ..., "bullets": [...], ...}
    }
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import (LANGS, LEGACY_VERSION, REPORT_VERSION, SEEN_PATH, SUMMARY_VERSION,
                     ensure_dirs)

# Per-language fields; ``relevance`` and ``keywords`` are shared across languages.
TEXT_FIELDS = ("one_liner", "bullets", "method", "data", "takeaway", "relevance_why")


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
        print(f"! Could not read {path.name} ({exc}); trying the backup.")
        if backup.exists():
            with backup.open(encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            return {}
    return _migrate(data) if isinstance(data, dict) else {}


def _migrate(data: dict[str, dict]) -> dict[str, dict]:
    """Bring entries written by older versions up to the current shape.

    v0.1 had no ``src``/``ext_id``; v0.3 stored a single Korean summary with the
    text fields at the top level of ``summary``.
    """
    for pid, entry in data.items():
        if not isinstance(entry, dict):
            continue
        entry.setdefault("src", "ssrn" if pid.startswith("ssrn-") else "arxiv")
        entry.setdefault("ext_id", pid.split("-", 1)[1] if pid.startswith("ssrn-") else pid)

        summary = entry.get("summary")
        if isinstance(summary, dict) and "one_liner" in summary:
            korean = {k: summary.pop(k) for k in TEXT_FIELDS if k in summary}
            summary["ko"] = korean

        # Output that predates version stamping is adopted as current rather than
        # flagged. It was all produced by the prompts as they stand, and marking
        # it unknown would nag for a hundred-call rerun that changes nothing.
        # Only these existing entries are ever touched: everything written from
        # now on is stamped at write time.
        if is_summarized(entry):
            entry.setdefault("summary_version", LEGACY_VERSION)
        if entry.get("report_paths") and "report_versions" not in entry:
            entry["report_versions"] = {lang: LEGACY_VERSION for lang in entry["report_paths"]}
    return data


def save(data: dict, path: Path = SEEN_PATH) -> None:
    """Write via a temp file and ``os.replace``; keep one ``.bak`` generation."""
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def upsert(seen: dict[str, dict], paper_id: str, fields: dict) -> dict:
    """Refresh metadata without ever clobbering an existing summary."""
    entry = seen.setdefault(paper_id, {"id": paper_id, "first_seen": now_iso()})
    for key, value in fields.items():
        if key == "summary":
            continue
        if value in (None, "", [], {}) and entry.get(key):
            continue
        entry[key] = value
    return entry


def text(entry: dict, lang: str) -> dict:
    """Per-language part of a summary, falling back to the other language."""
    summary = entry.get("summary") or {}
    block = summary.get(lang)
    if isinstance(block, dict) and block.get("one_liner"):
        return block
    for other in LANGS:
        block = summary.get(other)
        if isinstance(block, dict) and block.get("one_liner"):
            return block
    return {}


def has_lang(entry: dict, lang: str) -> bool:
    block = (entry.get("summary") or {}).get(lang)
    return isinstance(block, dict) and bool(block.get("one_liner"))


def needs_summary(entry: dict, langs: tuple[str, ...] = LANGS) -> bool:
    return not all(has_lang(entry, lang) for lang in langs)


def summary_version(entry: dict) -> str | None:
    return entry.get("summary_version")


def summary_stale(entry: dict) -> bool:
    """Summarized by an older summary prompt. Independent of the report prompt."""
    return not needs_summary(entry) and summary_version(entry) != SUMMARY_VERSION


def report_version(entry: dict, lang: str) -> str | None:
    return (entry.get("report_versions") or {}).get(lang)


def report_stale(entry: dict, lang: str) -> bool:
    """A deep report made by an older report prompt. Independent of summaries."""
    return report_version(entry, lang) != REPORT_VERSION


def is_summarized(entry: dict) -> bool:
    """True once at least one language is present (enough to render a card)."""
    return any(has_lang(entry, lang) for lang in LANGS)
