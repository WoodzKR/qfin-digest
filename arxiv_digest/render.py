"""Render ``seen.json`` into a single self-contained HTML digest.

The page carries both languages at once. Everything language-specific is tagged
``data-l="ko"`` / ``data-l="en"`` and CSS shows only the one matching
``<html data-lang>``, so switching is instant and needs no rebuild.
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import (ABS_URL, ALPHAARCH_LABEL, BLOG_LABELS, BLOG_SOURCES, CATEGORIES, LANGS,
                     MACROSYNERGY_LABEL, PAPER_DIR, PDF_URL, QUANTOCRACY_LABEL,
                     QUANTPEDIA_LABEL, REPORT_DIR, SOURCES, SSRN_ABS_URL, SSRN_JOURNALS,
                     SSRN_PDF_URL, ensure_dirs, report_name)
from .store import text as summary_text

CAT_SHORT = {"q-fin.PM": "PM", "q-fin.ST": "ST", "q-fin.TR": "TR"}
SSRN_SHORTS = {short: name for short, name in SSRN_JOURNALS.values()}
BLOG_SHORTS = dict(BLOG_LABELS)
SRC_LABEL = {"arxiv": "arXiv", "ssrn": "SSRN", "quantpedia": QUANTPEDIA_LABEL,
             "alphaarchitect": ALPHAARCH_LABEL,
             "macrosynergy": MACROSYNERGY_LABEL, "quantocracy": QUANTOCRACY_LABEL}
SRC_BADGE_CLASS = {"ssrn": "b-ssrn", "quantpedia": "b-qp",
                   "alphaarchitect": "b-aa", "macrosynergy": "b-ms",
                   "quantocracy": "b-qc"}
LANG_BUTTON = {"ko": "한국어", "en": "English"}


def abs_url(entry: dict) -> str:
    src = entry.get("src", "arxiv")
    if src == "ssrn":
        return entry.get("abs_url") or SSRN_ABS_URL.format(id=entry.get("ext_id", ""))
    if src in BLOG_SOURCES:
        return entry.get("abs_url", "")
    return ABS_URL.format(id=entry.get("ext_id") or entry.get("id", ""))


def pdf_url(entry: dict) -> str:
    """Empty string when the source has no PDF (blog posts)."""
    src = entry.get("src", "arxiv")
    if src == "ssrn":
        return entry.get("pdf_url") or SSRN_PDF_URL.format(id=entry.get("ext_id", ""))
    if src in BLOG_SOURCES:
        return entry.get("pdf_url", "")
    return PDF_URL.format(id=entry.get("ext_id") or entry.get("id", ""))


CSS = """
:root{
  --bg:#f6f7f9; --panel:#ffffff; --panel-2:#fbfcfd; --ink:#16191d; --muted:#5c6672;
  --line:#e2e6ea; --accent:#3b6ef0; --accent-soft:#eaf0fe;
  --pm:#3b6ef0; --st:#0f9d76; --tr:#d4791f; --ssrn:#8b5cf6; --other:#7a68c9;
  --qp:#c0392b; --man:#0f766e; --aa:#1d4ed8; --ms:#a16207; --qc:#6d28d9;
  --star:#f0a91b; --shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#101317; --panel:#181c22; --panel-2:#1e232a; --ink:#e7ebf0; --muted:#98a3b0;
    --line:#2a3038; --accent:#7ea3ff; --accent-soft:#1d2637;
    --pm:#7ea3ff; --st:#4bd6a8; --tr:#f0ad5e; --ssrn:#b18cff; --other:#b0a0f0;
    --qp:#f08a7c; --man:#3fc4b4; --aa:#8fb2ff; --ms:#e3b341; --qc:#c4a6ff;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 14px rgba(0,0,0,.25);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,"Segoe UI","Malgun Gothic",Roboto,"Helvetica Neue",sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:32px 20px 140px}
a{color:var(--accent)}

/* language switching: only the active language is displayed */
[data-l]{display:none}
html[data-lang="ko"] [data-l="ko"]{display:revert}
html[data-lang="en"] [data-l="en"]{display:revert}

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
.rowlabel{font-size:11.5px;color:var(--muted);font-weight:700;letter-spacing:.06em;min-width:38px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--muted);
  border-radius:999px;padding:5px 12px;font-size:12.5px;cursor:pointer;
  font-family:inherit;transition:.12s;white-space:nowrap}
.chip[aria-pressed="true"]{background:var(--accent-soft);border-color:var(--accent);
  color:var(--accent);font-weight:600}
.chip:hover{border-color:var(--accent)}
.langsel{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.langsel button{border:0;background:var(--panel);color:var(--muted);padding:5px 13px;
  font:inherit;font-size:12.5px;cursor:pointer;transition:.12s}
.langsel button[aria-pressed="true"]{background:var(--accent);color:#fff;font-weight:700}
#q{flex:1;min-width:180px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink);font:inherit;font-size:13.5px}
#q:focus{outline:2px solid var(--accent);outline-offset:-1px}
select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink);font:inherit;font-size:13.5px}
.count{color:var(--muted);font-size:12.5px;margin-left:auto}

h2.day{font-size:15px;margin:30px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line);
  color:var(--muted);font-weight:600;letter-spacing:.02em}
h2.day span.d{color:var(--ink)}

.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow)}
.card.hide{display:none}
.badges{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:2.5px 8px;
  border-radius:5px;color:#fff}
.b-PM{background:var(--pm)} .b-ST{background:var(--st)} .b-TR{background:var(--tr)}
.b-ssrn{background:var(--ssrn)} .b-qp{background:var(--qp)} .b-man{background:var(--man)}
.b-aa{background:var(--aa)} .b-ms{background:var(--ms)} .b-qc{background:var(--qc)}
.b-XX{background:var(--other)}
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
.kv{display:grid;grid-template-columns:92px 1fr;gap:5px 10px;font-size:13.5px;margin-bottom:12px}
.kv dt{color:var(--muted);font-weight:600}
.kv dd{margin:0}
.keys{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
.key{font-size:11.5px;background:var(--panel-2);border:1px solid var(--line);
  border-radius:5px;padding:2px 7px;color:var(--muted)}
.abs{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
  padding:11px 13px;font-size:13px;color:var(--muted);line-height:1.7}
.abs b{color:var(--ink);display:block;margin-bottom:4px;font-size:12px;letter-spacing:.03em}

.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;align-items:center}
.actions .sep{width:1px;height:18px;background:var(--line);margin:0 2px}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--muted);
  border-radius:7px;padding:5.5px 12px;font-size:12.5px;cursor:pointer;
  font-family:inherit;text-decoration:none;display:inline-block;transition:.12s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}
.btn.queued{background:var(--accent-soft);border-color:var(--accent);color:var(--accent);
  font-weight:600}
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
.bar pre{background:var(--panel-2);border:1px solid var(--line);border-radius:6px;
  padding:6px 9px;font-size:12px;flex:1;min-width:200px;overflow:auto;margin:0;
  white-space:pre;line-height:1.5}
.empty{color:var(--muted);text-align:center;padding:50px 0}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
@media print{.controls,.bar,.actions{display:none!important}.detail{display:block!important}
  .card{break-inside:avoid;box-shadow:none}}
"""

JS = r"""
const LKEY='qfin-digest-lang', QKEY='qfin-digest-queue';
const I18N={
  ko:{search:'제목·요약·저자·키워드 검색',rel:'★ 구현 가능성 순',orig:'기본 순서',
      expand:'전체 펼치기',collapse:'전체 접기',shown:'편 표시',more:'▾ 자세히',
      less:'▴ 접기',copy:'요청 목록 복사',copied:'✓ 복사됨',
      queuedFor:'편 대기 중',waiting:'대기 중',failed:'⚠ 실패 — 다시 시도'},
  en:{search:'Search title, summary, author, keyword',rel:'★ Implementability',orig:'Listed order',
      expand:'Expand all',collapse:'Collapse all',shown:'shown',more:'▾ Details',
      less:'▴ Hide',copy:'Copy commands',copied:'✓ Copied',
      queuedFor:'queued',waiting:'queued',failed:'⚠ Failed — retry'}};
let LANG=(()=>{try{return localStorage.getItem(LKEY)||'ko'}catch(e){return 'ko'}})();
const T=k=>I18N[LANG][k];

function applyLang(){
  document.documentElement.setAttribute('data-lang',LANG);
  document.documentElement.setAttribute('lang',LANG);
  try{localStorage.setItem(LKEY,LANG)}catch(e){}
  document.querySelectorAll('.langsel button').forEach(b=>
    b.setAttribute('aria-pressed',String(b.dataset.val===LANG)));
  document.getElementById('q').placeholder=T('search');
  const s=document.getElementById('sort');
  s.options[0].textContent=T('rel'); s.options[1].textContent=T('orig');
  document.querySelectorAll('[data-act="toggle"]').forEach(b=>{
    b.textContent=b.closest('.card').querySelector('.detail').hidden?T('more'):T('less');});
  document.querySelector('[data-act="copy"]').textContent=T('copy');
  syncExpandLabel(); filter(); paint();
}

const loadQ=()=>{try{return JSON.parse(localStorage.getItem(QKEY)||'[]')}catch(e){return []}};
const saveQ=v=>{try{localStorage.setItem(QKEY,JSON.stringify(v))}catch(e){}};

let LIVE=false;
async function detectLive(){
  try{const r=await fetch('/api/ping',{cache:'no-store'});LIVE=r.ok;}catch(e){LIVE=false;}
  document.getElementById('livebadge').hidden=!LIVE;
  paint();
}

function paint(){
  const q=LIVE?[]:loadQ();
  document.querySelectorAll('.js-req').forEach(b=>{
    if(b.dataset.busy)return;
    const on=q.includes(b.dataset.id+'|'+b.dataset.lang);
    b.classList.toggle('queued',on);
    b.textContent=(on?'✓ ':'📄 ')+b.dataset.label;
  });
  document.getElementById('bar').classList.toggle('on',q.length>0);
  document.getElementById('qn').textContent=q.length;
  const byLang={};
  q.forEach(item=>{const [id,lang]=item.split('|');(byLang[lang]=byLang[lang]||[]).push(id);});
  document.getElementById('qcmd').textContent=
    Object.entries(byLang).map(([l,ids])=>'python run.py paper --lang '+l+' '+ids.join(' '))
      .join('\n');
}
function toggleReq(id,lang){
  const key=id+'|'+lang, q=loadQ(), i=q.indexOf(key);
  if(i<0)q.push(key); else q.splice(i,1);
  saveQ(q); paint();
}

function linkify(btn,url){
  const a=document.createElement('a');
  a.className='btn done'; a.href=url; a.target='_blank'; a.rel='noopener';
  a.textContent='📄 '+btn.dataset.label;
  btn.replaceWith(a);
  return a;
}

// A report built in another tab, or in an earlier session, should appear here
// without rebuilding the page. Cheap, so re-run it whenever the window is focused.
async function syncReports(){
  if(!LIVE)return;
  let names=[];
  try{names=(await (await fetch('/api/reports',{cache:'no-store'})).json()).reports||[];}
  catch(e){return;}
  const have=new Set(names);
  document.querySelectorAll('.js-req').forEach(b=>{
    if(b.dataset.busy)return;
    const file=b.dataset.id+'.'+b.dataset.lang+'.html';
    if(have.has(file))linkify(b,'/report/paper/'+file);
  });
}

async function genReport(btn){
  if(btn.dataset.busy)return;
  const id=btn.dataset.id, lang=btn.dataset.lang;
  btn.dataset.busy='1'; btn.classList.add('queued');
  btn.textContent='⏳ '+T('waiting')+'…';
  const fail=msg=>{btn.classList.remove('queued');btn.classList.add('failed');
    btn.textContent=T('failed');btn.title=msg||'';delete btn.dataset.busy;};
  try{
    const r=await fetch('/api/report',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({id,lang})});
    if(!r.ok)return fail('request rejected ('+r.status+')');
    for(;;){
      await new Promise(res=>setTimeout(res,2000));
      const s=await (await fetch('/api/status?id='+encodeURIComponent(id)+'&lang='+lang,
        {cache:'no-store'})).json();
      if(s.state==='done'){ linkify(btn,s.url).click(); return; }
      if(s.state==='error')return fail(s.error);
      if(s.note)btn.textContent='⏳ '+s.note+'…';
    }
  }catch(e){fail(String(e));}
}

const cards=[...document.querySelectorAll('.card')];
const pressed=sel=>[...document.querySelectorAll(sel)]
  .filter(c=>c.getAttribute('aria-pressed')==='true').map(c=>c.dataset.val);
const visible=()=>[...document.querySelectorAll('.card:not(.hide)')];
const anyCollapsed=()=>visible().some(c=>c.querySelector('.detail').hidden);
function syncExpandLabel(){
  document.getElementById('expandBtn').textContent=anyCollapsed()?T('expand'):T('collapse');
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
    s.style.display=s.querySelectorAll('.card:not(.hide)').length?'':'none';});
  document.getElementById('count').textContent=n+' / '+cards.length+' '+T('shown');
  document.getElementById('none').hidden=n>0;
  syncExpandLabel();
}
function sortBy(mode){
  document.querySelectorAll('section.day .list').forEach(list=>{
    [...list.children].sort((a,b)=>mode==='rel'
      ? (+b.dataset.rel)-(+a.dataset.rel)||a.dataset.title.localeCompare(b.dataset.title)
      : (+a.dataset.idx)-(+b.dataset.idx)).forEach(el=>list.appendChild(el));
  });
}

document.addEventListener('click',e=>{
  const t=e.target.closest('[data-act]');
  if(!t)return;
  const act=t.dataset.act;
  if(act==='lang'){LANG=t.dataset.val;applyLang();}
  else if(act==='req'){ if(LIVE)genReport(t); else toggleReq(t.dataset.id,t.dataset.lang); }
  else if(act==='toggle'){
    const d=t.closest('.card').querySelector('.detail');
    d.hidden=!d.hidden; t.textContent=d.hidden?T('more'):T('less'); syncExpandLabel();
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
    navigator.clipboard.writeText(document.getElementById('qcmd').textContent)
      .then(()=>{t.textContent=T('copied');setTimeout(()=>t.textContent=T('copy'),1400);});
  }
  else if(act==='clear'){saveQ([]);paint();}
  else if(act==='expand'){
    const open=anyCollapsed();
    visible().forEach(c=>{
      c.querySelector('.detail').hidden=!open;
      const b=c.querySelector('[data-act="toggle"]');
      if(b)b.textContent=open?T('less'):T('more');
    });
    syncExpandLabel();
  }
});
document.getElementById('q').addEventListener('input',filter);
document.getElementById('sort').addEventListener('change',e=>sortBy(e.target.value));
applyLang();
detectLive().then(syncReports);
window.addEventListener('focus',syncReports);
"""


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _stars(n: int) -> str:
    n = max(1, min(5, int(n or 3)))
    return "★" * n + f"<i>{'★' * (5 - n)}</i>"


def _badge(cat: str, src: str) -> str:
    cls = SRC_BADGE_CLASS.get(src)
    if cls:
        title = SSRN_SHORTS.get(cat) or BLOG_SHORTS.get(cat) or cat
        return f'<span class="badge {cls}" title="{_esc(title)}">{_esc(cat)}</span>'
    short = CAT_SHORT.get(cat)
    if short:
        return f'<span class="badge b-{short}">{short}</span>'
    return f'<span class="badge ghost">{_esc(cat)}</span>'


DETAIL_LABELS = {
    "ko": {"method": "방법", "data": "데이터", "takeaway": "시사점", "why": "적용도"},
    "en": {"method": "Method", "data": "Data", "takeaway": "Use", "why": "Score"},
}


def _detail_block(entry: dict, lang: str, rel: int) -> str:
    body = summary_text(entry, lang)
    labels = DETAIL_LABELS[lang]
    bullets = "".join(f"<li>{_esc(b)}</li>" for b in (body.get("bullets") or []))
    kv = "".join(
        f"<dt>{labels[key]}{f' {rel}/5' if key == 'why' else ''}</dt><dd>{_esc(value)}</dd>"
        for key, value in (("method", body.get("method")), ("data", body.get("data")),
                           ("takeaway", body.get("takeaway")),
                           ("why", body.get("relevance_why"))) if value)
    return (f'<div data-l="{lang}">'
            f'{f"<ul>{bullets}</ul>" if bullets else ""}'
            f'{f"<dl class=\'kv\'>{kv}</dl>" if kv else ""}'
            f'</div>')


def _card(entry: dict, idx: int) -> str:
    pid = entry["id"]
    src = entry.get("src", "arxiv")
    summary = entry.get("summary") or {}
    src_cats = entry.get("src_cats") or []
    rel = int(summary.get("relevance", 3) or 3)
    authors = entry.get("authors") or []
    author_line = ", ".join(authors[:5]) + (f" +{len(authors) - 5}" if len(authors) > 5 else "")
    if src == "ssrn" and entry.get("affiliations"):
        author_line += f" · {entry['affiliations']}"

    searchable = " ".join(
        [entry.get("title", ""), entry.get("abstract", "")]
        + [v for lang in LANGS for k, v in summary_text(entry, lang).items()
           if isinstance(v, str) and k != "bullets"]
        + list(summary.get("keywords") or []) + authors + list(entry.get("journals") or [])
    ).lower()

    badges = (f'<span class="badge ghost">{SRC_LABEL.get(src, src)}</span>'
              + "".join(_badge(c, src) for c in src_cats))
    if src == "arxiv":
        extra = [c for c in (entry.get("categories") or [])
                 if c not in src_cats and c not in CATEGORIES][:2]
        badges += "".join(f'<span class="badge ghost">{_esc(c)}</span>' for c in extra)
        if entry.get("cross_from"):
            badges += '<span class="badge ghost">cross-list</span>'
    elif src == "ssrn" and entry.get("page_count"):
        badges += f'<span class="badge ghost">{entry["page_count"]}p</span>'
    elif src in BLOG_SOURCES:
        badges += "".join(f'<span class="badge ghost">{_esc(c)}</span>'
                          for c in (entry.get("categories") or [])[:2])

    one_liners = "".join(
        f'<p class="oneliner" data-l="{lang}">{_esc(summary_text(entry, lang).get("one_liner", ""))}</p>'
        for lang in LANGS)
    details = "".join(_detail_block(entry, lang, rel) for lang in LANGS)
    keys = "".join(f'<span class="key">{_esc(k)}</span>' for k in (summary.get("keywords") or []))

    report_btns = ""
    for lang in LANGS:
        label = LANG_BUTTON[lang]
        if (PAPER_DIR / report_name(pid, lang)).exists():
            report_btns += (f'<a class="btn done" href="paper/{_esc(report_name(pid, lang))}"'
                            f' target="_blank" rel="noopener">📄 {label}</a>')
        else:
            report_btns += (f'<button class="btn js-req" data-act="req" data-id="{_esc(pid)}"'
                            f' data-lang="{lang}" data-label="{label}">📄 {label}</button>')

    return f"""
<article class="card" data-src="{_esc(src)}" data-cats="{_esc('|'.join(src_cats))}"
         data-rel="{rel}" data-idx="{idx}" data-title="{_esc(entry.get('title', ''))}"
         data-text="{_esc(searchable)}">
  <div class="badges">{badges}
    <span class="badge ghost">{_esc(entry.get('ext_id', pid))}</span>
    <span class="stars" title="systematic-trading implementability {rel}/5">{_stars(rel)}</span>
  </div>
  <h3 class="title"><a href="{_esc(abs_url(entry))}" target="_blank"
      rel="noopener">{_esc(entry.get('title', pid))}</a></h3>
  {one_liners}
  <p class="authors">{_esc(author_line)}</p>
  <div class="detail" hidden>
    {details}
    {f'<div class="keys">{keys}</div>' if keys else ''}
    <div class="abs"><b>ORIGINAL ABSTRACT</b>{_esc(entry.get('abstract', ''))}</div>
  </div>
  <div class="actions">
    <button class="btn" data-act="toggle">▾</button>
    <a class="btn" href="{_esc(abs_url(entry))}" target="_blank" rel="noopener">{
      'source' if src in BLOG_SOURCES else 'abs'}</a>
    {f'<a class="btn" href="{_esc(pdf_url(entry))}" target="_blank" rel="noopener">PDF</a>'
     if pdf_url(entry) else ''}
    <span class="sep"></span>{report_btns}
  </div>
</article>"""


def _bi(ko: str, en: str) -> str:
    """Inline pair of language spans."""
    return f'<span data-l="ko">{ko}</span><span data-l="en">{en}</span>'


LANG_SELECTOR = ('<div class="langsel">'
                 '<button data-act="lang" data-val="ko" aria-pressed="true">한국어</button>'
                 '<button data-act="lang" data-val="en" aria-pressed="false">English</button>'
                 '</div>')


def build_index(seen: dict[str, dict] | None = None) -> Path:
    """Repository-root index.html — the GitHub Pages entry point."""
    from .config import ROOT

    ensure_dirs()
    digests = sorted(REPORT_DIR.glob("qfin-digest-*.html"), reverse=True)
    papers = sorted(PAPER_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    titles = {e["id"]: e.get("title", e["id"]) for e in (seen or {}).values()}
    now = datetime.now()

    rows = ""
    for i, path in enumerate(digests):
        stamp = path.stem.replace("qfin-digest-", "")
        try:
            day = datetime.strptime(stamp, "%Y%m%d")
            label = _bi(day.strftime("%Y년 %m월 %d일 다이제스트"), day.strftime("%d %b %Y digest"))
        except ValueError:
            label = _esc(stamp)
        tag = f' <span class="badge b-ssrn">{_bi("최신", "latest")}</span>' if i == 0 else ""
        rows += f'<li><a href="report/{path.name}">{label}</a>{tag}</li>'

    plist = ""
    for path in papers:
        pid, _, lang = path.stem.rpartition(".")
        if lang not in LANGS:
            pid, lang = path.stem, "ko"
        plist += (f'<li><a href="report/paper/{path.name}">{_esc(titles.get(pid, pid))}</a>'
                  f' <span class="key">{LANG_BUTTON.get(lang, lang)}</span></li>')

    out = ROOT / "index.html"
    out.write_text(f"""<!doctype html>
<html lang="ko" data-lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quant Paper Digest</title>
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
    <h1>{_bi("퀀트 논문 다이제스트", "Quant Paper Digest")}</h1>
    <p class="sub">arXiv q-fin.PM/ST/TR · SSRN {len(SSRN_JOURNALS)} eJournals ·
       {_bi(f"블로그 {len(BLOG_LABELS)}곳", f"{len(BLOG_LABELS)} blogs")} ·
       {_bi("갱신", "updated")} {now:%Y-%m-%d %H:%M}</p>
    <div class="stats">
      <div class="stat"><b>{len(digests)}</b>{_bi("개 다이제스트", " digests")}</div>
      <div class="stat"><b>{len(papers)}</b>{_bi("편 상세 리포트", " deep reports")}</div>
    </div>
    <div class="row" style="margin-top:14px">{LANG_SELECTOR}</div>
  </header>

  <h2 class="sec">{_bi("날짜별 다이제스트", "Daily digests")}</h2>
  <ul class="idx">{rows or f'<li>{_bi("아직 없습니다.", "Nothing yet.")}</li>'}</ul>

  <h2 class="sec">{_bi("상세 리포트", "Deep reports")}</h2>
  <ul class="idx">{plist or f'<li>{_bi("아직 없습니다.", "Nothing yet.")}</li>'}</ul>

  <footer><p>{_bi("로컬 Claude Code 로 생성한 요약입니다. 원문 저작권은 각 저자에게 있습니다.",
                  "Summaries generated locally with Claude Code. Papers remain their authors’ copyright.")}</p></footer>
</div>
<script>
(function(){{
  const K='qfin-digest-lang';
  let l='ko'; try{{l=localStorage.getItem(K)||'ko'}}catch(e){{}}
  const set=v=>{{l=v;document.documentElement.setAttribute('data-lang',v);
    document.documentElement.setAttribute('lang',v);
    try{{localStorage.setItem(K,v)}}catch(e){{}}
    document.querySelectorAll('.langsel button').forEach(b=>
      b.setAttribute('aria-pressed',String(b.dataset.val===v)));}};
  document.addEventListener('click',e=>{{
    const t=e.target.closest('[data-act="lang"]'); if(t)set(t.dataset.val);}});
  set(l);
}})();
</script>
</body>
</html>
""", encoding="utf-8")
    return out


def build(seen: dict[str, dict], days: list[str] | None = None,
          sources: list[str] | None = None, out_path: Path | None = None) -> Path:
    """Render every summarized paper into one digest page."""
    ensure_dirs()
    entries = [e for e in seen.values()
               if any((e.get("summary") or {}).get(lang, {}).get("one_liner") for lang in LANGS)]
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
        for s in SOURCES if src_counts.get(s))
    cat_chips = "".join(
        f'<button class="chip" data-act="chip" data-kind="cat" data-val="{c}" '
        f'aria-pressed="false" title="{_esc(name)}">{CAT_SHORT[c]} ({cat_counts.get(c, 0)})</button>'
        for c, name in CATEGORIES.items() if cat_counts.get(c))
    cat_chips += "".join(
        f'<button class="chip" data-act="chip" data-kind="cat" data-val="{short}" '
        f'aria-pressed="false" title="{_esc(name)}">{short} ({cat_counts.get(short, 0)})</button>'
        for short, name in list(SSRN_JOURNALS.values()) + list(BLOG_SHORTS.items())
        if cat_counts.get(short))

    stats = (f'<div class="stat"><b>{len(entries)}</b>{_bi("건", " items")}</div>'
             f'<div class="stat"><b>{len(by_day)}</b>{_bi("개 날짜", " dates")}</div>'
             + "".join(f'<div class="stat"><b>{src_counts.get(s, 0)}</b>{SRC_LABEL[s]}</div>'
                       for s in SOURCES if src_counts.get(s)))

    sections, idx = "", 0
    for day in sorted(by_day, reverse=True):
        cards = ""
        for entry in by_day[day]:
            cards += _card(entry, idx)
            idx += 1
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d")
            label = _bi(parsed.strftime("%Y년 %m월 %d일"), parsed.strftime("%A, %d %b %Y"))
        except ValueError:
            label = _esc(day)
        sections += (f'<section class="day"><h2 class="day"><span class="d">{label}</span>'
                     f' — {len(by_day[day])}{_bi("편", "")}</h2>'
                     f'<div class="list">{cards}</div></section>')

    # A range, not a list: the store spans many dates and enumerating them all
    # made the header unreadable.
    ordered_days = sorted(by_day)
    if not ordered_days:
        day_line = "-"
    elif len(ordered_days) == 1:
        day_line = ordered_days[0]
    else:
        day_line = f"{ordered_days[0]} ~ {ordered_days[-1]}"
    out = out_path or (REPORT_DIR / f"qfin-digest-{now:%Y%m%d}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""<!doctype html>
<html lang="ko" data-lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quant Paper Digest {now:%Y-%m-%d}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>{_bi("퀀트 논문 다이제스트", "Quant Paper Digest")}</h1>
  <p class="sub">{_bi("대상 날짜", "Dates")} {_esc(day_line)} ·
     {_bi("생성", "built")} {now:%Y-%m-%d %H:%M}<br>
     arXiv q-fin.PM/ST/TR · SSRN {len(SSRN_JOURNALS)} eJournals ·
     {_bi(f"블로그 {len(BLOG_LABELS)}곳", f"{len(BLOG_LABELS)} blogs")}<br>
     {_bi("★ = 시스템 트레이딩 구현 가능성 (표준 데이터로 규칙을 코딩해 자동매매로 돌릴 수 있는가)",
          "★ = systematic-trading implementability (can it be coded into rules on standard data?)")}</p>
  <div class="stats">{stats}</div>
</header>

<div class="controls">
  <div class="row">{LANG_SELECTOR}
    <span class="rowlabel">{_bi("출처", "Source")}</span>{src_chips}
    <input id="q" type="search">
    <select id="sort"><option value="rel"></option><option value="orig"></option></select>
  </div>
  <div class="row"><span class="rowlabel">{_bi("분야", "Field")}</span>{cat_chips}
    <button class="chip" data-act="reset">{_bi("필터 해제", "Clear")}</button>
    <button class="chip" id="expandBtn" data-act="expand"></button>
    <span class="count" id="count"></span>
    <span id="livebadge" hidden>{_bi("로컬 서버 연결됨", "local server connected")}</span>
  </div>
</div>

{sections}
<p class="empty" id="none" hidden>{_bi("조건에 맞는 논문이 없습니다.", "No papers match.")}</p>

<footer>
  <p>{_bi("초록 출처: arXiv Atom API · SSRN abstract 페이지 · 요약: 로컬 Claude Code",
          "Abstracts: arXiv Atom API and SSRN abstract pages. Summaries generated locally with Claude Code.")}
     {_bi("원문 저작권은 각 저자에게 있습니다.", "Papers remain their authors’ copyright.")}</p>
</footer>
</div>

<div class="bar" id="bar"><div class="bar-in">
  <strong><span id="qn">0</span></strong>
  {_bi("편 상세 리포트 요청 대기", "deep reports queued")}
  <pre id="qcmd"></pre>
  <button class="btn primary" data-act="copy"></button>
  <button class="btn" data-act="clear">{_bi("비우기", "Clear")}</button>
</div></div>

<script>{JS}</script>
</body>
</html>
""", encoding="utf-8")
    return out
