"""로컬 Claude Code CLI (`claude -p`) 를 호출해 초록을 한국어로 요약한다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

SCHEMA_KEYS = ("one_liner", "bullets", "method", "data", "takeaway", "keywords",
               "relevance", "relevance_why")

# relevance 는 "연구가 훌륭한가"가 아니라 "시스템 트레이딩으로 옮길 수 있는가"를 잰다.
RELEVANCE_RUBRIC = """relevance — 시스템 트레이딩 구현 가능성 (1~5 정수)

이 점수는 논문의 학술적 수준이 아니라 **계량적 규칙으로 코딩해 자동매매로 돌릴 수 있는가**
하나만 잽니다. 아래 기준에서 먼저 기본 점수를 정하세요.

5 — 진입·청산 규칙이 명시적이고, 공개·표준 데이터(가격·거래량·호가·옵션체인·재무제표 등)만으로
    그대로 백테스트하고 자동매매로 구현할 수 있다. 유니버스와 리밸런싱 주기까지 특정돼 있다.
4 — 매매 신호나 전략 방법론을 제시하고 표준 데이터로 재현할 수 있다.
    파라미터나 집행 규칙 일부는 직접 정해야 한다.
3 — 시스템 트레이딩에 쓸 특징(feature)이나 리스크·포트폴리오 구성 기법을 준다.
    그대로 옮기려면 설계를 상당히 더 해야 한다.
2 — 착상은 흥미롭지만 구현 장벽이 크다. 구하기 어려운 데이터(위성 사진, 독점 주문흐름,
    설문, 수작업 라벨), 접근이 어려운 자산, 초저지연 인프라가 전제된다.
1 — 이론·정책·법률·제도·서베이 등 자동매매로 옮길 여지가 사실상 없다.

가산점 — 다음에 해당하면 위 점수에 +1 (최대 5, 최소 1은 유지):
- 널리 쓰이는 통념이나 기존 전략을 반증해서, 쓰지 말아야 할 것을 알려준다.
- 백테스트·검증 방법론 자체를 개선한다. (누출 차단, 다중검정 보정, 거래비용 반영 등)
- 착상이 독창적이어서 직접 구현하지 않더라도 읽을 값어치가 크다.

감점 요인을 무시하지 마세요. 데이터를 구할 수 없으면 결과가 아무리 좋아도 2 이하입니다."""

PROMPT = """당신은 시스템 트레이딩 전략을 개발하는 퀀트입니다. 아래 논문 초록을 한국어로 요약하세요.

[제목] {title}
[분류] {categories}
[저자] {authors}
[초록]
{abstract}

아래 JSON 스키마로만 응답하세요. 설명·인사말·코드펜스 없이 JSON 객체 하나만 출력합니다.

{{
  "one_liner": "이 논문이 한 일을 한 문장(40자 내외)으로",
  "bullets": ["문제의식", "방법론", "핵심 결과"],
  "method": "사용한 모델/기법을 한 문장으로",
  "data": "사용한 데이터셋과 검증 구간을 한 문장으로. 없으면 '이론 연구'",
  "takeaway": "시스템 트레이딩에 쓴다면 무엇을 어떻게 쓸지 한 문장",
  "keywords": ["영문 키워드 3~6개"],
  "relevance": 1,
  "relevance_why": "그 점수를 준 이유 한 문장. 필요한 데이터의 확보 난이도를 반드시 언급"
}}

{rubric}

내용 규칙:
- bullets 는 3~4개, 각 항목 60자 내외.
- 초록에 없는 내용을 지어내지 마세요.

문체 규칙 — 직역체를 쓰지 마세요. 한국어로 다시 쓴다는 생각으로 작성합니다.
- 한 문장 60자 안팎. 접속사로 길게 이어붙이지 마세요.
- 수동태를 능동태로. ("~에 의해 측정된다" → "~로 측정한다")
- 번역투 금지: "~에 대한", "~를 통하여", "~에 있어서", "~하는 것을 통해".
- 명사를 셋 이상 연달아 붙이지 마세요. 조사를 넣어 풀어 쓰세요.
- 전문 용어는 처음 나올 때만 한국어(영문) 병기. 예: 평균-분산(mean-variance).
- 문장 끝은 '~다'로 통일. bullets 는 명사형이나 '~다' 중 하나로 일관되게.
"""


class SummarizerError(RuntimeError):
    pass


def find_cli() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise SummarizerError(
            "claude CLI 를 찾을 수 없습니다. `npm i -g @anthropic-ai/claude-code` 로 설치하세요."
        )
    return exe


def _run_cli(exe: str, prompt: str, timeout: int) -> str:
    # Windows 에서 claude 는 .cmd 래퍼이므로 cmd /c 를 거쳐야 안전하다.
    if os.name == "nt":
        cmd = ["cmd", "/c", exe, "-p", "--output-format", "json"]
    else:
        cmd = [exe, "-p", "--output-format", "json"]
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise SummarizerError(f"claude 종료코드 {proc.returncode}: {(proc.stderr or '')[:400]}")
    return proc.stdout or ""


def _extract_json(text: str) -> dict:
    """```json 펜스나 앞뒤 잡소리가 섞여 있어도 첫 JSON 객체를 뽑아낸다."""
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
    raise SummarizerError(f"JSON 파싱 실패: {text[:300]}")


def _normalize(raw: dict) -> dict:
    out = {
        "one_liner": str(raw.get("one_liner", "")).strip(),
        "bullets": [str(b).strip() for b in raw.get("bullets", []) if str(b).strip()][:4],
        "method": str(raw.get("method", "")).strip(),
        "data": str(raw.get("data", "")).strip(),
        "takeaway": str(raw.get("takeaway", "")).strip(),
        "keywords": [str(k).strip() for k in raw.get("keywords", []) if str(k).strip()][:6],
        "relevance_why": str(raw.get("relevance_why", "")).strip(),
    }
    try:
        out["relevance"] = max(1, min(5, int(raw.get("relevance", 3))))
    except (TypeError, ValueError):
        out["relevance"] = 3
    if not out["one_liner"]:
        raise SummarizerError("one_liner 가 비어 있습니다.")
    return out


def summarize_one(entry: dict, exe: str, timeout: int = 300, retries: int = 2) -> dict:
    prompt = PROMPT.format(
        title=entry.get("title", ""),
        categories=", ".join(entry.get("categories", [])),
        authors=", ".join(entry.get("authors", [])[:8]),
        abstract=entry.get("abstract", ""),
        rubric=RELEVANCE_RUBRIC,
    )
    last: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            stdout = _run_cli(exe, prompt, timeout)
            envelope = _extract_json(stdout)
            # --output-format json 은 {"result": "...", ...} 형태로 감싼다.
            payload = envelope.get("result") if isinstance(envelope.get("result"), str) else None
            raw = _extract_json(payload) if payload else envelope
            return _normalize(raw)
        except (SummarizerError, subprocess.TimeoutExpired) as exc:
            last = exc
            if attempt <= retries:
                print(f"    재시도 {attempt}/{retries} ({entry.get('id')}): {str(exc)[:120]}")
    raise SummarizerError(str(last))


def summarize_many(entries: list[dict], workers: int = 3, timeout: int = 300) -> tuple[int, int]:
    """entries 를 제자리에서 갱신. (성공, 실패) 개수를 돌려준다."""
    if not entries:
        return 0, 0
    exe = find_cli()
    from .store import now_iso

    ok = fail = 0

    def work(entry: dict) -> tuple[dict, dict | None, str]:
        try:
            return entry, summarize_one(entry, exe, timeout), ""
        except Exception as exc:  # noqa: BLE001 - 한 건 실패로 전체를 멈추지 않는다
            return entry, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, (entry, summary, err) in enumerate(pool.map(work, entries), 1):
            title = (entry.get("title") or entry.get("id", ""))[:60]
            if summary:
                entry["summary"] = summary
                entry["summarized_at"] = now_iso()
                ok += 1
                print(f"  [{i}/{len(entries)}] OK  {entry['id']} {title}")
            else:
                fail += 1
                print(f"  [{i}/{len(entries)}] 실패 {entry['id']} {title} — {err[:160]}", file=sys.stderr)
    return ok, fail
