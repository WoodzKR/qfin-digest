# 퀀트 논문 Digest — 설계 문서

작성일: 2026-08-31 · v0.2 (SSRN 7개 eJournal 추가)

> v0.2 변경 요약은 문서 맨 아래 [§10](#10-v02--ssrn-추가와-리포트-개선) 참고.

## 1. 목표

arXiv의 계량금융 3개 카테고리 최신 목록에서 **가장 최근 2개 날짜**에 올라온 논문을
전부 수집 → 초록을 로컬 Claude로 한국어 요약 → **이미 요약한 논문은 건너뜀** →
HTML 리포트로 발행한다.

대상 목록 페이지:

| 카테고리 | 의미 | URL |
|---|---|---|
| `q-fin.PM` | Portfolio Management | https://arxiv.org/list/q-fin.PM/recent |
| `q-fin.ST` | Statistical Finance | https://arxiv.org/list/q-fin.ST/recent |
| `q-fin.TR` | Trading & Market Microstructure | https://arxiv.org/list/q-fin.TR/recent |

## 2. 전체 파이프라인

```
[1] fetch      list/recent 3개 페이지 크롤 → #articles > h3 날짜 파싱
                → 최근 2개 날짜 그룹의 arXiv ID 전부 수집
                     ↓
[2] enrich     arXiv API(id_list, 100건/요청)로 제목·저자·초록·카테고리 확보
                     ↓
[3] dedup      state/seen.json 과 대조 → 이미 요약된 ID 제거
                     ↓
[4] summarize  남은 논문만 → 로컬 Claude 요약 → state/seen.json 에 누적 저장
                     ↓
[5] report     seen.json → report/arxiv-qfin-YYYYMMDD.html 생성
```

각 단계는 독립 실행 가능(중간에 끊겨도 재개 가능)하도록 파일 기반으로 연결한다.

## 3. 크롤링 상세

### 3.1 날짜 파싱

- 요청 URL: `https://arxiv.org/list/{cat}/recent?skip=0&show=2000`
  (`show=2000`으로 한 번에 전체를 받아 페이지네이션 제거)
- `<dl id="articles">` 안의 `<h3>` 텍스트 예: `Thu, 28 Aug 2025 (showing 34 of 34 entries)`
  - 정규식 `^\w{3}, (\d{1,2} \w{3} \d{4})` 로 날짜 추출 → `date(2025, 8, 28)`
- h3 이후 다음 h3 전까지의 `<dt>` 블록이 그 날짜에 속하는 논문들
- **3개 카테고리 각각에서 최근 2개 날짜**를 취하고, 날짜 합집합의 상위 2개를 최종 대상으로 삼는다
  (카테고리마다 갱신일이 어긋날 수 있으므로)

### 3.2 ID 추출

- `<dt>` 안의 `<a href="/abs/2608.28399">arXiv:2608.28399</a>` 에서 ID 추출
- 버전 접미사(`v2`)는 제거하고 **base ID**를 dedup 키로 사용
- 카테고리 간 중복(cross-list) 논문은 한 번만 처리하되, 노출 카테고리는 리스트로 보관

### 3.3 초록 확보

HTML의 접힌 초록을 파싱하지 않고 **arXiv Atom API**를 쓴다.

```
GET https://export.arxiv.org/api/query?id_list=2608.28399,2608.28400,...&max_results=100
```

- 이유: 목록 HTML은 초록이 잘려 있거나(`△ More`) 마크업이 자주 바뀌지만, API는 안정적이고
  제목·저자·초록·주/부 카테고리·게시일·개정일을 한 번에 준다. 외부 의존성도 `requests` 하나면 끝.
- 예의: 요청 간 3초 sleep, `User-Agent`에 연락 수단 명시, 100건/요청 배치.
- API 실패 시 `/abs/{id}` 페이지의 `<blockquote class="abstract">` 파싱으로 폴백.

## 4. 상태 저장 (중복 방지)

`state/seen.json` — 단일 파일, ID를 키로 하는 사전.

```json
{
  "2608.28399": {
    "id": "2608.28399",
    "title": "...",
    "authors": ["...", "..."],
    "categories": ["q-fin.PM", "q-fin.ST"],
    "primary": "q-fin.PM",
    "listed_date": "2026-08-28",
    "abstract": "...",
    "summary": {
      "one_liner": "한 줄 요약",
      "bullets": ["...", "...", "..."],
      "method": "...",
      "data": "...",
      "takeaway": "실무 시사점",
      "keywords": ["portfolio", "transformer"],
      "relevance": 4
    },
    "summarized_at": "2026-08-31T09:12:00+09:00",
    "report_requested": false
  }
}
```

- `summary`가 있으면 **이미 요약 완료** → 다음 실행에서 건너뜀
- 파일 쓰기는 임시파일 → `os.replace` 원자적 교체 (중단되어도 손상 없음)
- 백업: `state/seen.json.bak` 1세대 유지

## 5. 요약 (로컬 Claude 연결)

`claude` 실행 파일이 PATH에 없으므로 **하프-오토 방식**을 기본으로 한다.

1. `fetch.py` 가 미요약 논문만 모아 `state/pending.json` 으로 떨궈 준다
2. 이 VSCode 세션에서 Claude가 `pending.json`을 읽고 요약 → `state/summaries_in.json` 으로 기록
3. `ingest.py` 가 그 결과를 `seen.json`에 병합하고 `pending.json`을 비운다

즉 사용자 입장에서는 명령 2번(`python run.py fetch` → "요약해줘") + 리포트 생성 1번.

> `npm i -g @anthropic-ai/claude-code` 로 CLI를 깔면 `claude -p`로 2번 단계까지
> 완전 자동화 가능. 스크립트는 CLI가 있으면 자동으로 그 경로를 타도록 분기해 둔다.

### 요약 포맷 (한국어)

- `one_liner`: 1문장, 40자 내외
- `bullets`: 3~4개. 문제의식 / 방법론 / 핵심 결과
- `method`, `data`: 각 1문장 (모델·데이터셋·검증구간)
- `takeaway`: 퀀트/포트폴리오 실무 관점 시사점 1문장
- `keywords`: 3~6개 영문 키워드
- `relevance`: 1~5, **시스템 트레이딩 구현 가능성** (§11 기준)
- `relevance_why`: 그 점수를 준 이유 한 문장 (데이터 확보 난이도를 반드시 언급)

## 6. HTML 리포트

`report/arxiv-qfin-YYYYMMDD.html` — 단일 파일, 외부 의존 없음(CSS/JS 인라인).

레이아웃:

- 상단 헤더: 생성 시각, 대상 날짜 2개, 카테고리별 논문 수
- 필터 바: 카테고리 토글(PM/ST/TR), 키워드 검색, relevance 정렬
- 논문 카드 (날짜 → 카테고리 순 그룹핑)
  - 제목(영문) / 한 줄 요약(국문) / 저자 / 카테고리 배지 / relevance 별점
  - 접기·펼치기: 상세 요약 + 원문 초록
  - 버튼 3종:
    - `abs` → `https://arxiv.org/abs/{id}` 새 탭
    - `PDF` → `https://arxiv.org/pdf/{id}` 새 탭
    - `📄 보고서 생성` → 해당 논문 상세 리포트 요청 (§6.1)
- 다크/라이트 자동 대응, 모바일 폭 대응

### 6.1 "보고서 생성" 버튼 동작

HTML은 정적 파일이라 스스로 Claude를 호출할 수 없다. 그래서:

- 버튼 클릭 → 해당 ID가 브라우저 `localStorage`에 큐로 쌓이고 화면 상단에 배지 표시
- 하단 "요청 목록 복사" 버튼 → `2608.28399, 2608.28401` 형태로 클립보드 복사
- 사용자가 그대로 Claude에 붙여넣으면 → 원문(abs/PDF 본문)까지 읽고
  `report/paper/{id}.html` 상세 리포트 생성

## 7. 디렉터리 구조

```
C:\Users\260165\arxiv-qfin-digest\
├── DESIGN.md
├── run.py                # CLI 엔트리 (fetch / ingest / report / all)
├── arxiv_digest/
│   ├── listing.py        # 목록 크롤 + 날짜 파싱
│   ├── api.py            # arXiv Atom API
│   ├── store.py          # seen.json 입출력
│   ├── prompt.py         # 요약 프롬프트 / 스키마
│   └── render.py         # HTML 생성
├── state/
│   ├── seen.json
│   ├── pending.json
│   └── summaries_in.json
└── report/
    ├── arxiv-qfin-20260831.html
    └── paper/
```

## 8. 사용법 (예정)

```powershell
python run.py fetch      # 크롤 → 미요약 논문 pending.json 생성
# → Claude에게 "pending 요약해줘"
python run.py ingest     # 요약 병합
python run.py report     # HTML 생성 후 브라우저 열기

python run.py all        # CLI가 설치돼 있으면 위 3단계 한 번에
```

## 9. 확정된 결정 (2026-08-31)

| 항목 | 결정 |
|---|---|
| 요약 실행 | **claude CLI 완전 자동** — `@anthropic-ai/claude-code` 2.1.251 설치 완료. `claude -p --output-format json` 을 스레드 3~4개로 병렬 호출 |
| 보고서 버튼 | **상세 리포트 요청 큐** — localStorage 에 쌓고 `python run.py paper <ids>` 명령을 클립보드로 복사. abs/PDF 링크 버튼도 함께 |
| 요약 상세도 | **풀 스키마** (§5) |
| 실행 주기 | **수동 실행** |

### 구현하며 확정된 사항

- **§3.1 수정** — "최근 2개 날짜"는 *논문이 실제로 있는* 날짜 기준. arXiv 는 휴일·주말에
  `No updates for this time period.` 로 빈 날짜 헤더를 내보내므로 이를 건너뛴다.
- **전역이 아닌 카테고리별 상위 2일** — 실측 결과 q-fin.PM 은 08-26/08-25,
  q-fin.ST·TR 은 08-31/08-28 로 갱신일이 어긋났다. 전역 상위 2일을 쓰면 PM 이 통째로 빠진다.
- **HTML 파싱 주의점** — 목록 페이지는 `href ="/abs/ID"` 처럼 `=` 앞에 공백이 있다.
  또 `<dl id='articles'>` 블록이 날짜마다 하나씩 **반복**된다(문서 전체에 하나가 아님).
- **SSL** — stdlib `urllib` 은 사내 인증서 체인 때문에 실패한다. `requests`(certifi)를 쓴다.
- **하프오토 경로 제거** — CLI 자동화로 확정되어 `pending.json` 중계 단계는 만들지 않았다.
  미요약 판정은 `seen.json` 의 `summary` 유무로 직접 한다.
- **Windows subprocess** — `claude` 는 `.CMD` 래퍼라 `cmd /c` 를 거쳐 호출한다.
- **상세 리포트 본문** — `https://arxiv.org/html/{id}v1` 전문(최대 90k자)을 우선 사용하고,
  없으면 초록만으로 생성하되 그 사실을 리포트에 명시하도록 프롬프트에 규정.

---

## 10. v0.2 — SSRN 추가와 리포트 개선

### 10.1 SSRN 대상 저널 7종

| journal_id | 배지 | 저널 |
|---|---|---|
| 4058861 | QM | Quantitative Methods in Investing & Financial Statement Analysis |
| 4058853 | TI | Technology & Investing |
| 4058857 | GIS | Global Investment Strategy |
| 4058865 | GEX | Global Equities, Exchanges & Investment Indices |
| 1508951 | APV | Capital Markets: Asset Pricing & Valuation |
| 1504403 | MEF | Capital Markets: Market Efficiency |
| 1504404 | MMS | Capital Markets: Market Microstructure |

"최근 2개 날짜"의 기준은 SSRN 의 **승인일(`approved_date`)** 이다. 실측 볼륨은
7개 저널 합계 29~35편 수준으로, arXiv 와 합쳐도 하루치 처리량이 부담되지 않는다.

### 10.2 수집 경로 — 두 단계로 쪼갠 이유

SSRN 은 arXiv 와 달리 **Cloudflare JS 챌린지**로 막혀 있다. 다만 전부 막힌 것은 아니라
경로를 둘로 나눴다.

| 대상 | 경로 | Cloudflare |
|---|---|---|
| 목록(제목·저자·소속·승인일·abstract_id) | `api.ssrn.com/content/v1/bindings/{jid}/papers` | **없음** — 평범한 requests 로 읽힘 |
| 초록·PDF 링크 | `papers.ssrn.com/sol3/papers.cfm?abstract_id=` | 있음 — 브라우저 필요 |

목록 API 는 `sort=0` 에서 승인일 내림차순이고 `index`/`count` 로 페이지를 넘긴다.
초록은 주지 않으므로 논문 페이지를 열어야 한다. `api.ssrn.com` 의 논문 상세
엔드포인트는 모두 401 이었다.

### 10.3 Cloudflare 통과 — 실측 결과

| 방법 | 결과 |
|---|---|
| `requests` (브라우저 UA·헤더 완비) | ❌ 403 "Just a moment..." |
| Playwright 번들 Chromium (headless) | ❌ 60초 대기해도 챌린지 유지 |
| Playwright 번들 Chromium (headed) | ❌ 동일 |
| Playwright `channel="chrome"` (실제 Chrome, headed) | ❌ 동일 |
| **직접 실행한 Chrome + `connect_over_cdp`** | ✅ **약 4초 만에 통과** |

Playwright 가 `launch()` 한 브라우저는 자동화 플래그 때문에 판정당한다. 반면 우리가
`--remote-debugging-port` 로 띄운 평범한 Chrome 에 CDP 로 붙으면 통과한다.
한 번 통과하면 `cf_clearance` 쿠키가 전용 프로필(`state/chrome_profile`)에 남아
다음 실행이 빨라진다.

- 창은 `--window-position=-2400,-2400` 으로 화면 밖에 띄워 작업을 방해하지 않는다.
  디버깅이 필요하면 `--show-browser`.
- **챌린지 페이지 제목은 브라우저 언어로 번역된다**(한국어 Chrome 에서 "잠시만 기다리십시오…").
  제목으로 통과 여부를 판정하면 안 되고, 목표 셀렉터(`div.abstract-text`)의 등장으로 판정한다.
- 초록 없이 PDF 만 받는 경로는 만들지 않았다. PDF 다운로드도 같은 `cf_clearance` 쿠키를
  쓰므로 어차피 브라우저를 한 번 거쳐야 한다.

대안으로 Crossref·OpenAlex·Semantic Scholar 에서 초록을 받는 길도 확인했으나,
**승인 당일~이틀 된 SSRN 워킹페이퍼는 세 곳 모두 아직 색인하지 않아**(전부 404) 쓸 수 없었다.

### 10.4 상세 리포트 수식 깨짐 수정

arXiv 의 HTML 판은 LaTeXML 출력이라 수식이 `<math alttext="A_{id}(p,r)=\sum...">` 형태로
들어 있다. 기존 코드는 태그를 그냥 벗겨서 첨자·기호가 뭉개진 문자열(`A id p r`)을
모델에 넘겼고, 그래서 리포트의 수식이 전부 깨졌다.

- 태그 제거 **전에** `alttext` 를 `\( ... \)` 로 복원해 원본 LaTeX 를 살린다.
- 프롬프트에 수식 표기 규칙을 넣어 인라인은 `\( \)`, 별행은 `\[ \]` 로 쓰게 한다.
- 리포트 HTML 에 MathJax 3 을 넣어 실제로 렌더한다. (유일한 외부 의존.
  오프라인이면 LaTeX 원문이 그대로 보여 읽기는 가능하다.)
- SSRN 은 PDF 텍스트라 수식이 애초에 평문으로 나오므로 같은 규칙이 그대로 적용된다.

### 10.5 번역 문체 개선

요약·상세 리포트 프롬프트 양쪽에 문체 규칙을 명시했다.

- 직역 금지, 한 문장 60자 안팎, 수동태→능동태
- 번역투 조사 표현 금지: "~에 대한", "~를 통하여", "~에 있어서", "~하는 것을 통해"
- 명사 3개 이상 연쇄 금지, 한 문단 2~4문장
- 나열·비교는 문장 대신 `<ul>`/`<table>` 로 분리
- 전문 용어는 첫 등장 때만 한국어(영문) 병기

### 10.6 통합 저장소

`seen.json` 하나에 두 출처를 함께 담는다. 키 충돌을 막으려고 SSRN 은 `ssrn-` 접두어를 쓴다.

| 필드 | arXiv | SSRN |
|---|---|---|
| `id` | `2608.28399` | `ssrn-7375498` |
| `ext_id` | `2608.28399` | `7375498` |
| `src` | `arxiv` | `ssrn` |
| `src_cats` | `["q-fin.TR"]` | `["MMS"]` |
| `listed_date` | 목록 게시일 | 승인일 |

v0.1 로 저장된 항목은 `store._migrate()` 가 로드 시점에 `src`/`ext_id` 를 채운다.

---

## 11. ★ 점수 기준 — 시스템 트레이딩 구현 가능성

`relevance` 는 "연구가 훌륭한가"가 아니라 **계량적 규칙으로 코딩해 자동매매로 돌릴 수 있는가**
하나만 잰다. 논문의 학술적 가치와는 무관하게 매긴다.

| 점수 | 기준 |
|---|---|
| 5 | 진입·청산 규칙이 명시적이고, 공개·표준 데이터(가격·거래량·호가·옵션체인·재무제표)만으로 그대로 백테스트·자동매매 구현이 가능. 유니버스와 리밸런싱 주기까지 특정됨 |
| 4 | 매매 신호나 전략 방법론을 제시하고 표준 데이터로 재현 가능. 파라미터·집행 규칙 일부는 직접 결정 |
| 3 | 쓸 만한 특징(feature)이나 리스크·포트폴리오 구성 기법은 주지만, 옮기려면 설계를 상당히 더 해야 함 |
| 2 | 착상은 흥미로우나 구현 장벽이 큼 — 구하기 어려운 데이터(위성 사진, 독점 주문흐름, 설문, 수작업 라벨), 접근 어려운 자산, 초저지연 인프라 전제 |
| 1 | 이론·정책·법률·제도·서베이 등 자동매매로 옮길 여지가 사실상 없음 |

**가산점 (+1, 상한 5)** — 다음에 해당하면 기본 점수에 더한다.

- 널리 쓰이는 통념이나 기존 전략을 **반증**해서, 쓰지 말아야 할 것을 알려준다
- **백테스트·검증 방법론 자체를 개선**한다 (누출 차단, 다중검정 보정, 거래비용 반영)
- 착상이 독창적이어서 직접 구현하지 않더라도 읽을 값어치가 크다

데이터를 구할 수 없으면 결과가 아무리 좋아도 2 이하로 내린다. 점수와 함께
`relevance_why` 에 근거를 한 문장으로 남기고, 여기에는 **데이터 확보 난이도를 반드시 적는다.**

### 재채점 결과 (2026-08-31, 43편)

| 점수 | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| 편수 | 2 | 11 | 12 | 7 | 11 |

평균 2.67. 이전 기준에서는 대부분 3~4에 몰려 변별력이 없었다. 법률·제도·서베이 논문이
1점으로, 위성 사진·설문·독점 데이터에 기대는 논문이 2점으로 내려가면서 상위권이 드러난다.

---

## 12. v0.3 — 원클릭 리포트 생성과 Git 연동

### 12.1 "복사 → 터미널 붙여넣기" 를 없앤 방법

정적 HTML 은 스스로 Claude 를 호출할 수 없다는 제약이 v0.1 설계의 출발점이었다.
그래서 localStorage 큐 → 명령어 복사 → 터미널 실행이라는 왕복이 생겼는데, 실제로 써 보니
이 왕복이 가장 불편한 지점이었다.

해법은 정적 파일을 포기하는 대신 **선택적으로 서버를 얹는 것**이다.

```
GET  /api/ping             살아 있는지
POST /api/report {id}      생성 큐에 넣기
GET  /api/status?id=...    상태 조회 (queued / running+note / done+url / error)
```

- 페이지는 열릴 때 `api/ping` 을 한 번 찔러 본다. 응답이 있으면 라이브 모드,
  없으면 예전 명령어 복사 모드로 **조용히** 되돌아간다.
  덕분에 같은 HTML 한 벌이 로컬 서버·파일 열기·GitHub Pages 세 곳에서 모두 동작한다.
- 워커는 하나만 둔다. claude 호출과 Chrome 이 동시에 여러 개 뜨면 서로 방해한다.
- SSRN 브라우저는 서버가 살아 있는 동안 한 번만 띄워 재사용한다.
  건별로 띄우면 Chrome 기동 + Cloudflare 통과에 매번 6~7초가 더 든다.
- 생성이 끝나면 `on_done` 콜백이 다이제스트 HTML 을 다시 만들어 링크를 반영한다.
  라이브 모드에서는 JS 가 버튼을 그 자리에서 링크로 바꾸므로 새로고침도 필요 없다.

실측: SSRN 논문 1편(PDF 받기 + 전문 요약) 제출부터 완료까지 약 140초.

### 12.2 `--deep N`

수집 직후 ★ 상위 N편의 상세 리포트를 미리 만들어 둔다. 어차피 읽을 논문은 정해져 있으니
버튼을 누르기 전에 준비해 두는 편이 낫다. `python run.py --deep 5` 로 쓴다.

### 12.3 Git 세팅에서 걸린 것

- **git 이 설치돼 있지 않았고, winget 설치가 UAC 에서 막혔다**(exit 12).
  관리자 권한이 필요 없는 PortableGit + gh CLI zip 을 `%LOCALAPPDATA%\Programs` 에
  풀고 사용자 PATH 에 등록하는 방식으로 우회했다.
- **`state/chrome_profile/` 은 반드시 제외한다.** 150MB 넘는 캐시인 데다
  `cf_clearance` 세션 쿠키가 들어 있어 공개 저장소에 올리면 안 된다.
- `state/seen.json` 과 `report/` 는 의도적으로 커밋한다. 누적 DB가 함께 가야
  다른 기기에서 clone 해도 이미 요약한 논문을 건너뛴다.
- 루트 `index.html` 을 Pages 진입점으로 자동 생성한다. `report` 명령이 돌 때마다
  날짜별 다이제스트와 상세 리포트 목록을 다시 만든다. Jekyll 처리를 끄려고
  `.nojekyll` 도 둔다.

### 12.4 public 저장소의 대가

Pages 무료 플랜은 public 저장소에서만 동작한다. 그래서 `seen.json` 과 리포트에 담긴
**논문 초록 원문이 함께 공개된다.** arXiv 초록은 배포에 제약이 없지만 SSRN 초록은
저자·SSRN 에 저작권이 있어 회색지대다. 개인 연구 노트 수준이라 실질적 위험은 낮다고 보고
진행했으나, 문제가 되면 저장소를 private 으로 바꾸고 Pages 를 끄면 된다.
