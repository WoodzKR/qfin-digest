"""Summarize abstracts by shelling out to the local Claude Code CLI (``claude -p``).

One call produces both languages at once — cheaper and more consistent than
scoring the same paper twice, since ``relevance`` must not drift between them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from .config import LANGS
from .store import TEXT_FIELDS

# ``relevance`` measures one thing only: can this be coded up as a systematic
# strategy? Academic merit is explicitly not what is being scored.
RELEVANCE_RUBRIC = """relevance — systematic-trading implementability (integer 1-5)

Score how far the paper can be turned into rules a machine can trade, and
nothing else. Academic quality is irrelevant here. Pick a base score:

5 - Entry and exit rules are explicit and everything needed is public, standard
    data (prices, volume, quotes, option chains, filings). Universe and
    rebalancing cadence are specified. Backtestable as written.
4 - Gives a trading signal or a strategy method reproducible from standard data.
    Some parameters or execution rules are left to the implementer.
3 - Offers usable features, risk models or portfolio-construction techniques,
    but turning them into a strategy needs substantial further design.
2 - Interesting idea, high barrier to implement: hard-to-source data (satellite
    imagery, proprietary order flow, surveys, hand-labelled sets), assets that
    are hard to access, or ultra-low-latency infrastructure.
1 - Theory, policy, law, institutional description or survey. Essentially
    nothing to automate.

Bonus of +1 (cap at 5, floor stays 1) if any of these hold:
- It refutes a widely held belief or a popular strategy, so it tells you what
  NOT to trade.
- It improves backtesting or validation methodology itself (leakage control,
  multiple-testing correction, realistic transaction costs).
- The idea is original enough to be worth reading even if never implemented.

Do not ignore the penalties. If the data cannot be obtained, cap the score at 2
no matter how strong the reported results are."""

KO_STYLE = """한국어 문체 규칙 — 번역체와 AI 문체를 쓰지 마세요. 한국어로 처음부터 쓴다는 생각으로.

금지 표현 (하나라도 쓰면 실패)
- 번역투 조사: "~에 대한", "~를 통하여", "~에 있어서", "~하는 것을 통해", "~와 관련하여"
- 이중 피동: "~되어진다", "~지게 된다". "~에 의해" 피동도 행위자를 주어로 바꾸세요.
  ("모델에 의해 예측된다" → "모델이 예측한다")
- have/take 직역: "~을 가지고 있다" → "~이 있다", "~이 강하다"
- 만능 동사: "보여준다", "제공한다", "시사한다", "가져온다".
  구체 동사로. ("성과 개선을 보여준다" → "샤프비율이 0.3 올랐다")
- 과장 어휘: "혁신적", "획기적", "압도적", "전례 없는", "시사하는 바가 크다"
- 죽은 은유: "잠식", "청사진", "적신호", "신호탄", "움켜쥐다", "뿌리내리다"
- 상승 공식: "단순한 X를 넘어 Y", "X에서 Y로"
- 분열문: "핵심은 ~이다", "중요한 것은 ~이다" → "~가 핵심이다"가 아니라 바로 단언
- 연결어미(-고, -며, -지만, -면서, -아서) **직후에 쉼표를 찍지 마세요.** 가장 강한 AI 신호입니다.

리듬
- 한 문장 60자 안팎. 다만 전부 같은 길이로 만들지 마세요. 짧은 문장을 섞으세요.
- 같은 종결어미를 세 번 넘게 잇지 마세요.
- 명사를 셋 이상 붙이지 말고 조사를 넣어 푸세요.
- 명사 앞에 관형절을 길게 달지 마세요. 문장을 나누세요.
- "-적/-성/-화"를 겹쳐 쓰지 마세요. ("전략적 함의" → "전략상 의미")

지켜야 할 것
- 전문 용어는 처음 나올 때만 한국어(영문) 병기. 예: 평균-분산(mean-variance).
- 문장 끝은 '~다'로 통일.
- 원문이 "~할 수 있다"로 유보한 주장을 "~한다"로 단정하지 마세요. 확신의 세기를 그대로."""

EN_STYLE = """English style rules — write for a practitioner skimming 40 papers.
- Plain, direct sentences under 20 words. No throat-clearing.
- Active voice. Name the actor.
- No filler ("it is important to note", "this paper aims to").
- Concrete nouns and numbers over abstractions."""

PROMPT = """You are a quant developing systematic trading strategies.
Summarize the paper abstract below in BOTH Korean and English.

[Title] {title}
[Categories] {categories}
[Authors] {authors}
[Abstract]
{abstract}

Reply with one JSON object and nothing else — no prose, no code fences.

{{
  "relevance": 1,
  "keywords": ["3-6 English keywords"],
  "ko": {{
    "one_liner": "이 논문이 한 일을 한 문장(40자 내외)으로",
    "bullets": ["문제의식", "방법론", "핵심 결과"],
    "method": "사용한 모델/기법을 한 문장으로",
    "data": "사용한 데이터셋과 검증 구간을 한 문장으로. 없으면 '이론 연구'",
    "takeaway": "시스템 트레이딩에 쓴다면 무엇을 어떻게 쓸지 한 문장",
    "relevance_why": "그 점수를 준 이유 한 문장. 데이터 확보 난이도를 반드시 언급"
  }},
  "en": {{
    "one_liner": "One sentence on what the paper does",
    "bullets": ["the gap it targets", "the method", "the headline result"],
    "method": "The model or technique, in one sentence",
    "data": "Dataset and evaluation window in one sentence, or 'theory only'",
    "takeaway": "What you would actually use it for, in one sentence",
    "relevance_why": "One sentence on the score. Must mention data availability"
  }}
}}

Content rules:
- 3-4 bullets, each roughly 60 characters.
- The two languages must describe the same content — same facts, same numbers.
  They are not translations of each other; write each one natively.
- Never invent numbers or findings that are not in the abstract.
- "relevance" and "keywords" are shared, so state them once at the top level.

{rubric}

{ko_style}

{en_style}
"""


class SummarizerError(RuntimeError):
    pass


def find_cli() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise SummarizerError(
            "claude CLI not found. Install it with `npm i -g @anthropic-ai/claude-code`.")
    return exe


def _run_cli(exe: str, prompt: str, timeout: int) -> str:
    # On Windows `claude` is a .CMD shim, so it has to go through cmd /c.
    cmd = (["cmd", "/c", exe] if os.name == "nt" else [exe]) + ["-p", "--output-format", "json"]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise SummarizerError(f"claude exited {proc.returncode}: {(proc.stderr or '')[:400]}")
    return proc.stdout or ""


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out, tolerating fences and stray prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start: i + 1])
                except json.JSONDecodeError:
                    start = None
    raise SummarizerError(f"could not parse JSON: {text[:300]}")


def _normalize_block(raw: dict, lang: str) -> dict:
    block = {
        "one_liner": str(raw.get("one_liner", "")).strip(),
        "bullets": [str(b).strip() for b in raw.get("bullets", []) if str(b).strip()][:4],
        "method": str(raw.get("method", "")).strip(),
        "data": str(raw.get("data", "")).strip(),
        "takeaway": str(raw.get("takeaway", "")).strip(),
        "relevance_why": str(raw.get("relevance_why", "")).strip(),
    }
    if not block["one_liner"]:
        raise SummarizerError(f"{lang}.one_liner is empty")
    return {k: block[k] for k in TEXT_FIELDS}


def _normalize(raw: dict) -> dict:
    out: dict = {
        "keywords": [str(k).strip() for k in raw.get("keywords", []) if str(k).strip()][:6],
    }
    try:
        out["relevance"] = max(1, min(5, int(raw.get("relevance", 3))))
    except (TypeError, ValueError):
        out["relevance"] = 3
    for lang in LANGS:
        block = raw.get(lang)
        if not isinstance(block, dict):
            raise SummarizerError(f"missing '{lang}' block")
        out[lang] = _normalize_block(block, lang)
    return out


def summarize_one(entry: dict, exe: str, timeout: int = 300, retries: int = 2) -> dict:
    prompt = PROMPT.format(
        title=entry.get("title", ""),
        categories=", ".join(entry.get("categories", [])),
        authors=", ".join(entry.get("authors", [])[:8]),
        abstract=entry.get("abstract", ""),
        rubric=RELEVANCE_RUBRIC,
        ko_style=KO_STYLE,
        en_style=EN_STYLE,
    )
    last: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            envelope = _extract_json(_run_cli(exe, prompt, timeout))
            # `--output-format json` wraps the answer as {"result": "...", ...}.
            payload = envelope.get("result") if isinstance(envelope.get("result"), str) else None
            return _normalize(_extract_json(payload) if payload else envelope)
        except (SummarizerError, subprocess.TimeoutExpired) as exc:
            last = exc
            if attempt <= retries:
                print(f"    retry {attempt}/{retries} ({entry.get('id')}): {str(exc)[:120]}")
    raise SummarizerError(str(last))


def summarize_many(entries: list[dict], workers: int = 3,
                   timeout: int = 300) -> tuple[int, int]:
    """Update entries in place. Returns (succeeded, failed)."""
    if not entries:
        return 0, 0
    exe = find_cli()
    from .store import now_iso

    ok = fail = 0

    def work(entry: dict) -> tuple[dict, dict | None, str]:
        try:
            return entry, summarize_one(entry, exe, timeout), ""
        except Exception as exc:  # noqa: BLE001 - one failure must not stop the batch
            return entry, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, (entry, summary, err) in enumerate(pool.map(work, entries), 1):
            title = (entry.get("title") or entry.get("id", ""))[:58]
            if summary:
                entry["summary"] = summary
                entry["summarized_at"] = now_iso()
                ok += 1
                print(f"  [{i}/{len(entries)}] ok   {entry['id']} {title}")
            else:
                fail += 1
                print(f"  [{i}/{len(entries)}] FAIL {entry['id']} {title} — {err[:150]}",
                      file=sys.stderr)
    return ok, fail
