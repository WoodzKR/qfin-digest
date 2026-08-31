"""논문 1편 상세 리포트 생성 (report/paper/{id}.html).

arXiv 전문(HTML) 또는 SSRN PDF 본문을 확보해 한국어 심층 리포트를 만든다.
본문을 못 구하면 초록만으로 생성하되 그 사실을 리포트에 명시한다.

수식 처리: arXiv 의 LaTeXML 출력은 `<math alttext="\\bar{p}_{id}">` 형태로 원본
LaTeX 를 품고 있다. 태그를 그냥 벗기면 첨자·기호가 뭉개지므로, 태그 제거 **전에**
alttext 를 `\\( ... \\)` 로 되살린 뒤 모델에 넘기고, 출력 리포트는 MathJax 로 렌더한다.
"""

from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path

import requests

from .config import HTML_URL, PAPER_DIR, USER_AGENT, ensure_dirs
from .render import CSS, _esc, abs_url, pdf_url
from .summarize import SummarizerError, _extract_json, _run_cli, find_cli

_SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_MATH_RE = re.compile(r"<math\b[^>]*?\balttext=\"(.*?)\"[^>]*>.*?</math>", re.S | re.I)
_BLOCK_RE = re.compile(r"</(p|div|section|h[1-6]|li|tr|table|figure|blockquote)\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

MAX_CHARS = 90_000

STYLE_RULES = """문체 규칙 — 이 리포트는 가독성이 생명입니다. 아래를 반드시 지키세요.
- 영어를 직역하지 말고 한국어로 다시 쓴다는 생각으로 작성하세요.
- 한 문장은 60자 안팎으로 끊으세요. 접속사로 계속 이어붙인 긴 문장을 만들지 마세요.
- 수동태를 능동태로 바꾸세요. ("~에 의해 측정된다" → "~로 측정한다")
- 번역투를 피하세요. "~에 대한", "~를 통하여", "~에 있어서", "~하는 것을 통해" 금지.
- 명사를 셋 이상 연달아 붙이지 마세요. 조사를 넣어 풀어 쓰세요.
- 한 문단은 2~4문장. 5문장을 넘기면 문단을 나누세요.
- 나열·비교는 문장 대신 <ul> 이나 <table> 로 빼서 문장 길이를 줄이세요.
- 전문 용어는 처음 나올 때만 한국어(영문) 병기하고, 그 뒤로는 한국어만 쓰세요.
- 문장 끝은 '~다'로 통일하고, 구어체·감탄사·수사 의문문을 쓰지 마세요."""

MATH_RULES = r"""수식 표기 — 페이지에 MathJax 가 들어 있습니다.
- 인라인 수식은 \( ... \), 별행 수식은 \[ ... \] 로 감싸 LaTeX 그대로 쓰세요.
- 본문에 이미 \( ... \) 형태로 들어 있는 수식은 그대로 옮기세요. 임의로 고치지 마세요.
- 수식 뒤에는 기호가 무엇을 뜻하는지 한 줄로 풀어 주세요.
- 수식에는 <code> 를 쓰지 마세요. <code> 는 변수명·파일명·함수명에만 씁니다."""

PROMPT = """당신은 퀀트 리서치 애널리스트입니다. 아래 논문을 읽고 한국어 심층 리포트를 작성하세요.
독자는 금융공학 배경은 있지만 이 논문은 처음 보는 실무자입니다.

[제목] {title}
[저자] {authors}
[분류] {categories}
[출처] {origin}
[본문 출처] {source}

<paper>
{body}
</paper>

아래 순서의 HTML 조각만 출력하세요. <html>/<head>/<body> 태그와 코드펜스는 쓰지 마세요.
쓸 수 있는 태그: h2, h3, p, ul, ol, li, table, thead, tbody, tr, th, td, strong, em, code, blockquote.

<h2>1. 한눈에 보기</h2>
  먼저 <blockquote> 안에 이 논문의 결론을 2문장으로 적고, 이어서 <ul> 로 핵심 포인트 3~4개.
<h2>2. 문제의식과 배경</h2>
  기존 연구가 어디서 막혔는지, 이 논문은 무엇을 다르게 보는지.
<h2>3. 방법론</h2>
  모델과 알고리즘을 단계별로. 핵심 수식은 별행으로 보이고 기호를 설명.
<h2>4. 데이터와 실험 설계</h2>
  데이터셋·기간·벤치마크·평가지표. 항목이 여럿이면 <table> 로 정리.
<h2>5. 주요 결과</h2>
  수치를 인용해 구체적으로. 수치 비교는 <table> 로.
<h2>6. 한계와 주의점</h2>
  저자가 밝힌 한계와, 재현·실전 적용에서 걸릴 지점.
<h2>7. 실무 적용 아이디어</h2>
  포트폴리오나 트레이딩에 쓴다면 무엇을, 어떻게, 어떤 데이터로. 구체적으로.
<h2>8. 함께 볼 만한 개념</h2>
  관련 기법과 논문 키워드를 <ul> 로.

{style}

{math}

사실 규칙:
- 본문에 없는 수치나 결과를 지어내지 마세요. 근거가 없으면 "본문에 명시되지 않음"이라고 쓰세요.
- 본문이 초록뿐이라면 1번 항목 끝에 그 사실을 한 문장으로 밝히고, 추론한 대목은 "추정"이라고 표시하세요.
"""


def html_to_text(page: str, keep_math: bool = True) -> str:
    """HTML → 평문. 수식은 LaTeX 로 되살리고 블록 경계는 줄바꿈으로 남긴다."""
    body = _SCRIPT_RE.sub(" ", page)
    if keep_math:
        body = _MATH_RE.sub(lambda m: " \\(" + html.unescape(m.group(1)).strip() + "\\) ", body)
    body = _BLOCK_RE.sub("\n", body)
    text = html.unescape(_TAG_RE.sub(" ", body))
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_fulltext(paper_id: str, session: requests.Session | None = None) -> tuple[str, str]:
    """arXiv 전문 HTML → (본문 텍스트, 출처 설명). 없으면 ('', 사유)."""
    sess = session or requests.Session()
    try:
        resp = sess.get(HTML_URL.format(id=paper_id), headers={"User-Agent": USER_AGENT}, timeout=90)
    except requests.RequestException:
        return "", "요청 실패 (초록만 사용)"
    if resp.status_code != 200 or "<html" not in resp.text.lower():
        return "", "전문 HTML 없음 (초록만 사용)"
    text = html_to_text(resp.text)
    if len(text) < 2000:
        return "", "전문 HTML 내용 부족 (초록만 사용)"
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], f"arXiv HTML 전문{' (앞부분 발췌)' if truncated else ''}"


def _clean_fragment(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:html)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    body = re.search(r"<body[^>]*>(.*)</body>", text, re.S | re.I)
    if body:
        text = body.group(1).strip()
    return text


MATHJAX = r"""
<script>
window.MathJax={
  tex:{inlineMath:[['\\(','\\)']],displayMath:[['\\[','\\]'],['$$','$$']],processEscapes:true},
  options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']},
  chtml:{scale:0.98}
};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
"""

DOC_CSS = textwrap.dedent("""
.doc{max-width:780px}
.doc h1{font-size:24px;line-height:1.35;margin:0 0 10px}
.doc h2{font-size:19px;margin:38px 0 12px;padding-bottom:7px;border-bottom:2px solid var(--accent);
  letter-spacing:-.01em}
.doc h3{font-size:15.5px;margin:22px 0 8px;color:var(--accent)}
.doc p{margin:0 0 14px}
.doc ul,.doc ol{margin:0 0 16px;padding-left:22px}
.doc li{margin-bottom:7px}
.doc blockquote{margin:0 0 18px;padding:14px 18px;border-left:3px solid var(--accent);
  background:var(--accent-soft);border-radius:0 8px 8px 0;font-size:15.5px}
.doc blockquote p:last-child{margin-bottom:0}
.doc table{width:100%;border-collapse:collapse;margin:0 0 18px;font-size:13.5px;
  display:block;overflow-x:auto}
.doc th,.doc td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
.doc th{background:var(--panel-2);font-weight:650;white-space:nowrap}
.doc code{background:var(--panel-2);border:1px solid var(--line);border-radius:4px;
  padding:1px 5px;font-size:13px}
.doc mjx-container[display="true"]{margin:16px 0;overflow-x:auto;overflow-y:hidden;padding:2px 0}
.doc .meta-head{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin:18px 0 26px;box-shadow:var(--shadow)}
.doc .meta-head .sub{margin-bottom:4px}
""")


def build_report(entry: dict, body: str, source: str, timeout: int = 900) -> Path:
    """본문 텍스트를 받아 상세 리포트 HTML 을 쓴다."""
    ensure_dirs()
    exe = find_cli()
    pid = entry["id"]
    prompt = PROMPT.format(
        title=entry.get("title", pid),
        authors=", ".join(entry.get("authors", [])),
        categories=", ".join(entry.get("categories") or entry.get("src_cats") or []),
        origin=("arXiv:" + entry.get("ext_id", pid)) if entry.get("src", "arxiv") == "arxiv"
               else ("SSRN abstract_id " + entry.get("ext_id", "")),
        source=source,
        body=body,
        style=STYLE_RULES,
        math=MATH_RULES,
    )
    stdout = _run_cli(exe, prompt, timeout)
    envelope = _extract_json(stdout)
    fragment = _clean_fragment(envelope.get("result") if isinstance(envelope.get("result"), str) else "")
    if len(fragment) < 200:
        raise SummarizerError(f"{pid}: 리포트 본문이 비었습니다.")

    summary = entry.get("summary") or {}
    authors = ", ".join(entry.get("authors", []))
    tags = ", ".join(entry.get("categories") or entry.get("src_cats") or [])
    origin_label = ("arXiv:" + entry.get("ext_id", pid)) if entry.get("src", "arxiv") == "arxiv" \
        else ("SSRN " + entry.get("ext_id", ""))

    out = PAPER_DIR / f"{pid}.html"
    out.write_text(f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(entry.get('title', pid))} — 상세 리포트</title>
<style>{CSS}{DOC_CSS}</style>
{MATHJAX}
</head>
<body>
<div class="wrap doc">
  <p class="sub"><a href="javascript:history.back()">← 돌아가기</a></p>
  <h1>{_esc(entry.get('title', pid))}</h1>
  <div class="meta-head">
    <p class="sub">{_esc(authors)}</p>
    <p class="sub">{_esc(origin_label)} · {_esc(tags)}</p>
    <p class="sub">본문 출처: {_esc(source)}</p>
    <div class="actions">
      <a class="btn" href="{_esc(abs_url(entry))}" target="_blank" rel="noopener">원문 페이지</a>
      <a class="btn" href="{_esc(pdf_url(entry))}" target="_blank" rel="noopener">원문 PDF</a>
    </div>
  </div>
  {f'<blockquote><p>{_esc(summary.get("one_liner", ""))}</p></blockquote>' if summary.get("one_liner") else ''}
  {fragment}
  <div class="abs" style="margin-top:32px"><b>ORIGINAL ABSTRACT</b>{_esc(entry.get('abstract', ''))}</div>
  <footer><p>로컬 Claude Code 로 생성한 요약 리포트입니다. 인용 전 반드시 원문을 확인하세요.</p></footer>
</div>
</body>
</html>
""", encoding="utf-8")
    return out


def build_paper_report(entry: dict, session: requests.Session | None = None,
                       timeout: int = 900, ssrn_browser=None) -> Path:
    """출처에 맞게 본문을 확보한 뒤 리포트를 만든다."""
    src = entry.get("src", "arxiv")
    if src == "ssrn":
        from . import ssrn

        body, source = ssrn.fetch_fulltext(entry, browser=ssrn_browser)
    else:
        body, source = fetch_fulltext(entry.get("ext_id", entry["id"]), session)

    if not body:
        body = entry.get("abstract", "")
        if not body:
            raise SummarizerError(f"{entry['id']}: 본문도 초록도 없습니다.")
        source = source or "초록만 사용"
    return build_report(entry, body, source, timeout=timeout)
