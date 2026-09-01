"""Deep report for a single paper -> ``report/paper/{id}.{lang}.html``.

Body text comes from the arXiv HTML edition or the SSRN PDF. If neither can be
had we fall back to the abstract and say so on the page.

Math: arXiv's LaTeXML output carries the original LaTeX in
``<math alttext="\\bar{p}_{id}">``. Stripping tags first mangles subscripts into
noise, so alttext is restored to ``\\( ... \\)`` *before* tags are removed, and
the rendered page loads MathJax.
"""

from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path

import requests

from .config import (BLOG_SOURCES, HTML_URL, LANGS, PAPER_DIR, USER_AGENT, ensure_dirs,
                     report_name)
from .render import CSS, _esc, abs_url, pdf_url
from .summarize import SummarizerError, _extract_json, _run_cli, find_cli
from .store import text as summary_text

_SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_MATH_RE = re.compile(r"<math\b[^>]*?\balttext=\"(.*?)\"[^>]*>.*?</math>", re.S | re.I)
_BLOCK_RE = re.compile(r"</(p|div|section|h[1-6]|li|tr|table|figure|blockquote)\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

MAX_CHARS = 90_000

MATH_RULES = r"""Math notation — the page ships with MathJax.
- Inline math goes in \( ... \); display math in \[ ... \]. Write raw LaTeX.
- Math already present as \( ... \) in the source must be copied verbatim.
- After a formula, explain what each symbol means in one line.
- Never wrap math in <code>. <code> is only for variable, file and function names."""

KO_SECTIONS = """<h2>1. 한눈에 보기</h2>
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
<h2>7. 시스템 트레이딩 적용 아이디어</h2>
  자동매매로 옮긴다면 어떤 신호를, 어떤 데이터로, 어떤 주기로. 구체적으로.
<h2>8. 함께 볼 만한 개념</h2>
  관련 기법과 논문 키워드를 <ul> 로."""

KO_STYLE = """문체 규칙 — 번역체와 AI 문체를 쓰지 마세요. 한국어로 처음부터 쓴다는 생각으로.

금지 표현
- 번역투 조사: "~에 대한", "~를 통하여", "~에 있어서", "~하는 것을 통해", "~와 관련하여"
- 이중 피동 "~되어진다", "~지게 된다". "~에 의해" 피동은 행위자를 주어로.
  ("모델에 의해 예측된다" → "모델이 예측한다")
- have/take 직역 "~을 가지고 있다" → "~이 있다", "~이 강하다"
- 만능 동사 "보여준다", "제공한다", "시사한다", "가져온다" → 구체 동사와 수치로
- 과장 어휘 "혁신적", "획기적", "압도적", "전례 없는", "시사하는 바가 크다", "주목할 만하다"
- 죽은 은유 "잠식", "청사진", "적신호", "신호탄", "움켜쥐다", "뿌리내리다", "짓누르다"
- 상승 공식 "단순한 X를 넘어 Y", "X에서 Y로"
- 분열문 "핵심은 ~이다", "중요한 것은 ~이다", "주목할 점은 ~이다" → 바로 단언
- 도치 결산 "~하는 이유다" → "그래서 ~다"
- 나열 도입구 "크게 세 가지로 나눌 수 있다", "다음과 같다" → 도입구 없이 바로 본론
- 연결어미(-고, -며, -지만, -면서, -아서) **직후 쉼표 금지.** 가장 강한 AI 신호입니다.

결산 표현 절제
- "결론적으로", "따라서", "이를 통해", "요약하면", "결국"은 리포트 전체에서 합쳐 두 번까지.
- 문단 첫머리 "또한 / 나아가 / 게다가 / 즉"을 한 문단에 세 번 이상 쓰지 마세요.
- 섹션을 "~할 때다", "~할 시점이다"로 닫지 마세요.

리듬
- 한 문장 60자 안팎. 다만 전부 같은 길이면 기계처럼 읽힙니다. 짧은 문장을 섞고,
  문단마다 긴 문장 하나쯤은 두세요.
- 같은 종결어미를 네 문장 넘게 잇지 마세요.
- 한 문단은 2~4문장. 다섯 문장을 넘기면 나누세요.
- 명사를 셋 이상 붙이지 말고, 명사 앞 관형절이 길어지면 문장을 나누세요.
- "-적/-성/-화"를 겹쳐 쓰지 마세요. ("전략적 함의" → "전략상 의미")
- 나열·비교는 문장 대신 <ul> 이나 <table> 로 빼세요.

용어 일관성 — 리포트 전체를 한 번에 쓰는 이점을 살리세요.
- 한 개념에는 한 번 정한 번역어를 끝까지 씁니다. 3번 섹션에서 "타이밍 알파"라고 했으면
  6번 섹션에서 "시점 초과수익"으로 바꾸지 마세요.
- 논문이 정의한 기호와 이름은 그 논문의 용법을 따릅니다. 더 자연스러운 말이 떠올라도
  정의된 용어를 바꾸지 마세요.
- 앞 섹션에서 설명한 개념은 뒤에서 다시 풀어 쓰지 말고 그대로 지칭하세요.

지켜야 할 것
- 전문 용어는 처음 나올 때만 한국어(영문) 병기하고, 그 뒤로는 한국어만.
- 문장 끝은 '~다'로 통일. 구어체와 수사 의문문은 쓰지 마세요.
- 원문이 "~할 수 있다"로 유보한 주장을 "~한다"로 단정하지 마세요. 확신의 세기를 그대로.
- 원문에 없는 비유나 상투구를 새로 만들어 넣지 마세요.
- 흔한 말로 쓰세요. 더 고유한 한국어처럼 보이려고 덜 쓰이는 어휘를 고르지 마세요.
  ("비교했다"를 "견주었다"로 바꾸는 식은 가독성만 떨어뜨립니다.)"""

KO_FACTS = """사실 규칙:
- 본문에 없는 수치나 결과를 지어내지 마세요. 근거가 없으면 "본문에 명시되지 않음"이라고 쓰세요.
- 본문이 초록뿐이라면 1번 항목 끝에 그 사실을 한 문장으로 밝히고,
  추론한 대목은 "추정"이라고 표시하세요."""

EN_SECTIONS = """<h2>1. At a glance</h2>
  Open with a <blockquote> holding the paper's conclusion in two sentences,
  then a <ul> of 3-4 key points.
<h2>2. The gap it targets</h2>
  Where prior work stalls, and what this paper looks at differently.
<h2>3. Method</h2>
  The model and algorithm, step by step. Show key formulas on their own line
  and explain the symbols.
<h2>4. Data and experimental design</h2>
  Datasets, window, benchmarks, metrics. Use a <table> when there are several.
<h2>5. Results</h2>
  Concrete, with the reported numbers. Put comparisons in a <table>.
<h2>6. Limitations</h2>
  What the authors flag, plus what would bite on replication or in production.
<h2>7. Systematic trading angle</h2>
  If you traded this: which signal, from which data, at what cadence. Be specific.
<h2>8. Related concepts</h2>
  Adjacent techniques and search keywords, as a <ul>."""

EN_STYLE = """Style rules — this report lives or dies on readability.
- Plain, direct sentences. Aim under 20 words; break anything longer.
- Active voice, named actors. No "it can be observed that".
- Paragraphs of 2-4 sentences. Split anything past five.
- Push enumerations and comparisons into <ul> or <table> instead of prose.
- Define a term once on first use, then just use it.
- No filler openers, no rhetorical questions, no hedging strings."""

EN_FACTS = """Accuracy rules:
- Never invent numbers or findings. If the source is silent, write
  "not stated in the paper".
- If the only source was the abstract, say so in one sentence at the end of
  section 1 and mark anything inferred as an inference."""

LANG_SPEC = {
    "ko": {"name": "Korean", "sections": KO_SECTIONS, "style": KO_STYLE, "facts": KO_FACTS,
           "back": "← 돌아가기", "src": "본문 출처", "page": "원문 페이지", "pdf": "원문 PDF",
           "abs": "ORIGINAL ABSTRACT",
           "foot": "로컬 Claude Code 로 생성한 요약 리포트입니다. 인용 전 반드시 원문을 확인하세요.",
           "suffix": "상세 리포트"},
    "en": {"name": "English", "sections": EN_SECTIONS, "style": EN_STYLE, "facts": EN_FACTS,
           "back": "← Back", "src": "Body source", "page": "Source page", "pdf": "Source PDF",
           "abs": "ORIGINAL ABSTRACT",
           "foot": "Generated locally with Claude Code. Check the original before citing.",
           "suffix": "deep report"},
}

PROMPT = """You are a quant research analyst. Read the paper below and write a deep
report in {language}. The reader knows financial engineering but has not seen this paper.

[Title] {title}
[Authors] {authors}
[Categories] {categories}
[Source] {origin}
[Body source] {source}

<paper>
{body}
</paper>
{critique}
Output an HTML fragment only, in the section order below. No <html>/<head>/<body>
wrapper, no code fences. Allowed tags: h2, h3, p, ul, ol, li, table, thead, tbody,
tr, th, td, strong, em, code, blockquote.

{sections}

{style}

{math}

{facts}
"""


def html_to_text(page: str, keep_math: bool = True) -> str:
    """HTML -> plain text, restoring math as LaTeX and keeping block boundaries."""
    body = _SCRIPT_RE.sub(" ", page)
    if keep_math:
        body = _MATH_RE.sub(lambda m: " \\(" + html.unescape(m.group(1)).strip() + "\\) ", body)
    body = _BLOCK_RE.sub("\n", body)
    text = html.unescape(_TAG_RE.sub(" ", body))
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_fulltext(paper_id: str, session: requests.Session | None = None) -> tuple[str, str]:
    """arXiv HTML edition -> (body text, provenance). Empty body means no full text."""
    sess = session or requests.Session()
    try:
        resp = sess.get(HTML_URL.format(id=paper_id), headers={"User-Agent": USER_AGENT},
                        timeout=90)
    except requests.RequestException:
        return "", "request failed (abstract only)"
    if resp.status_code != 200 or "<html" not in resp.text.lower():
        return "", "no HTML edition (abstract only)"
    text = html_to_text(resp.text)
    if len(text) < 2000:
        return "", "HTML edition too thin (abstract only)"
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS], f"arXiv HTML full text{' (truncated)' if truncated else ''}"


REVIEW_PROMPT = """Use the academic-paper-reviewer skill in quick assessment mode on the
paper below. Judge the work, do not summarize it.

[Title] {title}
[Source] {origin}

<paper>
{body}
</paper>

Return plain text under these headings, nothing else:

CLAIMS      The 2-3 claims the paper actually stands on.
METHOD      Whether the design can support those claims. Name the identifying
            assumption and say if it holds.
VALIDITY    Concrete threats: look-ahead, survivorship, multiple testing, sample
            selection, overfitting, unreported transaction costs, regime
            dependence. Only ones you can point at in the text.
COUNTER     The strongest argument against the headline result.
NUMBERS     Reported figures a reader should not take at face value, and why.
UNSTATED    What a practitioner needs that the paper never reports.

Rules:
- Cite the paper's own numbers when you challenge them.
- If the source text is only an abstract, say so and keep the critique to what
  is actually visible.
- No praise, no hedging filler. Every line must be actionable."""


def review_paper(entry: dict, body: str, origin: str, exe: str, timeout: int = 900) -> str:
    """Critique pass. Feeds the Korean report so its analysis is not just paraphrase."""
    try:
        stdout = _run_cli(exe, REVIEW_PROMPT.format(
            title=entry.get("title", entry["id"]), origin=origin, body=body), timeout)
        envelope = _extract_json(stdout)
        critique = envelope.get("result") if isinstance(envelope.get("result"), str) else ""
    except Exception as exc:  # noqa: BLE001 - the review is an enhancement, never fatal
        print(f"      review skipped: {str(exc)[:110]}")
        return ""
    critique = critique.strip()
    return critique if len(critique) > 200 else ""


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
.doc .langlinks{float:right;font-size:12.5px}
""")


CRITIQUE_BLOCK = """
An independent reviewer assessed this paper. Use it for sections 5 and 6 — the
results and the limitations must reflect these findings, not just restate the
paper's own framing. Do not copy it verbatim and do not add claims it does not make.

<reviewer_notes>
{critique}
</reviewer_notes>
"""


def build_report(entry: dict, body: str, source: str, lang: str = "ko",
                 timeout: int = 900, review: bool = False) -> Path:
    """Turn body text into a deep report page in ``lang``."""
    ensure_dirs()
    spec = LANG_SPEC[lang]
    exe = find_cli()
    pid = entry["id"]
    src = entry.get("src", "arxiv")
    origin = {"arxiv": f"arXiv:{entry.get('ext_id', pid)}",
              "ssrn": f"SSRN abstract_id {entry.get('ext_id', '')}"}.get(
        src, f"{src} · {entry.get('abs_url', '')}")

    critique = review_paper(entry, body, origin, exe, timeout) if review else ""
    if critique:
        print(f"      reviewer notes: {len(critique)} chars")

    prompt = PROMPT.format(
        language=spec["name"],
        critique=CRITIQUE_BLOCK.format(critique=critique) if critique else "",
        title=entry.get("title", pid),
        authors=", ".join(entry.get("authors", [])),
        categories=", ".join(entry.get("categories") or entry.get("src_cats") or []),
        origin=origin,
        source=source,
        body=body,
        sections=spec["sections"],
        style=spec["style"],
        math=MATH_RULES,
        facts=spec["facts"],
    )
    envelope = _extract_json(_run_cli(exe, prompt, timeout))
    fragment = _clean_fragment(
        envelope.get("result") if isinstance(envelope.get("result"), str) else "")
    if len(fragment) < 200:
        raise SummarizerError(f"{pid}: report body came back empty.")

    one_liner = summary_text(entry, lang).get("one_liner", "")
    tags = ", ".join(entry.get("categories") or entry.get("src_cats") or [])
    others = "".join(
        f'<a href="{_esc(report_name(pid, other))}">{LANG_SPEC[other]["name"]}</a> '
        for other in LANGS if other != lang and (PAPER_DIR / report_name(pid, other)).exists())

    out = PAPER_DIR / report_name(pid, lang)
    out.write_text(f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(entry.get('title', pid))} — {spec['suffix']}</title>
<style>{CSS}{DOC_CSS}</style>
{MATHJAX}
</head>
<body>
<div class="wrap doc">
  <p class="sub"><span class="langlinks">{others}</span>
     <a href="javascript:history.back()">{spec['back']}</a></p>
  <h1>{_esc(entry.get('title', pid))}</h1>
  <div class="meta-head">
    <p class="sub">{_esc(", ".join(entry.get("authors", [])))}</p>
    <p class="sub">{_esc(origin)} · {_esc(tags)}</p>
    <p class="sub">{spec['src']}: {_esc(source)}</p>
    <div class="actions">
      <a class="btn" href="{_esc(abs_url(entry))}" target="_blank" rel="noopener">{spec['page']}</a>
      {f'<a class="btn" href="{_esc(pdf_url(entry))}" target="_blank" rel="noopener">{spec["pdf"]}</a>' if pdf_url(entry) else ''}
    </div>
  </div>
  {f'<blockquote><p>{_esc(one_liner)}</p></blockquote>' if one_liner else ''}
  {fragment}
  <div class="abs" style="margin-top:32px"><b>{spec['abs']}</b>{_esc(entry.get('abstract', ''))}</div>
  <footer><p>{spec['foot']}</p></footer>
</div>
</body>
</html>
""", encoding="utf-8")
    return out


def build_paper_report(entry: dict, session: requests.Session | None = None,
                       timeout: int = 900, ssrn_browser=None, lang: str = "ko",
                       review: bool = False) -> Path:
    """Get the body from the right place for this source, then write the report."""
    src = entry.get("src", "arxiv")
    if src == "ssrn":
        from . import ssrn

        body, source = ssrn.fetch_fulltext(entry, browser=ssrn_browser)
    elif src in BLOG_SOURCES:
        from . import blogs

        body, source = blogs.fetch_fulltext(entry, session)
    else:
        body, source = fetch_fulltext(entry.get("ext_id", entry["id"]), session)

    if not body:
        body = entry.get("abstract", "")
        if not body:
            raise SummarizerError(f"{entry['id']}: no full text and no abstract.")
        source = source or "abstract only"
    return build_report(entry, body, source, lang=lang, timeout=timeout, review=review)
