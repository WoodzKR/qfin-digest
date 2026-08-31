"""seen.json → 단일 HTML 리포트 (MathJax 외에는 외부 의존 없음)."""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import (ABS_URL, CATEGORIES, PAPER_DIR, PDF_URL, REPORT_DIR, SSRN_ABS_URL,
                     SSRN_JOURNALS, SSRN_PDF_URL, ensure_dirs)

CAT_SHORT = {"q-fin.PM": "PM", "q-fin.ST": "ST", "q-fin.TR": "TR"}
SSRN_SHORTS = {short: name for short, name in SSRN_JOURNALS.values()}
SRC_LABEL = {"arxiv": "arXiv", "ssrn": "SSRN"}


def abs_url(entry: dict) -> str:
    if entry.get("src") == "ssrn":
        return entry.get("abs_url") or SSRN_ABS_URL.format(id=entry.get("ext_id", ""))
    return ABS_URL.format(id=entry.get("ext_id") or entry.get("id", ""))


def pdf_url(entry: dict) -> str:
    if entry.get("src") == "ssrn":
        return entry.get("pdf_url") or SSRN_PDF_URL.format(id=entry.get("ext_id", ""))
    return PDF_URL.format(id=entry.get("ext_id") or entry.get("id", ""))


CSS = """
:root{
  --bg:#f6f7f9; --panel:#ffffff; --panel-2:#fbfcfd; --ink:#16191d; --muted:#5c6672;
  --line:#e2e6ea; --accent:#3b6ef0; --accent-soft:#eaf0fe;
  --pm:#3b6ef0; --st:#0f9d76; --tr:#d4791f; --ssrn:#8b5cf6; --other:#7a68c9;
  --star:#f0a91b; --shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#101317; --panel:#181c22; --panel-2:#1e232a; --ink:#e7ebf0; --muted:#98a3b0;
    --line:#2a3038; --accent:#7ea3ff; --accent-soft:#1d2637;
    --pm:#7ea3ff; --st:#4bd6a8; --tr:#f0ad5e; --ssrn:#b18cff; --other:#b0a0f0;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 14px rgba(0,0,0,.25);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,"Segoe UI","Malgun Gothic",Roboto,"Helvetica Neue",sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:32px 20px 140px}
a{color:var(--accent)}

header.top{margin-bottom:24px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:13.5px;margin:0}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:9px 13px;font-size:13px;box-shadow:var(--shadow)}
.stat b{font-size:16px;margin-right:5px}

.controls{position:sticky;top:0;z-index:20;background:var(--bg);
  padding:12px 0 10px;margin:20px 0 8px;border-bottom:1px solid var(--line)}
.row{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-bottom:7px}
.row:last-child{margin-bottom:0}
.rowlabel{font-size:11.5px;color:var(--muted);font-weight:700;letter-spacing:.06em;
  min-width:38px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--muted);
  border-radius:999px;padding:5px 12px;font-size:12.5px;cursor:pointer;
  font-family:inherit;transition:.12s;white-space:nowrap}
.chip[aria-pressed="true"]{background:var(--accent-soft);border-color:var(--accent);
  color:var(--accent);font-weight:600}
.chip:hover{border-color:var(--accent)}
#q{flex:1;min-width:180px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink);font:inherit;font-size:13.5px}
#q:focus{outline:2px solid var(--accent);outline-offset:-1px}
select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink);font:inherit;font-size:13.5px}
.count{color:var(--muted);font-size:12.5px;margin-left:auto}

h2.day{font-size:15px;margin:30px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line);
  color:var(--muted);font-weight:600;letter-spacing:.02em}
h2.day span{color:var(--ink)}

.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow)}
.card.hide{display:none}
.badges{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:2.5px 8px;
  border-radius:5px;color:#fff}
.b-PM{background:var(--pm)} .b-ST{background:var(--st)} .b-TR{background:var(--tr)}
.b-ssrn{background:var(--ssrn)} .b-XX{background:var(--other)}
.badge.ghost{background:transparent;border:1px solid var(--line);color:var(--muted);font-weight:600}
.stars{color:var(--star);font-size:12.5px;letter-spacing:1px;margin-left:auto}
.stars i{color:var(--line);font-style:normal}

.title{font-size:16.5px;font-weight:650;line-height:1.4;margin:0 0 6px;letter-spacing:-.01em}
.title a{color:var(--ink);text-decoration:none}
.title a:hover{color:var(--accent)}
.oneliner{margin:0 0 8px;font-size:14.5px;color:var(--ink)}
.oneliner::before{content:"\\25B8 ";color:var(--accent)}
.authors{margin:0;color:var(--muted);font-size:12.5px}

.detail{margin-top:12px;padding-top:12px;border-top:1px dashed var(--line)}
.detail[hidden]{display:none}
.detail ul{margin:0 0 12px;padding-left:19px}
.detail li{margin-bottom:4px}
.kv{display:grid;grid-template-columns:76px 1fr;gap:5px 10px;font-size:13.5px;margin-bottom:12px}
.kv dt{color:var(--muted);font-weight:600}
.kv dd{margin:0}
.keys{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
.key{font-size:11.5px;background:var(--panel-2);border:1px solid var(--line);
  border-radius:5px;padding:2px 7px;color:var(--muted)}
.abs{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
  padding:11px 13px;font-size:13px;color:var(--muted);line-height:1.7}
.abs b{color:var(--ink);display:block;margin-bottom:4px;font-size:12px;letter-spacing:.03em}

.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--muted);
  border-radius:7px;padding:5.5px 12px;font-size:12.5px;cursor:pointer;
  font-family:inherit;text-decoration:none;display:inline-block;transition:.12s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}
.btn.queued{background:var(--accent-soft);border-color:var(--accent);color:var(--accent);font-weight:600}
.btn.done{border-color:var(--st);color:var(--st)}
.btn.failed{border-color:var(--tr);color:var(--tr)}
#livebadge{font-size:11.5px;color:var(--st);font-weight:700;letter-spacing:.03em;
  display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
#livebadge::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--st);
  animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

.bar{position:fixed;left:0;right:0;bottom:0;z-index:50;background:var(--panel);
  border-top:1px solid var(--line);box-shadow:0 -4px 20px rgba(0,0,0,.10);
  padding:12px 20px;display:none}
.bar.on{display:block}
.bar-in{max-width:1000px;margin:0 auto;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.bar code{background:var(--panel-2);border:1px solid var(--line);border-radius:6px;
  padding:4px 8px;font-size:12px;flex:1;min-width:200px;overflow:auto;white-space:nowrap}
.empty{color:var(--muted);text-align:center;padding:50px 0}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
@media print{.controls,.bar,.actions{display:none!important}.detail{display:block!important}
  .card{break-inside:avoid;box-shadow:none}}
"""

JS = """
const KEY='arxiv-qfin-report-queue';
const load=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){return []}};
const save=v=>{try{localStorage.setItem(KEY,JSON.stringify(v))}catch(e){}};

// 로컬 서버(run.py serve)가 뒤에 있으면 버튼 한 번으로 바로 생성한다.
// 서버가 없으면(파일 열기 / GitHub Pages) 예전처럼 명령어 복사 방식으로 되돌아간다.
let LIVE=false;
async function detectLive(){
  try{const r=await fetch('api/ping',{cache:'no-store'});LIVE=r.ok;}catch(e){LIVE=false;}
  document.getElementById('livebadge').hidden=!LIVE;
  paint();
}

function paint(){
  const q=LIVE?[]:load();
  document.querySelectorAll('.js-req').forEach(b=>{
    if(b.dataset.busy)return;
    const on=q.includes(b.dataset.id);
    b.classList.toggle('queued',on);
    b.textContent=on?'\\u2713 요청됨':'\\ud83d\\udcc4 보고서 생성';
  });
  document.getElementById('bar').classList.toggle('on',q.length>0);
  document.getElementById('qn').textContent=q.length;
  document.getElementById('qcmd').textContent='python run.py paper '+q.join(' ');
}

async function genReport(btn){
  if(btn.dataset.busy)return;
  const id=btn.dataset.id;
  btn.dataset.busy='1'; btn.classList.add('queued'); btn.textContent='\\u23f3 대기 중…';
  const fail=msg=>{btn.classList.remove('queued');btn.classList.add('failed');
    btn.textContent='\\u26a0 실패 — 다시 시도';btn.title=msg||'';delete btn.dataset.busy;};
  try{
    const r=await fetch('api/report',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    if(!r.ok){return fail('요청이 거부되었습니다 ('+r.status+')');}
    for(;;){
      await new Promise(res=>setTimeout(res,2000));
      const s=await (await fetch('api/status?id='+encodeURIComponent(id),
        {cache:'no-store'})).json();
      if(s.state==='done'){
        const a=document.createElement('a');
        a.className='btn done'; a.href=s.url; a.target='_blank'; a.rel='noopener';
        a.textContent='\\ud83d\\udcc4 상세 리포트 보기';
        btn.replaceWith(a); a.click(); return;
      }
      if(s.state==='error')return fail(s.error);
      if(s.note)btn.textContent='\\u23f3 '+s.note+'…';
    }
  }catch(e){fail(String(e));}
}
function toggleReq(id){
  const q=load(); const i=q.indexOf(id);
  if(i<0)q.push(id); else q.splice(i,1);
  save(q); paint();
}

const cards=[...document.querySelectorAll('.card')];
const pressed=sel=>[...document.querySelectorAll(sel)]
  .filter(c=>c.getAttribute('aria-pressed')==='true').map(c=>c.dataset.val);

// 보이는 카드 중 접혀 있는 게 하나라도 있으면 다음 동작은 '펼치기'
const visible=()=>[...document.querySelectorAll('.card:not(.hide)')];
const anyCollapsed=()=>visible().some(c=>c.querySelector('.detail').hidden);
function syncExpandLabel(){
  document.getElementById('expandBtn').textContent=anyCollapsed()?'전체 펼치기':'전체 접기';
}
function filter(){
  const srcs=pressed('.chip[data-kind="src"]');
  const cats=pressed('.chip[data-kind="cat"]');
  const term=document.getElementById('q').value.trim().toLowerCase();
  let n=0;
  cards.forEach(c=>{
    const okSrc=!srcs.length||srcs.includes(c.dataset.src);
    const okCat=!cats.length||cats.some(k=>c.dataset.cats.split('|').includes(k));
    const okTerm=!term||c.dataset.text.includes(term);
    const show=okSrc&&okCat&&okTerm;
    c.classList.toggle('hide',!show);
    if(show)n++;
  });
  document.querySelectorAll('section.day').forEach(s=>{
    s.style.display=s.querySelectorAll('.card:not(.hide)').length?'':'none';
  });
  document.getElementById('count').textContent=n+' / '+cards.length+'편 표시';
  document.getElementById('none').hidden=n>0;
  syncExpandLabel();
}
function sortBy(mode){
  document.querySelectorAll('section.day .list').forEach(list=>{
    [...list.children]
      .sort((a,b)=>mode==='rel'
        ? (+b.dataset.rel)-(+a.dataset.rel)||a.dataset.title.localeCompare(b.dataset.title)
        : (+a.dataset.idx)-(+b.dataset.idx))
      .forEach(el=>list.appendChild(el));
  });
}

document.addEventListener('click',e=>{
  const t=e.target.closest('[data-act]');
  if(!t)return;
  const act=t.dataset.act;
  if(act==='req'){ if(LIVE)genReport(t); else toggleReq(t.dataset.id); }
  else if(act==='toggle'){
    const d=t.closest('.card').querySelector('.detail');
    d.hidden=!d.hidden; t.textContent=d.hidden?'\\u25be 자세히':'\\u25b4 접기';
    syncExpandLabel();
  }
  else if(act==='chip'){
    t.setAttribute('aria-pressed',t.getAttribute('aria-pressed')==='true'?'false':'true');
    filter();
  }
  else if(act==='reset'){
    document.querySelectorAll('.chip[data-kind]').forEach(c=>c.setAttribute('aria-pressed','false'));
    document.getElementById('q').value=''; filter();
  }
  else if(act==='copy'){
    const txt=document.getElementById('qcmd').textContent;
    navigator.clipboard.writeText(txt).then(()=>{t.textContent='\\u2713 복사됨';
      setTimeout(()=>t.textContent='요청 목록 복사',1400);});
  }
  else if(act==='clear'){save([]);paint();}
  else if(act==='expand'){
    const open=anyCollapsed();
    visible().forEach(c=>{
      c.querySelector('.detail').hidden=!open;
      const b=c.querySelector('[data-act="toggle"]');
      if(b)b.textContent=open?'\\u25b4 접기':'\\u25be 자세히';
    });
    syncExpandLabel();
  }
});
document.getElementById('q').addEventListener('input',filter);
document.getElementById('sort').addEventListener('change',e=>sortBy(e.target.value));
paint();filter();detectLive();
"""


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _stars(n: int) -> str:
    n = max(1, min(5, int(n or 3)))
    return "★" * n + f"<i>{'★' * (5 - n)}</i>"


def _badge(cat: str, src: str) -> str:
    if src == "ssrn":
        return f'<span class="badge b-ssrn" title="{_esc(SSRN_SHORTS.get(cat, cat))}">{_esc(cat)}</span>'
    short = CAT_SHORT.get(cat)
    if short:
        return f'<span class="badge b-{short}">{short}</span>'
    return f'<span class="badge ghost">{_esc(cat)}</span>'


def _card(entry: dict, idx: int) -> str:
    pid = entry["id"]
    src = entry.get("src", "arxiv")
    summary = entry.get("summary") or {}
    src_cats = entry.get("src_cats") or []
    rel = int(summary.get("relevance", 3) or 3)
    authors = entry.get("authors") or []
    author_line = ", ".join(authors[:5]) + (f" 외 {len(authors) - 5}명" if len(authors) > 5 else "")
    if src == "ssrn" and entry.get("affiliations"):
        author_line += f" · {entry['affiliations']}"

    searchable = " ".join(
        [entry.get("title", ""), summary.get("one_liner", ""), summary.get("takeaway", "")]
        + list(summary.get("keywords") or []) + authors
        + list(entry.get("journals") or []) + [entry.get("abstract", "")]
    ).lower()

    badges = (f'<span class="badge ghost">{SRC_LABEL.get(src, src)}</span>'
              + "".join(_badge(c, src) for c in src_cats))
    if src == "arxiv":
        extra = [c for c in (entry.get("categories") or [])
                 if c not in src_cats and c not in CATEGORIES][:2]
        badges += "".join(f'<span class="badge ghost">{_esc(c)}</span>' for c in extra)
        if entry.get("cross_from"):
            badges += '<span class="badge ghost">cross-list</span>'
    elif entry.get("page_count"):
        badges += f'<span class="badge ghost">{entry["page_count"]}p</span>'

    bullets = "".join(f"<li>{_esc(b)}</li>" for b in (summary.get("bullets") or []))
    keys = "".join(f'<span class="key">{_esc(k)}</span>' for k in (summary.get("keywords") or []))
    kv = "".join(f"<dt>{label}</dt><dd>{_esc(value)}</dd>"
                 for label, value in (("방법", summary.get("method")),
                                      ("데이터", summary.get("data")),
                                      ("시사점", summary.get("takeaway")),
                                      (f"적용도 {rel}/5", summary.get("relevance_why"))) if value)

    if (PAPER_DIR / f"{pid}.html").exists():
        req_btn = (f'<a class="btn done" href="paper/{_esc(pid)}.html" target="_blank">'
                   f'📄 상세 리포트 보기</a>')
    else:
        req_btn = (f'<button class="btn js-req" data-act="req" data-id="{_esc(pid)}">'
                   f'📄 보고서 생성</button>')

    return f"""
<article class="card" data-src="{_esc(src)}" data-cats="{_esc('|'.join(src_cats))}"
         data-rel="{rel}" data-idx="{idx}" data-title="{_esc(entry.get('title', ''))}"
         data-text="{_esc(searchable)}">
  <div class="badges">{badges}
    <span class="badge ghost">{_esc(entry.get('ext_id', pid))}</span>
    <span class="stars" title="{_esc(f'시스템 트레이딩 구현 가능성 {rel}/5' + (' — ' + summary['relevance_why'] if summary.get('relevance_why') else ''))}">{_stars(rel)}</span>
  </div>
  <h3 class="title"><a href="{_esc(abs_url(entry))}" target="_blank"
      rel="noopener">{_esc(entry.get('title', pid))}</a></h3>
  <p class="oneliner">{_esc(summary.get('one_liner', '(요약 없음)'))}</p>
  <p class="authors">{_esc(author_line)}</p>
  <div class="detail" hidden>
    {f'<ul>{bullets}</ul>' if bullets else ''}
    {f'<dl class="kv">{kv}</dl>' if kv else ''}
    {f'<div class="keys">{keys}</div>' if keys else ''}
    <div class="abs"><b>ORIGINAL ABSTRACT</b>{_esc(entry.get('abstract', ''))}</div>
  </div>
  <div class="actions">
    <button class="btn" data-act="toggle">▾ 자세히</button>
    <a class="btn" href="{_esc(abs_url(entry))}" target="_blank" rel="noopener">원문</a>
    <a class="btn" href="{_esc(pdf_url(entry))}" target="_blank" rel="noopener">PDF</a>
    {req_btn}
  </div>
</article>"""


def build_index(seen: dict[str, dict] | None = None) -> Path:
    """저장소 루트 index.html — GitHub Pages 진입점 겸 리포트 목록."""
    from .config import ROOT

    ensure_dirs()
    digests = sorted(REPORT_DIR.glob("qfin-digest-*.html"), reverse=True)
    papers = sorted(PAPER_DIR.glob("*.html"))
    titles = {}
    if seen:
        titles = {e["id"]: e.get("title", e["id"]) for e in seen.values()}

    now = datetime.now()
    rows = ""
    for i, path in enumerate(digests):
        stamp = path.stem.replace("qfin-digest-", "")
        try:
            label = datetime.strptime(stamp, "%Y%m%d").strftime("%Y년 %m월 %d일")
        except ValueError:
            label = stamp
        tag = ' <span class="badge b-ssrn">최신</span>' if i == 0 else ""
        rows += (f'<li><a href="report/{path.name}">{_esc(label)} 다이제스트</a>{tag}</li>')

    plist = "".join(
        f'<li><a href="report/paper/{p.name}">{_esc(titles.get(p.stem, p.stem))}</a>'
        f' <span class="key">{_esc(p.stem)}</span></li>'
        for p in sorted(papers, key=lambda x: x.stat().st_mtime, reverse=True))

    out = ROOT / "index.html"
    out.write_text(f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>퀀트 논문 다이제스트</title>
<style>{CSS}
.wrap{{max-width:760px}}
ul.idx{{list-style:none;padding:0;margin:0 0 28px}}
ul.idx li{{padding:11px 14px;border:1px solid var(--line);border-radius:9px;
  background:var(--panel);margin-bottom:8px;box-shadow:var(--shadow);
  display:flex;align-items:center;gap:9px;flex-wrap:wrap}}
ul.idx a{{text-decoration:none;font-weight:600}}
ul.idx a:hover{{text-decoration:underline}}
h2.sec{{font-size:15px;color:var(--muted);margin:0 0 12px;letter-spacing:.02em}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>퀀트 논문 다이제스트</h1>
    <p class="sub">arXiv q-fin.PM/ST/TR · SSRN {len(SSRN_JOURNALS)}개 eJournal ·
       갱신 {now:%Y-%m-%d %H:%M}</p>
    <div class="stats">
      <div class="stat"><b>{len(digests)}</b>개 다이제스트</div>
      <div class="stat"><b>{len(papers)}</b>편 상세 리포트</div>
    </div>
  </header>

  <h2 class="sec">날짜별 다이제스트</h2>
  <ul class="idx">{rows or '<li>아직 생성된 리포트가 없습니다.</li>'}</ul>

  <h2 class="sec">상세 리포트</h2>
  <ul class="idx">{plist or '<li>아직 생성된 상세 리포트가 없습니다.</li>'}</ul>

  <footer><p>로컬 Claude Code 로 생성한 요약입니다. 원문 저작권은 각 저자에게 있습니다.</p></footer>
</div>
</body>
</html>
""", encoding="utf-8")
    return out


def build(seen: dict[str, dict], days: list[str] | None = None,
          sources: list[str] | None = None, out_path: Path | None = None) -> Path:
    """요약이 끝난 논문들로 HTML 리포트를 만든다."""
    ensure_dirs()
    entries = [e for e in seen.values() if (e.get("summary") or {}).get("one_liner")]
    if sources:
        entries = [e for e in entries if e.get("src", "arxiv") in set(sources)]
    if days:
        entries = [e for e in entries if e.get("listed_date") in set(days)]
    entries.sort(key=lambda e: (e.get("listed_date", ""),
                                int((e.get("summary") or {}).get("relevance", 3))), reverse=True)

    by_day: dict[str, list[dict]] = {}
    for entry in entries:
        by_day.setdefault(entry.get("listed_date", "unknown"), []).append(entry)

    cat_counts = Counter(c for e in entries for c in (e.get("src_cats") or []))
    src_counts = Counter(e.get("src", "arxiv") for e in entries)
    now = datetime.now()

    src_chips = "".join(
        f'<button class="chip" data-act="chip" data-kind="src" data-val="{s}" '
        f'aria-pressed="false">{SRC_LABEL[s]} ({src_counts.get(s, 0)})</button>'
        for s in ("arxiv", "ssrn") if src_counts.get(s))
    arxiv_chips = "".join(
        f'<button class="chip" data-act="chip" data-kind="cat" data-val="{c}" '
        f'aria-pressed="false" title="{_esc(name)}">{CAT_SHORT[c]} ({cat_counts.get(c, 0)})</button>'
        for c, name in CATEGORIES.items() if cat_counts.get(c))
    ssrn_chips = "".join(
        f'<button class="chip" data-act="chip" data-kind="cat" data-val="{short}" '
        f'aria-pressed="false" title="{_esc(name)}">{short} ({cat_counts.get(short, 0)})</button>'
        for short, name in SSRN_JOURNALS.values() if cat_counts.get(short))

    stats = (f'<div class="stat"><b>{len(entries)}</b>편</div>'
             f'<div class="stat"><b>{len(by_day)}</b>개 날짜</div>'
             + "".join(f'<div class="stat"><b>{src_counts.get(s, 0)}</b>{SRC_LABEL[s]}</div>'
                       for s in ("arxiv", "ssrn") if src_counts.get(s)))

    sections, idx = "", 0
    for day in sorted(by_day, reverse=True):
        cards = ""
        for entry in by_day[day]:
            cards += _card(entry, idx)
            idx += 1
        try:
            label = datetime.strptime(day, "%Y-%m-%d").strftime("%Y년 %m월 %d일 (%a)")
        except ValueError:
            label = day
        sections += (f'<section class="day"><h2 class="day"><span>{_esc(label)}</span>'
                     f' — {len(by_day[day])}편</h2><div class="list">{cards}</div></section>')

    day_line = " · ".join(sorted(by_day, reverse=True)) or "대상 없음"
    out = out_path or (REPORT_DIR / f"qfin-digest-{now:%Y%m%d}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>퀀트 논문 다이제스트 {now:%Y-%m-%d}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>퀀트 논문 다이제스트</h1>
  <p class="sub">대상 날짜 {_esc(day_line)} · 생성 {now:%Y-%m-%d %H:%M}<br>
     arXiv q-fin.PM/ST/TR · SSRN {len(SSRN_JOURNALS)}개 eJournal<br>
     ★ = 시스템 트레이딩 구현 가능성 (표준 데이터로 규칙을 코딩해 자동매매로 돌릴 수 있는가)</p>
  <div class="stats">{stats}</div>
</header>

<div class="controls">
  <div class="row"><span class="rowlabel">출처</span>{src_chips}
    <input id="q" type="search" placeholder="제목·요약·저자·키워드 검색">
    <select id="sort" title="★ = 시스템 트레이딩 구현 가능성">
      <option value="rel">★ 구현 가능성 순</option>
      <option value="orig">기본 순서</option>
    </select>
  </div>
  <div class="row"><span class="rowlabel">분야</span>{arxiv_chips}{ssrn_chips}
    <button class="chip" data-act="reset">필터 해제</button>
    <button class="chip" id="expandBtn" data-act="expand">전체 펼치기</button>
    <span class="count" id="count"></span>
    <span id="livebadge" hidden title="보고서 생성 버튼을 누르면 바로 만들어집니다">로컬 서버 연결됨</span>
  </div>
</div>

{sections}
<p class="empty" id="none" hidden>조건에 맞는 논문이 없습니다.</p>

<footer>
  <p>초록 출처: arXiv Atom API · SSRN abstract 페이지 · 요약: 로컬 Claude Code ·
     원문 저작권은 각 저자에게 있습니다.</p>
</footer>
</div>

<div class="bar" id="bar"><div class="bar-in">
  <strong><span id="qn">0</span>편</strong> 상세 리포트 요청 대기
  <code id="qcmd"></code>
  <button class="btn primary" data-act="copy">요청 목록 복사</button>
  <button class="btn" data-act="clear">비우기</button>
</div></div>

<script>{JS}</script>
</body>
</html>
""", encoding="utf-8")
    return out
